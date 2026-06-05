# DataWatch — Agent Context

> **PFE project** (Ingénieur d'État final-year thesis) by Mounir Gaiby.
> Everything built feeds into a written rapport and jury oral defense.
> Log every non-trivial decision, problem, and measurement to Notion as you go.

---

## What This Project Is

DataWatch is a **multi-tenant data quality monitoring SaaS**. It connects to databases and warehouses (PostgreSQL, MySQL, MongoDB, Cassandra, BigQuery, Snowflake, Redshift, ClickHouse, SQL Server, Databricks, Trino, DuckDB, SQLite), profiles tables on a schedule, detects anomalies using 7 statistical methods, creates incidents, and delivers AI-generated root-cause reports via Slack/email/PagerDuty.

The primary differentiator is the **LLM narration layer**: every P1/P2 incident gets an AI-written incident report explaining what happened, likely causes, and recommended actions.

**Multi-tenancy model:**
- Each customer gets a workspace at `{slug}.datawatch.io`
- Login always requires `org_slug` (workspace identifier)
- Main domain `datawatch.io` → landing page only
- `admin.datawatch.io` (configurable) → staff portal (manage orgs, plans, LLM keys)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | Python 3.12, FastAPI (async), SQLAlchemy 2.0 async |
| Task queue | Celery + Redis |
| Scheduler | APScheduler (embedded in FastAPI lifespan) |
| Database | PostgreSQL 16 (JSONB for metrics/narration) |
| Cache | Redis (discovery, IsoForest models, LLM narration) |
| AI | OpenRouter API (per-org key set via admin portal; global fallback via `OPENROUTER_API_KEY`) |
| Connectors | psycopg3, aiomysql, clickhouse-connect, aiosqlite, databricks-sql-connector, trino, bigquery, duckdb |
| Frontend | React 18, Vite, Tailwind CSS, Recharts |
| Infra | Docker Compose (dev), Railway (production) |
| Testing | pytest-asyncio, httpx AsyncClient |

---

## Repository Layout

```
DataWatch/
├── CLAUDE.md                  ← you are here
├── README.md                  ← user-facing setup guide
├── docker-compose.yml         ← dev stack (postgres, redis, api, worker)
├── docker-compose.prod.yml    ← prod stack (no source mounts)
├── railway.toml               ← Railway deploy config
├── .env.example               ← required env vars template
│
├── backend/
│   ├── app/
│   │   ├── main.py            ← FastAPI app + lifespan (scheduler start/stop)
│   │   ├── config.py          ← pydantic-settings (all env vars)
│   │   ├── database.py        ← async SQLAlchemy engine + get_db dependency
│   │   ├── auth.py            ← bcrypt, JWT, API key utils
│   │   ├── scheduler.py       ← APScheduler — one job per monitored table
│   │   ├── worker.py          ← Celery app + beat schedule
│   │   ├── tasks.py           ← Celery tasks (profile, anomaly, LLM, alerts, cleanup)
│   │   ├── models/            ← SQLAlchemy ORM models (9 tables)
│   │   ├── routers/           ← FastAPI routers (auth, orgs, sources, tables, incidents, alerts)
│   │   ├── services/          ← Business logic (profiler, anomaly, incident, LLM, alert, crypto, plans)
│   │   └── connectors/        ← Warehouse connectors (postgres, bigquery, duckdb, snowflake stub)
│   ├── alembic/               ← DB migrations (001 initial, 002 last_profiled_at)
│   ├── tests/                 ← pytest suite (conftest, test_e2e, test_anomaly, test_llm)
│   ├── requirements.txt       ← all Python deps
│   ├── pytest.ini
│   ├── Dockerfile             ← dev image
│   ├── Dockerfile.api         ← prod multi-stage API image (non-root)
│   └── Dockerfile.worker      ← prod Celery worker image
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx            ← React Router setup
│   │   ├── api/               ← axios client + all endpoint functions
│   │   ├── components/        ← HealthBadge, SeverityBadge, IncidentCard, MetricChart, NarrationPanel, Layout
│   │   └── pages/             ← Overview, TableDetail, Incidents, IncidentDetail, Settings
│   ├── package.json
│   ├── vite.config.js         ← dev proxy → localhost:8000
│   ├── tailwind.config.js
│   ├── Dockerfile             ← npm build → nginx static
│   └── nginx.conf             ← SPA fallback + /api proxy
│
├── scripts/
│   ├── seed_demo.py           ← demo data + anomaly injection (--clean/--history/--scenario)
│   └── test_llm_prompt.py     ← standalone LLM prompt tester (--fixture / --incident-id)
│
└── docs/
    ├── architecture.md        ← system design, data model, task chain, detection methods
    ├── development.md         ← setup, conventions, commit rules, testing
    ├── api.md                 ← full endpoint reference
    ├── tracking.md            ← Linear + Notion rules (read this before every session)
    └── deployment.md          ← Railway deploy guide
```

---

## Core Data Flow

```
POST /tables → scheduler.add_job()
                    ↓ every N minutes
             profile_table.delay(table_id)          [Celery]
                    ↓
             ProfilerService.profile()               [single SQL aggregate query]
                    ↓
             TableProfile saved to DB
                    ↓
             run_anomaly_checks.delay(table_id, profile_id)
                    ↓
             AnomalyService: z-score + rules + IsoForest + STL
                    ↓
             CheckResults saved → IncidentService.create_or_update()
                    ↓ (if new incident)
             generate_llm_narration.delay(incident_id)
                    ↓
             build_context() → Claude API → NarrationResult validated
                    ↓
             send_alerts.delay(incident_id)
                    ↓
             AlertService: Slack / Email / PagerDuty
```

---

## Database Schema (14 tables)

| Table | Purpose |
|---|---|
| `organizations` | Tenant — id, name, slug, plan, llm_api_key_encrypted, stripe_customer_id, subscription_status |
| `users` | Org members — email, password_hash, role (owner/admin/member), full_name |
| `staff_users` | DataWatch team — separate from org users, access admin portal only |
| `api_keys` | Programmatic access — staff-managed, key_hash (bcrypt), never returned in API |
| `invites` | Org member invitations — email, role, token, expires_at, accepted_at |
| `teams` | Team groups within an org (future feature, structure defined) |
| `team_members` | Team membership — user_id, team_id, role |
| `data_sources` | Warehouse connections — type, connection_config (Fernet-encrypted JSONB) |
| `monitored_tables` | What to watch — schema, table, interval, sensitivity, freshness_column |
| `table_profiles` | Profile snapshots — row_count, freshness_seconds, schema_fingerprint, column_metrics (JSONB) |
| `check_results` | Per-check outcome — check_type, status, observed_value, expected_range, deviation_score |
| `incidents` | Anomaly events — severity (P1/P2/P3), status (open/acknowledged/resolved), fired_checks, llm_narration (JSONB) |
| `alert_configs` | Routing rules — channel (slack/email/pagerduty), config (JSONB), min_severity |

---

## Detection Methods

| Method | Trigger | Min history |
|---|---|---|
| **Z-Score** | `\|z\| > sensitivity` (default 3σ), rolling 14-day window | 7 profiles |
| **Rule-Based** | row_count=0, freshness SLA breach, schema drift, null spike >20pp | 0 |
| **Isolation Forest** | multivariate anomaly score < -0.1, contamination=0.05 | 21 profiles |
| **STL Seasonal** | row_count residual > 3σ, period=7 | 21 daily profiles |
| **Cardinality Drop** | distinct_ratio drops >30% relative vs 14-day avg | 7 profiles |
| **Row Growth Rate** | z-score on per-profile row delta | 7 profiles |

**Severity logic:** P1 = row_count=0 or freshness breach. P2 = schema drift or ≥3 failures. P3 = 1-2 statistical failures.

## Profiler Column Metrics (per column, all types)

- `null_rate`, `distinct_count`, `cardinality_ratio`
- **Numeric:** min, max, mean, stddev, p25, p50, p75, p95, zero_rate, negative_rate
- **Timestamp/Date:** min, max, range_seconds
- **Text:** min_len, max_len, avg_len, empty_rate

---

## Auth Pattern

Two auth modes, both supported on all protected routes:

- **`x-api-key` header** — for programmatic/Celery use. Raw key prefixed `dw_`, bcrypt-hashed in DB.
- **`Authorization: Bearer <jwt>`** — for the SPA. 15-min JWT, login via `POST /auth/login`.

Dependency: `get_current_org_from_jwt` or `get_current_org_from_api_key` in `app/routers/auth.py`.

---

## Key Non-Obvious Design Decisions

1. **Single aggregate SQL query per profile run** — never row-by-row. All COUNT/AVG/STDDEV computed in one `SELECT`. See `app/services/profiler.py`.
2. **HKDF per-org Fernet keys** — `HKDF(master_key, salt=org_id)` so cross-org decryption is impossible even if master key leaks. See `app/services/crypto.py`.
3. **APScheduler MemoryJobStore + DB crash recovery** — simpler than SQLAlchemyJobStore, avoids async/sync mismatch. On restart, tables overdue by >2× interval get immediate enqueue.
4. **Celery tasks are sync with `asyncio.run()` wrappers** — keeps all service code async-native, no separate sync SQLAlchemy engine needed.
5. **LLM narration fires AFTER alert dispatch is queued** — generate_llm_narration → send_alerts chain ensures Slack messages include the AI summary.
6. **IsoForest model cached in Redis (7-day TTL)** — avoids retraining on every profile run (O(n²) on large history).
7. **Incident deduplication is per-table** — one open incident per table. Repeat failures append to `fired_checks` JSONB rather than creating new incidents.
8. **`status=paused` on source DELETE** — preserves all profile history for trend charts and rapport metrics.

---

## Plan Limits

```python
PLAN_LIMITS = {
    "free":       {"sources": 1,  "tables": 5,   "retention_days": 7},
    "starter":    {"sources": 3,  "tables": 50,  "retention_days": 90},
    "growth":     {"sources": -1, "tables": -1,  "retention_days": 365},
    "enterprise": {"sources": -1, "tables": -1,  "retention_days": -1},
}
```
Returns HTTP 402 with `{"error": "plan_limit_exceeded", "upgrade_url": ...}` on breach.

---

## Environment Variables

| Var | Description | Required |
|---|---|---|
| `SECRET_KEY` | JWT signing (32-byte hex) | ✅ |
| `FERNET_MASTER_KEY` | Credential encryption master key | ✅ |
| `DATABASE_URL` | `postgresql+asyncpg://...` | ✅ |
| `REDIS_URL` | `redis://...` | ✅ |
| `BASE_DOMAIN` | Root domain (default: `datawatch.io`) | Optional |
| `ADMIN_SUBDOMAIN` | Admin portal subdomain (default: `admin`) | Optional |
| `STAFF_EMAIL` | Seed staff email (default: `admin@datawatch.io`) | Optional |
| `STAFF_PASSWORD` | Seed staff password — **set this to enable seeding** | Optional |
| `STAFF_FULL_NAME` | Seed staff name | Optional |
| `OPENROUTER_API_KEY` | Global LLM fallback key (per-org keys override via admin portal) | Optional |
| `LLM_MODEL` | Default model ID | Optional |
| `LLM_BASE_URL` | LLM API base URL (default: OpenRouter) | Optional |
| `SENDGRID_API_KEY` | Email alerts | Optional |
| `FROM_EMAIL` | Alert sender | Optional |
| `ENVIRONMENT` | `development` or `production` | Optional |

Generate keys:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## Commit Rules

See `docs/development.md` for full conventions. Short version:

- **Format:** `type(scope): message` — e.g. `feat(anomaly): add STL seasonal check`
- **Types:** `feat` | `fix` | `refactor` | `test` | `docs` | `chore`
- **Scopes:** `api` | `frontend` | `anomaly` | `profiler` | `llm` | `alerts` | `auth` | `db` | `infra` | `tests`
- **Rule:** Never commit with failing tests. Run `pytest tests/test_anomaly.py tests/test_llm.py` (no DB needed) before every commit.
- **Rule:** After any non-trivial change, update Linear ticket state and log to Notion. See `docs/tracking.md`.

---

## Linear Project

URL: https://linear.app/mounir-gaiby/project/datawatch-77f9ab167670
Team: Mounir Gaiby | Identifier prefix: `MOU-`

| Ticket | Topic | Status |
|---|---|---|
| MOU-5 | Day 1 — Docker, DB, Auth | ✅ Done |
| MOU-6 | Day 2 — Connectors & Schema Discovery | ✅ Done |
| MOU-7 | Day 3 — Table Profiling Engine | ✅ Done |
| MOU-8 | Day 4 — Anomaly Detection + Incidents | ✅ Done |
| MOU-9 | Day 5 — LLM Narration + Alerting | ✅ Done |
| MOU-10 | Day 6 — APScheduler + React Frontend | ✅ Done |
| MOU-11 | Day 7 — Railway Deploy + Demo Seed | ✅ Done |
| MOU-12 | Multi-tenancy + Plan Enforcement | ✅ Done |
| MOU-13 | LLM Prompt Engineering | ✅ Done |
| MOU-14 | E2E Integration Tests | ✅ Done |

**Rule:** Move ticket to In Progress when starting, Done when complete. Never leave a ticket in Backlog while actively working on it.

---

## Notion Workspace

Hub: https://app.notion.com/p/374cb96c4e1c81af9989e9fafb3e2f7a

| Page | URL | What goes there |
|---|---|---|
| 7-Day Build Log | https://app.notion.com/p/374cb96c4e1c813686f6c77c3612bcea | Daily Done/Decisions/Problems/Numbers |
| Rapport Material | https://app.notion.com/p/374cb96c4e1c8126853bc980cbde78e6 | Decisions log, perf measurements, ML observations, LLM prompt iterations |
| Architecture | https://app.notion.com/p/374cb96c4e1c818b9c54dd576d209d9c | System design, ADRs |
| Demo Script | https://app.notion.com/p/374cb96c4e1c81c6911bf6040b81cef1 | Jury demo runbook |
| Academic Defense | https://app.notion.com/p/374cb96c4e1c8120a8f8c5ebffa5fa79 | Defense angles, talking points |

**Rule:** Every significant decision, bug, measurement, or ML observation must be logged to Notion. This is the source material for the written rapport.

---

## Recommended Skills (Claude Code)

When working on this project with Claude Code, these skills are relevant:

- `engineering:debug` — when a task chain breaks or a test fails unexpectedly
- `engineering:code-review` — before merging any anomaly detection or auth change
- `engineering:testing-strategy` — when adding a new detection method or connector
- `engineering:architecture` — when making structural decisions (new connector, new check type)
- `product-tracking-skills:product-tracking-instrument-new-feature` — when shipping a new feature that needs Notion/rapport documentation

---

## Auth Architecture

**Client login flow:**
1. User visits `{slug}.datawatch.io` → Login page pre-fills workspace from hostname
2. POST `/auth/login` with `{email, password, org_slug}` → returns JWT + org_slug + user_role
3. JWT carries `{sub: user_id, org_id, org_slug, type: "user"}`
4. All protected routes validated via `get_current_org_from_jwt` dependency

**Staff login flow:**
1. Staff visits `admin.datawatch.io/login` → AdminLogin page
2. POST `/auth/staff/login` with `{email, password}` → returns staff JWT
3. JWT carries `{sub: staff_id, email, type: "staff"}`
4. Admin routes validated via `get_current_staff` dependency

**API keys:** Staff-only via `POST /admin/orgs/{id}/api-key`. Not client-manageable.

## Current State

The project is in **MVP SaaS state**. Completed milestones:

1. **Subdomain-first multi-tenancy** — `localhost` = landing, `slug.localhost` = workspace, `admin.localhost` = admin (env-configured subdomain, never guessable)
2. **13 database connectors** — PostgreSQL, MySQL, MongoDB (Tier 1), + ClickHouse, Redshift, BigQuery, Snowflake, SQL Server, Cassandra, Databricks, Trino, DuckDB, SQLite
3. **7 anomaly detection methods** — Z-Score, Isolation Forest, STL Seasonal, Cardinality Drop, Row Growth Rate, Rule-Based, **Enum/Category Drift** (new)
4. **Staff admin portal** — org management, plan control, per-org LLM key (set by staff only), staff CRUD
5. **Reports system** — weekly reliability report, per-incident report, health score (0–100 weighted)
6. **AI features** — incident explanations, monitor recommender, natural language → SQL rule builder
7. **Frontend** — Overview, Tables, Monitors, Incidents, Incident Detail, Reports, Settings (with Billing + Team placeholders)
8. **Security** — HKDF per-org Fernet keys, login never reveals workspace existence, admin subdomain env-only

**To run locally:**

1. `cp .env.example .env` — fill in `SECRET_KEY`, `FERNET_MASTER_KEY`, `STAFF_PASSWORD`
2. Add to `.env`: `ADMIN_SUBDOMAIN=admin` (or any secret string)
3. Add to `frontend/.env.local`: `VITE_ADMIN_SUBDOMAIN=admin`
4. `docker-compose up -d postgres redis`
5. `cd backend && venv/bin/alembic upgrade head`
6. `venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000` (with all env vars set)
7. `cd frontend && npm install && npm run dev`
8. `python scripts/seed_demo.py --full`
9. **Workspace**: `http://acme-corp.localhost:5173` → `mounir@acme.io` / `demo1234`
10. **Landing**: `http://localhost:5173`
11. **Admin**: `http://admin.localhost:5173` → `admin@datawatch.io` / `admin1234`
12. Tests: `cd backend && pytest tests/test_anomaly.py tests/test_llm.py -v`

**What's next:**
- Stripe billing (placeholder UI in Settings → Billing)
- Team invites backend (placeholder UI in Settings → Team)
- Webhook + MS Teams alert channels
- PDF report export
- NL rule builder UI in table detail
- SSO / SAML
- CI/CD pipeline

→ See `docs/development.md` for full local setup.
→ See `docs/deployment.md` for Railway deploy.
→ See `docs/tracking.md` for Notion/Linear update rules.
