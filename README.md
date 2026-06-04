# DataWatch

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
│  profile_table  │    │  9 tables, indexes   │
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

| Warehouse  | Status   |
|------------|----------|
| PostgreSQL | ✅ Full  |
| BigQuery   | ✅ Full  |
| DuckDB     | ✅ Full (local/demo) |
| Snowflake  | 🚧 Stub (501) |

## Quick Start (local)

**Prerequisites:** Docker, Docker Compose

```bash
# 1. Clone
git clone <repo-url> && cd DataWatch

# 2. Configure
cp .env.example .env
# Edit .env — set SECRET_KEY, FERNET_MASTER_KEY, OPENROUTER_API_KEY

# 3. Start stack
docker-compose up -d

# 4. Run migrations
docker-compose exec api alembic upgrade head

# 5. Seed demo data (optional)
export DATABASE_URL=postgresql://datawatch:datawatch@localhost:5432/datawatch
python scripts/seed_demo.py --clean

# 6. Register org + get API key
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"org_name":"Demo","org_slug":"demo","email":"admin@demo.com","password":"secret"}'
```

Frontend: http://localhost:3000 (run `cd frontend && npm install && npm run dev`)
API docs: http://localhost:8000/docs

## Demo Walkthrough

```bash
# Seed 90 days of e-commerce data
export DATABASE_URL=postgresql://datawatch:datawatch@localhost:5432/datawatch
export DATAWATCH_API_URL=http://localhost:8000
export DATAWATCH_API_KEY=dw_<your-key>

python scripts/seed_demo.py --clean    # creates demo.orders/users/products
python scripts/seed_demo.py --history  # injects 90-day profile history

# In the UI:
# 1. Settings → Data Sources → Add (type: postgres, host: postgres, db: datawatch)
# 2. Settings → Tables → Add demo.orders (freshness_column: created_at)
# 3. Overview → should show healthy

# Inject anomaly
python scripts/seed_demo.py --scenario pipeline_failure

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
| GET | `/api/v1/sources` | JWT | List data sources |
| POST | `/api/v1/sources` | JWT | Register new source |
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

```bash
# Install Railway CLI
npm install -g @railway/cli && railway login

# Create project
railway init

# Add plugins: Postgres + Redis via Railway dashboard

# Deploy
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

## Incident Severity

| Condition | Severity |
|-----------|----------|
| row_count = 0 OR freshness SLA breach | P1 |
| schema drift OR ≥3 checks fail | P2 |
| 1–2 statistical failures | P3 |
