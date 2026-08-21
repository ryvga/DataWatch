# Panopta (DataWatch engine)

Data quality monitoring platform with LLM-powered incident narration.

Monitors your warehouse tables, detects anomalies (z-score, Isolation Forest, STL, rule-based), creates incidents, and delivers AI-generated root-cause reports to Slack, email, or PagerDuty.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  React SPA (Vite + Tailwind + Recharts)                     │
│  Overview · Table Detail · Incident Detail · Settings       │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTP / REST
┌────────────────────▼────────────────────────────────────────┐
│  FastAPI (Python 3.12)                                       │
│  /auth  /orgs  /api/v1/sources  /tables  /incidents  /alerts│
│  APScheduler — one interval job per monitored table         │
└──────┬──────────────────────────┬───────────────────────────┘
       │ Celery tasks             │ SQLAlchemy async
┌──────▼──────────┐    ┌──────────▼──────────┐
│  Celery Worker  │    │  PostgreSQL 16       │
│  profile_table  │    │  20 tables, indexes  │
│  anomaly_checks │    └─────────────────────┘
│  llm_narration  │
│  send_alerts    │    ┌─────────────────────┐
└──────┬──────────┘    │  Redis              │
       └───────────────►  Task broker        │
                       │  IsoForest cache    │
                       │  Discovery cache    │
                       │  LLM narration cache│
                       └─────────────────────┘
```

## Connectors

Connector metadata distinguishes connection/discovery from scheduled profiling. A
connector is not described as fully supported merely because it can connect.

| Source | Readiness | Current application path | Current limit |
|---|---|---|---|
| PostgreSQL / Aurora | Stable | Connect, discover, schema, full profile, restricted legacy SQL, typed-plan execution, safe DSL activation/scheduling/manual runs/incident bridge | Additional warehouse conformance and richer DSL templates pending |
| DuckDB | Beta | Connect, discover, schema, full profile, restricted legacy SQL, verified typed-plan execution, safe DSL activation/scheduling/manual runs/incident bridge | Local/in-process deployment model; hosted file-path boundary pending |
| SQLite | Beta | Connect, discover, native schema binding, typed freshness validation, core profile, restricted legacy SQL, verified typed-plan execution, safe DSL activation/scheduling/manual runs/incident bridge | Hosted SaaS file-path boundary, native stddev/percentiles pending |
| MySQL | Experimental | Connect, discover, native schema binding, typed freshness validation, core scheduled profile, and parameter-bound typed monitors in a database read-only transaction; verified TLS by default; MySQL 8.4 is a required CI service | Percentiles and an API-to-worker persisted live vertical remain pending |
| MariaDB | Experimental | First-class catalogue entry using the MySQL-family adapter; the same core profile and read-only typed-monitor contract is required against MariaDB 11.4 LTS in CI | Percentiles and an API-to-worker persisted live vertical remain pending |
| Redshift | Experimental | Connect, discover, schema | Scheduled profile conformance pending |
| BigQuery | Experimental | Connect, discover, schema | Async/cost-bounded profile planner pending |
| ClickHouse | Experimental | Connect, discover, schema | Scheduled profile dialect pending |
| Databricks | Experimental | Connect, discover, schema | Scheduled profile dialect pending |
| Trino / Presto | Experimental | Connect, discover, schema | Auth and profile conformance pending |
| SQL Server / Azure SQL | Experimental | Connect, discover, native schema binding, typed freshness validation, core scheduled profile, and parameter-bound typed monitors restricted to a read-only principal; CI packages ODBC Driver 18 and requires a SQL Server 2022 container lane | A trusted-certificate live TLS lane, API-to-worker persisted vertical, and percentile metrics remain pending |
| MongoDB | Experimental | Connect, discover, inferred schema, byte/document/field-bounded native profile, indexed scalar-date freshness, and immutable typed aggregation monitors with mandatory document ceilings; verified TLS and explicit provenance | Trusted-certificate live TLS, repeated-sample drift confirmation, controlled scale, and the remaining unsupported document metrics/predicates are promotion gates |
| Cassandra | Experimental | Connect, scoped discovery, deterministic partition metadata, and immutable manual typed monitors using exact partition bindings, prepared statements, mandatory row ceilings, and the shared incident/recovery path; Cassandra 5 is a required CI service; verified TLS is the default | Scheduled profiling, live trusted-certificate TLS, Cassandra 4 compatibility, controlled scale, and secure Astra bundle support remain pending |
| Snowflake | Planned | Registry metadata only | Connector is a 501 stub |
| Redis | Experimental | Connect, bounded keyspace discovery/profile, TTL/memory/type/Hash/Streams metadata without reading values; verified TLS by default | Typed monitor plans, incident bridge, mutation corpus, and dedicated Redis 7/8 lanes pending |
| Oracle | Planned | Not yet registered as a source | Thin-driver connection/discovery/schema/profile vertical pending |

The provider-by-provider completion gates and delivery order are maintained in
[`docs/connector-catalogue.md`](docs/connector-catalogue.md).
The reproducible MySQL/MariaDB/SQLite/SQL Server conformance and tiny-table timing record
is in [`docs/evidence/sql-connector-conformance-2026-08-21.md`](docs/evidence/sql-connector-conformance-2026-08-21.md).

`GET /api/v1/sources/connector-types` returns this readiness plus machine-readable
capabilities. Legacy custom SQL is a restricted, transitional escape hatch: definitions
are AST-validated to one table, run through a read-only/timeout connector path, and must
return exactly one non-negative integer scalar. The typed safe monitor DSL roadmap is
documented in `docs/monitor-dsl.md`.

Scheduled profiling executes one aggregate statement per asset. Sampling is currently
disabled: it will only be enabled after connector-native non-scanning estimates and
sample provenance prevent sampled counts from masquerading as true row counts.

The `datawatch.io/v1alpha1` runtime provides strict JSON validation, tenant asset
resolution, canonical hashing, bounded predicates, capability planning, draft creation,
append-only revision history, and short-lived preview attestations under `/api/v2`.
Preview now parses connector DDL into a typed, asset-bound schema and produces
deterministic parameterized PostgreSQL, DuckDB, SQLite, MySQL, MariaDB, and SQL Server
aggregate plans only when every referenced field and operation is compatible. Internal
PostgreSQL, DuckDB, and SQLite
adapters plus the MySQL family and SQL Server bind those parameters, enforce their
connector-specific read-only/timeout controls, and validate the exact typed result
contract; real container/file executions are covered by required tests. Public execution
and activation are enabled for these compiled runtimes. Activation binds an immutable
revision to the existing profile cadence, while
manual runs use the same idempotent reservation and lease state machine. Migration 012
and the internal run service provide ordered claims, expiring leases, immutable terminal
audits, atomic policy-state finalization, and a typed incident bridge; unsupported
connector plans remain fail-closed.
`maxBytesScanned` is enforced with conservative storage bounds and a Redis lease permits
only one compiled query per tenant/source at a time. Unsaved connection tests and source
credential changes require an owner/admin, share a Redis attempt limit, and pass the
deployment DNS/IP/local-file egress policy before a connector is created.

The internal evaluator implements deterministic `breachWhen`, consecutive breach,
recovery pass, and cooldown decisions. The idempotent run orchestrator persists every
attempted transition, and the incident bridge opens/resolves typed `monitor_dsl` checks.
Definition edit head and active runtime revision are separate pointers, preventing
unactivated edits from changing runs.

Public competitor capabilities and the independent feature-parity backlog are tracked in
[`docs/competitive-roadmap.md`](docs/competitive-roadmap.md).

## AI governance roadmap

DataWatch's next product layer is a database-native AI governance control plane. It will
connect AI-system inventory and immutable release versions to the exact training, RAG,
inference, evaluation, and logging assets they use; continuously evaluate data and
operational controls; preserve evidence, approvals, exceptions, and incidents; and export
explainable framework mappings. The design avoids automated legal-certification claims and
raw prompt/training-data collection by default. See
[`docs/ai-governance.md`](docs/ai-governance.md).

## Quick Start (local)

**Prerequisites:** Docker, Docker Compose

```bash
# 1. Clone
git clone <repo-url> && cd DataWatch

# 2. Configure
cp .env.example .env
# Edit .env — set SECRET_KEY, FERNET_MASTER_KEY, OPENROUTER_API_KEY

# 3. Start stack (the migrate service applies Alembic before API/worker start)
docker compose up -d

# 4. Seed all demo workspaces (optional)
backend/venv/bin/python scripts/quickstart.py --reset --local

# 5. Register org + get API key
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"org_name":"Demo","org_slug":"demo","email":"admin@demo.com","password":"secret"}'
```

Frontend: http://localhost:5173 (run `cd frontend && npm ci && npm run dev`)
API docs: http://localhost:8000/docs

## Demo Walkthrough

```bash
# Reset and seed all workspaces, users, tables, history, and incidents
backend/venv/bin/python scripts/quickstart.py --reset --local

# In the UI:
# 1. Settings → Data Sources → Add (type: postgres, host: postgres, db: datawatch)
# 2. Settings → Tables → Add demo.orders (freshness_column: created_at)
# 3. Overview → should show healthy

# Inject anomaly
backend/venv/bin/python scripts/quickstart.py --inject --local

# Trigger profile run
curl -X POST http://localhost:8000/api/v1/tables/<orders-id>/run \
  -H "x-api-key: $DATAWATCH_API_KEY"

# Watch the incident appear with LLM narration in the UI
```

Available scenarios: `pipeline_failure` · `null_spike` · `schema_drift` · `row_explosion`

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `SECRET_KEY` | JWT signing key (32-byte hex) | ✅ |
| `FERNET_MASTER_KEY` | Credential encryption master key | ✅ |
| `DATABASE_URL` | PostgreSQL async URL (`postgresql+asyncpg://...`) | ✅ |
| `REDIS_URL` | Redis URL | ✅ |
| `SOURCE_ALLOW_PRIVATE_NETWORKS` | Explicit production opt-in for private database targets | No (default `false`) |
| `SOURCE_LOCAL_PATH_ROOT` | Allowed production root for SQLite/DuckDB files | No (disabled when empty) |
| `OPENROUTER_API_KEY` | OpenRouter API key for LLM narration | Optional |
| `LLM_MODEL` | Model to use (default: `nvidia/nemotron-3-ultra-550b-a55b:free`) | Optional |
| `LLM_BASE_URL` | LLM API base URL (default: `https://openrouter.ai/api/v1`) | Optional |
| `SENDGRID_API_KEY` | Email alerts | Optional |
| `FROM_EMAIL` | Alert sender address | Optional |
| `ENVIRONMENT` | `development` or `production` | Optional |
| `LOG_LEVEL` | `INFO` or `DEBUG` | Optional |

Generate keys:
```bash
python -c "import secrets; print(secrets.token_hex(32))"          # SECRET_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # FERNET_MASTER_KEY
```

## API Reference

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/register` | — | Create org + user, returns API key |
| POST | `/auth/login` | — | Returns JWT token |
| GET | `/health` | — | DB + Redis + scheduler status |
| GET | `/ready` | — | HTTP 503 until DB and Redis can serve requests |
| GET | `/api/v1/sources` | JWT | List data sources |
| POST | `/api/v1/sources` | owner/admin JWT | Register new source |
| POST | `/api/v1/sources/test-connection` | owner/admin JWT | Test unsaved credentials under rate/egress policy |
| POST | `/api/v1/sources/{id}/test` | JWT | Test connection |
| POST | `/api/v1/sources/{id}/discover` | JWT | Discover schemas/tables |
| GET | `/api/v1/tables` | JWT | List monitored tables |
| POST | `/api/v1/tables` | JWT | Add table to monitoring |
| POST | `/api/v1/tables/{id}/run` | JWT/API | Trigger immediate profile |
| GET | `/api/v1/tables/{id}/profiles` | JWT | Profile history |
| GET | `/api/v1/incidents` | JWT | List incidents (filterable) |
| PATCH | `/api/v1/incidents/{id}/acknowledge` | JWT | Acknowledge |
| PATCH | `/api/v1/incidents/{id}/resolve` | JWT | Resolve |
| POST | `/api/v1/alerts` | JWT | Create alert config |
| POST | `/api/v1/alerts/{id}/test` | JWT | Send test alert |

## Railway Deploy

`railway.toml` deploys the API and worker services. Deploy the frontend as a
separate service from `frontend/Dockerfile`; see `docs/deployment.md` for the
complete service and environment-variable setup.

```bash
# Install Railway CLI
npm install -g @railway/cli && railway login

# Create project
railway init

# Add plugins: Postgres + Redis via Railway dashboard

# Deploy the configured backend services
railway up

# Set env vars
railway variables set SECRET_KEY=... FERNET_MASTER_KEY=... OPENROUTER_API_KEY=...

# Run migrations
railway run alembic upgrade head
```

## Detection Methods

| Method | Trigger | Min. History |
|--------|---------|--------------|
| Z-Score | \|z\| > sensitivity (default 3σ) | 7 profiles |
| Rule-Based | row_count=0, freshness breach, schema drift, null spike >20pp | 0 |
| Isolation Forest | multivariate anomaly score < -0.1 | 21 profiles |
| STL Seasonal | row_count residual > 3σ of historical residuals | 21 daily profiles |
| Cardinality Drop | distinct ratio drops by more than 30% from baseline | 7 profiles |
| Row Growth Rate | row-count delta deviates from the rolling baseline | 7 profiles |
| Enum / Category Drift | new or disappearing categorical values | 3 profiles |

## Incident Severity

| Condition | Severity |
|-----------|----------|
| row_count = 0 OR freshness SLA breach | P1 |
| schema drift OR ≥3 checks fail | P2 |
| 1–2 statistical failures | P3 |
