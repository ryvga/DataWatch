# DataWatch — Architecture

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
│  profile_table         │   │  9 tables                │
│  run_anomaly_checks    │   │  JSONB for metrics,      │
│  generate_llm_narration│   │  narration, config       │
│  send_alerts           │   │  Composite indexes on    │
│  cleanup_old_profiles  │   │  (table_id, collected_at)│
└─────────┬─────────────┘   └─────────────────────────-┘
          │
┌─────────▼─────────────────────────────────────────────┐
│  Redis                                                  │
│  • Celery broker + result backend                       │
│  • Discovery cache  key=discovery:{source_id}  TTL=30m │
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
   g. Update `monitored_table.last_profiled_at`
   h. Enqueue `run_anomaly_checks.delay(table_id, profile_id)`

4. `run_anomaly_checks` task:
   a. Load current profile + 30-day history
   b. Run all 4 detectors (z-score, rules, IsoForest, STL)
   c. Persist `CheckResult` rows
   d. If failures: `IncidentService.create_or_update()` → create/append incident
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
is_active BOOL | dbt_model_yaml TEXT | created_at | last_profiled_at
```

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
severity (P1|P2|P3) | status (open|acknowledged|resolved)
title VARCHAR(500) | fired_checks JSONB | llm_narration JSONB
created_at | acknowledged_at | resolved_at
INDEX (org_id, created_at) | INDEX (status, created_at)
```

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
    async def test_connection(self) -> bool
    async def discover_schemas(self) -> list[SchemaInfo]
    async def execute_profile_query(self, query: str) -> dict
    async def get_table_ddl(self, schema: str, table: str) -> str
    async def close(self) -> None
```

`ConnectorFactory.create(source_type, config)` returns the right implementation.

| Connector | File | Notes |
|---|---|---|
| PostgresConnector | `connectors/postgres.py` | psycopg3 async, connection pool min=1/max=5 |
| BigQueryConnector | `connectors/bigquery.py` | Service account JSON auth, sync client wrapped |
| DuckDBConnector | `connectors/duckdb.py` | In-process, path from config, great for demo |
| SnowflakeConnector | `connectors/snowflake.py` | Stub — raises NotImplementedError, API returns 501 |

---

## Profiling Query Design

`ProfilerService` (`app/services/profiler.py`) builds **one SQL query** per table run:

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
FROM schema.table
```

Column types are introspected once (via `get_table_ddl`) and classified as `numeric | text | timestamp | date` to generate appropriate expressions. Schema fingerprint = MD5(sorted `col:type` pairs).

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
