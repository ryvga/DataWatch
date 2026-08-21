# DataWatch — Architecture

## Planned AI governance control plane

The next product evolution is a database-native AI governance layer: an inventory of AI
systems and immutable versions, explicit mappings from each version to its training, RAG,
inference, evaluation, and logging data, versioned governance policies, continuous evidence,
review/exception workflows, and governance incidents. It will reuse connector profiles,
schema bindings, typed monitors, ordered run audits, teams, incidents, and alerts.

The implementation remains evidence-oriented and fail-closed: it distinguishes machine
observations, customer assertions, human approvals, and framework mappings; it does not
claim legal certification or let an LLM decide mandatory controls. See
[`docs/ai-governance.md`](ai-governance.md) for the domain model, policy DSL, enforcement
ladder, standards mapping, PFE evaluation plan, and first vertical slice.

## System Overview

DataWatch is a multi-tenant data quality monitoring platform. It is structured as a classic async Python microservice with one API process, one Celery worker process, and a React SPA served by nginx.

```
┌─────────────────────────────────────────────────────────────────────┐
│  Browser — React 18 SPA (Vite + Tailwind + Recharts)                │
│  Overview · Table Detail · Incident Detail · Settings               │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ REST / JSON
┌──────────────────────────▼──────────────────────────────────────────┐
│  FastAPI (Python 3.12, async)                                        │
│                                                                      │
│  Routers:  /auth  /orgs  /api/v1/sources  /tables                   │
│            /api/v1/incidents  /api/v1/alerts                         │
│                                                                      │
│  APScheduler (lifespan) — one IntervalTrigger job per active table  │
└─────────┬────────────────────────────┬────────────────────────────-─┘
          │ Celery .delay()             │ SQLAlchemy async
          │                            │
┌─────────▼─────────────┐   ┌──────────▼──────────────┐
│  Celery Worker         │   │  PostgreSQL 16           │
│                        │   │                          │
│  profile_table         │   │  14+ tables              │
│  bootstrap_autopilot   │   │  JSONB for metrics,      │
│  run_anomaly_checks    │   │  narration, config,      │
│  generate_llm_narration│   │  autopilot state         │
│  send_alerts           │   │  Composite indexes on    │
│  cleanup_old_profiles  │   │  (table_id, collected_at)│
└─────────┬─────────────┘   └─────────────────────────-┘
          │
┌─────────▼─────────────────────────────────────────────┐
│  Redis                                                  │
│  • Celery broker + result backend                       │
│  • Discovery cache  key=discovery:{org}:{source_id} TTL=30m │
│  • IsoForest model  key=isoforest:{table_id}   TTL=7d  │
│  • LLM narration    key=llm:incident:{id}      TTL=24h │
│  • Rate counters    key=rate:{kind}:{org}:{date}        │
└────────────────────────────────────────────────────────┘
```

---

## Request Lifecycle — Profile Run

1. APScheduler fires `_enqueue_profile(table_id)` every `check_interval_minutes`
2. Enqueues `profile_table.delay(table_id)` to Redis broker
3. Celery worker picks up task:
   a. Load `MonitoredTable` + `DataSource` from DB
   b. Rate-limit check via Redis counter
   c. `decrypt_config(source.connection_config["encrypted"], org_id)`
   d. `ConnectorFactory.create(source.type, config)` → `BaseConnector`
   e. `ProfilerService.profile(connector, schema, table, freshness_column)`
      - `get_table_ddl()` → column type introspection
      - `build_profile_query()` → single aggregate SQL
      - `execute_profile_query(query)` → dict of metrics
      - `parse_results()` → `ProfileResult`
   f. Persist `TableProfile` to DB
   g. Update `monitored_table.last_profiled_at` and `monitored_table.autopilot.steps.profile`
   h. Enqueue `run_anomaly_checks.delay(table_id, profile_id)` and `run_custom_monitors.delay(table_id, profile_id)`

`POST /api/v1/tables` also enqueues `bootstrap_table_autopilot.delay(table_id)`. This parses the schema snapshot, runs AI monitor recommendation, auto-enables safe built-in baseline checks in table autopilot state, infers a freshness column when safe, and stages risky/custom-SQL recommendations for review.

4. `run_anomaly_checks` task:
   a. Load current profile + 30-day history
   b. Run all 4 detectors (z-score, rules, IsoForest, STL)
   c. Persist `CheckResult` rows
   d. If failures: `IncidentService.auto_resolve()` closes recovered core-rule incidents first, then `create_or_update()` creates/appends remaining failures
   e. If all pass: `IncidentService.auto_resolve()` → resolve if previously open
   f. If new incident: enqueue `generate_llm_narration.delay(incident_id)`

5. `generate_llm_narration` task:
   a. Check Redis cache (skip if hit)
   b. `build_context(incident_id)` → compact TSV-style context string
   c. `generate_narration(context)` → Anthropic API → `NarrationResult` Pydantic validation
   d. Retry once with hint if validation fails
   e. Persist to `incident.llm_narration` JSONB + cache in Redis
   f. Enqueue `send_alerts.delay(incident_id)`

6. `send_alerts` task:
   a. Load matching `AlertConfig` rows (org + table, filtered by `is_active`)
   b. Check `min_severity` threshold per config
   c. Dispatch Slack / Email / PagerDuty

---

## Data Model Detail

### organizations
```sql
id UUID PK | name VARCHAR(255) | slug VARCHAR(100) UNIQUE | plan VARCHAR(50) | created_at TIMESTAMPTZ
```
Plan values: `free` | `starter` | `growth` | `enterprise`

### users
```sql
id UUID PK | org_id FK→organizations | email UNIQUE | password_hash | is_admin BOOL | created_at
```

### api_keys
```sql
id UUID PK | org_id FK→organizations | name | key_hash (bcrypt) | created_at | last_used_at
```
Raw key prefixed `dw_` — shown once at register, only hash stored.

### data_sources
```sql
id UUID PK | org_id FK | name | type (postgres|bigquery|snowflake|duckdb)
connection_config JSONB  ← {"encrypted": "<fernet_ciphertext>"}
status (pending|connected|error|paused) | last_connected_at
```
`connection_config` is always `{"encrypted": "..."}` — the actual credentials JSON is Fernet-encrypted at the application layer using a per-org HKDF-derived key.

### monitored_tables
```sql
id UUID PK | source_id FK | schema_name | table_name
freshness_column | check_interval_minutes INT | sensitivity FLOAT (z-score threshold)
is_active BOOL | dbt_model_yaml TEXT | autopilot JSONB | created_at | last_profiled_at
```

### monitors and monitor_revisions

```sql
monitors:
id UUID PK | org_id FK | table_id FK | name | mode | status
current_revision INT | active_revision_id FK nullable | created_by FK
created_at | updated_at | activated_at
UNIQUE (org_id, table_id, name)

monitor_revisions:
id UUID PK | monitor_id FK | revision INT | definition_version
definition_hash CHAR(64) | definition JSONB | validation_status
schema_fingerprint CHAR(64) | created_by FK | created_at
UNIQUE (monitor_id, revision)
```

The monitor row is stable identity and lifecycle state. Definitions are canonical,
append-only snapshots; edits use `expectedRevision` compare-and-swap semantics so two
writers cannot silently overwrite one another. The application exposes no update or
delete endpoint for revision rows.
Edits advance `current_revision`; execution may use only `active_revision_id`. A new edit
therefore cannot alter runtime behavior until a fresh attested activation changes the
active pointer. A database check forbids `status = 'active'` without that pointer, and a
composite foreign key requires the active revision to belong to the same monitor.

### monitor_runs

```sql
id UUID PK | org_id FK | monitor_id FK | revision_id FK | table_id FK
idempotency_key | trigger_type | profile_id | sequence_at | queued_at
plan_hash | planner_version | definition_hash | schema_fingerprint
status | attempt | claim_token | lease_expires_at
measurements JSONB | result JSONB | error_code | error | started_at | completed_at
UNIQUE (org_id, idempotency_key)
```

This is the execution audit boundary for the typed runtime. A partial unique index allows
only one running execution per monitor; another prevents duplicate profile triggers.
Terminal rows retain versioned measurements/decisions or an allowlisted sanitized error.
The internal state machine is queryable but not dispatched by a public lifecycle yet.

### monitor_evaluation_states

```sql
monitor_id UUID PK | org_id FK | revision_id FK | phase
breach_streak | recovery_streak | cooldown_until
last_run_id | last_sequence_at | last_idempotency_key | version | updated_at
```

This mutable row is locked and advanced atomically with terminal run finalization. It is
separate from terminal audit rows so retry/lease mechanics cannot rewrite history.

### table_profiles
```sql
id UUID PK | table_id FK | collected_at TIMESTAMPTZ
row_count INT | freshness_seconds FLOAT | schema_fingerprint VARCHAR(64)
column_metrics JSONB  ← {"col_name": {"null_rate": 0.01, "mean": 150, "stddev": 50, ...}}
profiling_duration_ms INT | error TEXT
INDEX (table_id, collected_at)
```

### check_results
```sql
id UUID PK | table_id FK | profile_id FK
check_type (z_score|rule|isoforest|stl) | check_name | column_name
status (passed|failed|error)
observed_value FLOAT | expected_range JSONB ← {"low": x, "high": y}
deviation_score FLOAT | checked_at TIMESTAMPTZ
INDEX (table_id, checked_at) | INDEX (status, checked_at)
```

### incidents
```sql
id UUID PK | org_id FK | table_id FK
severity (P1|P2|P3) | status (open|acknowledged|investigating|resolved|muted|ignored)
title VARCHAR(500) | fired_checks JSONB | llm_narration JSONB
created_at | acknowledged_at | resolved_at
INDEX (org_id, created_at) | INDEX (status, created_at)
```

Muted and false-positive incidents store suppression windows in `llm_narration.muted_until` and `llm_narration.false_positive_until`. Identical checks are suppressed during those windows.

### alert_configs
```sql
id UUID PK | org_id FK | table_id FK (nullable = org-wide)
channel (slack|email|pagerduty)
config JSONB  ← {"webhook_url": "...", "min_severity": "P2"}
is_active BOOL | created_at
```

---

## Connector Architecture

All connectors implement `BaseConnector` (abstract, `app/connectors/base.py`):

```python
class BaseConnector(ABC):
    profile_dialect: str | None
    supports_profile_sampling: bool
    async def test_connection(self) -> bool
    async def discover_schemas(self) -> list[SchemaInfo]
    async def execute_profile_query(self, query: str) -> dict
    async def get_table_ddl(self, schema: str, table: str) -> str
    async def get_table_schema(self, schema: str, table: str) -> tuple[str, set[str] | None]
    async def validate_profile_config(self, schema: str, table: str, freshness_column: str | None) -> None
    async def collect_native_profile(self, schema: str, table: str, freshness_column: str | None) -> dict
    async def close(self) -> None
```

`ConnectorFactory.create(source_type, config)` returns the implementation. Registry
metadata also publishes readiness and separate capabilities for connection tests,
discovery, schema inspection, profiling, custom monitors, and sampling. This prevents
the UI and API documentation from presenting experimental adapters as complete.

| Profile tier | Meaning |
|---|---|
| `full` | Standard metrics plus stddev and percentiles; sampling is a separate capability |
| `core` | A connector-native bounded metric set with explicit provenance; relational cores include row count, freshness, null/distinct/uniqueness, min/max/mean and text/range metrics |
| `none` | Connection/discovery may work, but scheduled profiling fails explicitly before SQL execution |

The exercised connector vertical slices are PostgreSQL, DuckDB, SQLite core, MySQL 8.4,
MariaDB 11.4 LTS, and SQL Server 2022. The three server containers are required CI gates
covering connection, discovery, deterministic schema, core profile, freshness, and a
compiled typed monitor. MySQL and MariaDB share the same adapter but retain separate
services so family/version drift is visible. SQL Server's isolated self-signed lane uses
an explicit insecure test mode; verified identity remains the runtime default.
The environment, commands, claim boundary, and 20-run measurements are preserved in
`docs/evidence/sql-connector-conformance-2026-08-21.md` and its JSON companion.
MongoDB uses a native sampled document profiler. Cassandra exposes scoped discovery and
deterministic schema snapshots plus manual typed partition monitors. The Cassandra
planner requires every partition key, binds values through a driver-prepared statement,
selects at most `maxRowsScanned + 1` rows, and fails closed instead of evaluating a
partial partition. Arbitrary caller CQL is rejected before a driver call, and Cassandra
transport defaults to certificate and hostname verification.

---

## Profiling Query Design

`ProfilerService` (`app/services/profiler.py`) builds **one aggregate query** per table
run for a declared dialect. Identifiers are quoted as identifiers, never inserted as
SQL fragments. PostgreSQL/DuckDB use the full metric set; SQLite uses a core dialect
that omits unavailable native stddev/percentile functions. MySQL has a separate core
dialect using backtick escaping, portable floating-point ratios, `TIMESTAMPDIFF`, and
`STDDEV_POP`; percentile metrics remain absent because the core capability contract does
not advertise them.
SQL Server has a separate T-SQL core dialect using bracket escaping, `DATEDIFF_BIG`,
`STDEVP`, and explicit floating-point casts; it also omits percentiles because the core
capability contract does not advertise them.
MySQL creates a hostname-verifying, certificate-required TLS context by default. An
explicit `tls_mode=disabled` exists for isolated development services and must not be
used for remote databases.

MySQL, MariaDB, SQLite, and SQL Server table onboarding returns driver-native column-name
sets rather than relying only on DDL parsing. Their connector validation rejects missing
freshness fields and fields without a date/time type before persisting an asset. SQLite
also rejects non-`main` schema names instead of silently inspecting a different asset.

Table onboarding and freshness updates bind against a connector-fetched, server-owned
DDL snapshot. Client input cannot replace this snapshot; the legacy model column name
`dbt_model_yaml` is retained internally until a data migration renames it.

Profiling does not run a preliminary exact `COUNT(*)`: that would double full-scan cost
before the aggregate and could corrupt row-count anomalies if a sampled count replaced
the true count. Sampling remains disabled until a connector supplies a non-scanning row
estimate and the persisted profile records explicit sampling provenance.

### MongoDB native profile

MongoDB uses PyMongo's `AsyncMongoClient`, replacing deprecated Motor. Connections are
restricted to one configured database, default to certificate and hostname verification,
and have bounded server-selection/connect/socket timeouts and pool size. The profile:

- reads an estimated document population without an exact collection scan;
- samples at most 1,000 documents with `maxTimeMS`, `allowDiskUse=false`, a 16-document
  cursor batch, a 128 KiB per-document envelope, and an 8 MiB total in-process budget;
- records missing/null ratios, BSON type distributions, numeric summaries, and Unicode
  string lengths without retaining raw sample values;
- permits freshness only when the field leads a non-partial index and a bounded probe
  observes an actual scalar BSON date;
- persists `profile_provenance` (`count_mode`, sampling strategy/size/limit,
  population estimate, byte/field/array limits, truncation state, and schema mode)
  alongside every profile.

Sampled document metrics currently feed only indexed freshness detection; estimated
counts do not feed exact zero/growth/seasonal or multivariate rules. A one-run sampled
fingerprint change does not open a schema incident; a future confirmation policy must
observe compatible repeated samples before promoting sampled schema drift. The design
follows the official [PyMongo async migration guidance](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/reference/migration/)
and accounts for the documented [`$sample` execution threshold](https://www.mongodb.com/docs/v8.0/reference/operator/aggregation/sample/).
The MongoDB byte envelope uses the server-side [`$bsonSize` expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bsonsize/).
Cassandra follows the [driver security guidance](https://docs.datastax.com/en/developer/python-driver/3.20/security/index.html)
by combining a certificate-required `SSLContext` with `ssl_options.server_hostname`
for identity verification.

MongoDB typed monitors use a separate planner identity,
`datawatch-v1alpha1-mongodb-1`; they are not coerced through the relational SQL/MD5
contract. Compilation emits an immutable canonical three-stage pipeline: a mandatory
`maxDocumentsScanned + 1` limit, one aggregate group, and one numeric projection. The
extra document is a scan attestation: reaching it fails the run with
`document_scan_budget_exceeded` instead of evaluating a partial measurement. Execution
sets `allowDiskUse=false`, a single-result batch, a bounded `maxTimeMS`, exact configured
database/collection scope, and an expression/stage allowlist. User strings are wrapped
in `$literal`, so values such as `$$ROOT` cannot become aggregation references.

The native planner supports row count, null/non-null, empty/whitespace, zero/negative,
boolean, numeric/text-length/freshness aggregates, and bounded violation count/rate
predicates. Distinct/duplicate metrics, metric filters, and string-pattern predicates
remain explicit compilation blockers. Preview attestations include the native planner
version; the same plan hash and sampled schema fingerprint are persisted on every run.
The required Mongo service lane proves both capped execution and an end-to-end breach →
incident → recovery transition.

### Cassandra partition monitors

Cassandra uses planner identity `datawatch-v1alpha1-cassandra-1` rather than relational
SQL. The server-owned DDL snapshot records partition and clustering-key roles. Preview
then requires `partitionBindings` to contain every partition key and no unrelated key,
plus `maxRowsScanned` between 1 and 10,000. Identifiers are rendered only by the planner;
partition values are bound by `session.prepare(...).bind(...)` and never interpolated
into CQL. The statement reads one exact partition with `LIMIT maxRowsScanned + 1`, a
bounded fetch size, and a driver timeout. Seeing the extra row raises
`row_scan_budget_exceeded`; measurements are never calculated from a truncated result.

The application evaluates allowlisted row-count, typed aggregate, freshness, and
violation metrics in memory over that bounded partition, then uses the same persisted
run, policy, incident, narration trigger, and recovery services as relational and Mongo
plans. Cassandra monitors are manual-only until a native scheduled profile contract can
supply trustworthy source-wide provenance. The required Cassandra 5 service lane proves
connection, scoped discovery, schema markers, prepared execution, mutation rejection,
overflow, cleanup, and an incident open → recovery transition. Live trusted-certificate
TLS, Cassandra 4, Astra bundles, and controlled-scale evidence remain explicit gaps.

### Redis native profile

Redis is represented as one logical `dbN.keyspace` asset. Its native profiler walks a
configured key pattern with cursor-based `SCAN`, a hard key ceiling, a count hint, and a
bounded round limit. It never calls value-reading commands such as `GET`, `HGETALL`, or
`XRANGE`. The only batched metadata commands are `TYPE`, `PTTL`, and `MEMORY USAGE`, with
`HLEN`, `XLEN`, and `XINFO GROUPS` issued only for the matching structures. This yields
type distribution, expiry/persistence counts, aggregate memory, Hash field totals, and
Stream entry/group/pending/lag totals without retaining key names or stored values.

Every profile records whether the cursor completed. A completed traversal is an exact
count for the configured pattern; hitting a bound is persisted and displayed as a lower
bound. The raw pattern is represented only by a SHA-256 digest in provenance. ACL-denied
metrics are listed in `unavailable_metrics` and use `null`, never a misleading zero.
Arbitrary caller commands are rejected. Verified TLS and hostname validation are the
default; plaintext transport requires an explicit isolated-development setting.

Redis typed monitors use planner identity `datawatch-v1alpha1-redis-1`. The deterministic
schema exposes only per-key metadata fields (`key_type`, `ttl_ms`, `memory_bytes`, Hash
size, and Stream entry/group/pending/lag counts). Its fingerprint also includes a SHA-256
digest of the configured key pattern, so changing scope invalidates an existing plan.
Every definition requires `maxKeysScanned` between 1 and 10,000 and sampling off.

Execution performs a cursor traversal capped at `maxKeysScanned + 1`, then uses only the
allowlisted `TYPE`, `PTTL`, `MEMORY USAGE`, `HLEN`, `XLEN`, and `XINFO GROUPS` metadata
commands. It never returns key names or invokes value-reading commands. An extra key,
unfinished cursor traversal, disappearing key, scope-fingerprint change, or ACL denial
for a required field fails the run before evaluation. The bounded metadata rows feed the
same typed metric/predicate evaluator, persisted run audit, policy, incident, narration
trigger, and recovery bridge as other planners. The required Redis 7 lane proves TTL,
memory, Hash and Stream measurements plus an empty-keyspace incident followed by
data recovery.

Redis `SCAN` is not a transactional snapshot: a completed traversal has documented
observational semantics while keys mutate concurrently. The connector therefore remains
Experimental until controlled concurrent-mutation and scale tests quantify that boundary,
along with live trusted-certificate TLS and Redis 8 compatibility.

```sql
SELECT
  COUNT(*) AS _row_count,
  EXTRACT(EPOCH FROM NOW() - MAX(created_at)) AS _freshness_seconds,
  -- per column:
  SUM(CASE WHEN amount IS NULL THEN 1 ELSE 0 END)::FLOAT / NULLIF(COUNT(*), 0) AS null_rate_amount,
  COUNT(DISTINCT amount) AS distinct_count_amount,
  MIN(amount) AS min_amount,
  MAX(amount) AS max_amount,
  AVG(amount::FLOAT) AS mean_amount,
  STDDEV(amount::FLOAT) AS stddev_amount,
  ...
FROM "schema"."table"
```

Column types are introspected once (via `get_table_ddl`) and classified as `numeric | text | timestamp | date` to generate appropriate expressions. Schema fingerprint = MD5(sorted `col:type` pairs).

Discovery cache keys are tenant-scoped (`discovery:{org_id}:{source_id}`), and source
ownership is checked before any cache read to prevent cross-workspace metadata leaks.

See `docs/monitor-dsl.md` for the connector-neutral monitoring plan and the security
boundary between typed DSL monitors and the legacy custom SQL escape hatch.

Legacy SQL definitions pass through `LegacySqlMonitorPolicy`: SQLGlot must parse exactly
one `SELECT`, every base-table reference must resolve to the monitored schema/table, and
file/network/session-side-effect functions are rejected. Execution uses a connector's
separate monitor method, with database read-only mode where available, a statement/app
timeout, exact-one-row detection, and an exact one-numeric-column non-negative integer
contract. Empty or malformed results are execution errors and cannot resolve incidents.

The v2 DSL validation boundary lives in `services/monitor_dsl.py`. Strict Pydantic models
produce canonical JSON and a stable SHA-256 hash, enforce bounded recursive predicates
and measurement references, and never compile or execute user input. The router resolves
the target through the tenant's data source and returns an explicit capability plan.
Draft definitions are stored as immutable revisions. Preview attestations use HMAC-SHA256
with a five-minute TTL and bind organization, asset, definition hash, latest successful
schema fingerprint, and planner version. Activation verifies that context and binds the
immutable revision to the table's existing profile cadence for PostgreSQL, DuckDB, and
SQLite compiled runtimes. Profile-triggered and manual runs share the idempotent
reservation/lease state machine, and breach/recovery policy actions bridge into typed
`monitor_dsl` incidents. Unsupported connector plans remain fail-closed.

`services/schema_binding.py` parses generated connector DDL into an asset-scoped relation
of exact field names, normalized physical types, logical types, nullability, and a schema
fingerprint. It handles multiline/single-line DDL, quoted names, nested type parameters,
and table constraints. Unknown fields and incompatible operations fail compilation.

`services/monitor_compiler.py` builds a SQLGlot AST without parsing raw user SQL, quotes
every schema/table/field identifier as one identifier, and places every user literal in
an ordered parameter bag. PostgreSQL, DuckDB, and SQLite render deterministic preview SQL
for schema-compatible aggregate plans. Short ordinal aliases avoid database identifier
truncation collisions. Preview exposes the plan and structured support analysis, but the
rendered placeholder syntax is never sent through a generic query API.

`services/monitor_runtime.py` is the internal execution boundary. It independently
re-parses a plan as one read-only `SELECT`, verifies unique parameters and output aliases,
then dispatches named bindings to dedicated PostgreSQL, DuckDB, SQLite, MySQL/MariaDB,
or SQL Server methods.
PostgreSQL starts from a clean transaction, sets transaction read-only and a server-side
statement timeout, and always rolls back. File-backed DuckDB connections are read-only
and use interrupt-on-timeout; SQLite opens files with `mode=ro` and interrupts timed-out
queries. MySQL/MariaDB use `START TRANSACTION READ ONLY`, driver-bound values, application
timeout cancellation, and rollback. SQL Server refuses a principal with target-object
write permission, uses driver-bound values, a transaction, lock timeout, application
cancellation, and rollback. `maxBytesScanned` is preserved in the signed plan: PostgreSQL,
SQLite, file-backed DuckDB, MySQL/MariaDB, and SQL Server compare it against a conservative
complete-relation/database allocation bound before execution; adapters that cannot
enforce it fail closed. A Redis token lease
serializes compiled queries per `(org, source)` across worker processes and expires after
the query timeout plus a bounded cleanup margin. The result must have the exact ordered
aliases and finite numeric values, with
null accepted only for nullable outputs. Driver exceptions are mapped to stable domain
codes without leaking credential text. These adapters are internal capability only.

`services/monitor_evaluator.py` is a pure post-query boundary. It resolves only declared
measurement references and JSON literals, performs no coercion, and deterministically
advances consecutive-breach, recovery-pass, cooldown, and notification eligibility
state. The compiled plan stores predicate fields with `exclude_unset=True`; this preserves
the distinction between absent operands and explicit JSON null and allows strict model
reconstruction before evaluation.

`services/monitor_run_service.py` reserves runs with PostgreSQL `ON CONFLICT`, validates
tenant/monitor/revision identity, and derives the profile cursor, schema binding, and plan
hash from stored tenant-owned records rather than worker input. It claims only the
earliest `(sequence_at, idempotency_key)` trigger, serializes a monitor with a row lock
plus partial unique index, and supports bounded lease recovery and renewal.
The claim must commit before connector I/O. Finalization locks the run and policy row,
rejects expired or obsolete claim tokens, inactive revisions, and plan-context drift,
then stores the terminal audit and policy transition in one transaction. Composite
foreign keys enforce tenant/monitor/revision/asset ownership, while PostgreSQL triggers
make revisions and terminal run rows append-only. Execution is at-least-once after worker
failure, but each idempotency key has one terminal result and one policy transition.
Profile IDs are immutable soft references so profile-retention cleanup cannot delete
audit history. Direct audit deletion is rejected; cascades initiated by an intentional
parent asset/source/tenant deletion remain available for the existing data-removal flows.
Migration 012 intentionally refuses to upgrade a non-empty `monitor_runs` table because
activation was previously gated and legacy rows lack the required audit context.

---

## Anomaly Detection Detail

### Z-Score
- Rolling 14-day window of historical values per metric key
- Bootstrap: skip if < 7 points
- Skip if stddev = 0 (constant metric)
- `z = (current - mean) / stddev`, flag if `|z| > table.sensitivity`
- `expected_range = [mean - k*std, mean + k*std]`

### Rule-Based (always-on)
- `row_count_zero`: `row_count == 0`
- `freshness_sla_breach`: `freshness_seconds > check_interval_minutes * 60 * 1.5`
- `schema_drift`: `current.schema_fingerprint != prev.schema_fingerprint`
- `null_rate_spike`: `|current_null_rate - prev_null_rate| > 0.20` (per column)

### Isolation Forest
- Feature vector: all flat metrics from `_extract_flat_metrics(profile)`
- Trained on last 30 profiles, `contamination=0.05`
- Serialized to Redis (7-day TTL) keyed by `isoforest:{table_id}`
- Anomaly threshold: `decision_function(x) < -0.1`
- Minimum 21 profiles before activating

### STL Seasonal Decomposition
- Applied to `row_count` only (most likely weekly seasonal)
- `statsmodels.tsa.seasonal.STL(series, period=7, robust=True)`
- Flag if `|residual[-1]| > 3 * std(residuals[:-1])`
- Minimum 21 daily profiles

---

## LLM Context Format

`build_context()` in `app/services/llm_context.py` produces a compact string (target < 3000 tokens):

```
=== INCIDENT ===
ID:        <uuid>
Severity:  P1
Title:     [P1] demo.orders — row count dropped to 0

=== SOURCE ===
Warehouse: Demo Postgres (postgres)
Table:     demo.orders
Freshness column: created_at

=== FAILED CHECKS ===
  FAIL: row_count_zero | observed=0 | deviation=None
  FAIL: freshness_sla_breach | observed=259200 | deviation=None

=== PROFILE HISTORY (last 14 days) ===
  date        rows  freshness_s  null_amount
  2026-05-21  501   3542         0.011
  ...
  2026-06-04  0     259200       0.000   ← ANOMALY
```

Output validated by `NarrationResult` Pydantic model. 1 retry on validation failure with "Return ONLY valid JSON" hint.

---

## Security Decisions

| Concern | Implementation |
|---|---|
| Credential storage | Fernet encryption with HKDF per-org key — cross-org decryption impossible |
| API authentication | bcrypt-hashed API keys OR 15-min JWT. Never plaintext. |
| Org isolation | Every DB query on tenant data includes `org_id` filter. 404 instead of 403 (no info leak). |
| Credential in logs | `connection_config` never returned in any API response — stripped at Pydantic schema level |
| Rate limiting | Redis counters per org per day — prevents abuse on free tier |
| Connection egress | Source create/update/preview require owner/admin, share a Redis attempt limit, resolve every DNS answer, block metadata/link-local and production private targets by default, and confine local-file connectors to an explicit root |
| Connection-string injection | PostgreSQL/Redshift use driver keyword arguments; SQL Server braces and escapes every ODBC value while pinning verified TLS attributes |
