# DataWatch — Deployment Guide

## Production Docker (local or VPS)

```bash
# Build + start production stack
cp .env.example .env
# Fill in all required vars (see CLAUDE.md env var table)

docker-compose -f docker-compose.prod.yml up -d

# Run migrations
docker-compose -f docker-compose.prod.yml exec api alembic upgrade head

# Seed demo data
export DATABASE_URL=postgresql://datawatch:<password>@localhost:5432/datawatch
export DATAWATCH_API_URL=http://localhost:8000
export DATAWATCH_API_KEY=dw_<your-key>
python scripts/seed_demo.py --clean
python scripts/seed_demo.py --history
```

---

## Railway Deploy

Railway hosts 4 services: Postgres plugin, Redis plugin, API service, Worker service.

### Step 1 — Create Railway project

```bash
npm install -g @railway/cli
railway login
railway init    # creates new project
```

### Step 2 — Add plugins (via Railway dashboard)

In the Railway dashboard for your project:
1. Click **+ New** → **Database** → **PostgreSQL** — Railway provisions it and injects `DATABASE_URL`
2. Click **+ New** → **Database** → **Redis** — injects `REDIS_URL`

### Step 3 — Deploy API service

```bash
# From the DataWatch root:
railway up --service api
```

Or connect GitHub repo in Railway dashboard for auto-deploy on push.

Railway uses `railway.toml` which points at `backend/Dockerfile.api`.

The API start command runs migrations before starting uvicorn:
```
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

### Step 4 — Deploy Worker service

```bash
railway up --service worker
```

Uses `backend/Dockerfile.worker`. CMD is `celery -A app.worker worker`.

To also run the beat scheduler (for daily cleanup):
```bash
# Either: run beat in the worker container
celery -A app.worker worker --beat --loglevel=info

# Or: deploy a separate beat service
# CMD: celery -A app.worker beat --loglevel=info
```

### Step 5 — Set environment variables

In Railway dashboard → your service → Variables:

```
SECRET_KEY=<generate with openssl rand -hex 32>
FERNET_MASTER_KEY=<generate with python Fernet.generate_key()>
OPENROUTER_API_KEY=sk-or-v1-...
LLM_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free
SENDGRID_API_KEY=SG....
FROM_EMAIL=alerts@yourdomain.com
ENVIRONMENT=production
LOG_LEVEL=INFO
```

`DATABASE_URL` and `REDIS_URL` are auto-injected by Railway plugins.

### Step 6 — Run migrations

```bash
railway run --service api alembic upgrade head
```

### Step 7 — Deploy frontend

Option A — Deploy frontend as a separate Railway service:
```bash
railway up --service frontend
# Uses frontend/Dockerfile (npm build → nginx)
```

Option B — Mount frontend build output into the API container and serve via FastAPI static files:
```python
# In app/main.py — add after all routers:
from fastapi.staticfiles import StaticFiles
app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")
```

### Step 8 — Verify

```bash
# Health check
curl https://<railway-url>/health

# Should return:
# {"status": "ok", "db": "connected", "redis": "connected", "scheduler_jobs": 0}
```

---

## Environment Checklist

Before going live, verify:

- [ ] `SECRET_KEY` is 32+ random bytes, not the example value
- [ ] `FERNET_MASTER_KEY` is a fresh Fernet key, not the example value
- [ ] `ENVIRONMENT=production` (enables strict CORS)
- [ ] `DATABASE_URL` uses `postgresql+asyncpg://` scheme (not plain `postgresql://`)
- [ ] Alembic migrations applied: `alembic upgrade head` returns clean
- [ ] `GET /health` returns `"db": "connected"` and `"redis": "connected"`
- [ ] Test alert fires: `POST /api/v1/alerts/{id}/test`
- [ ] LLM narration works: create test incident, verify `llm_narration` populated within 30s

---

## Demo Day Checklist

Run through this the morning of the jury demo:

```bash
# 1. Verify stack is up
curl https://<url>/health

# 2. Reset demo data to clean state
export DATABASE_URL=<prod-or-local-db>
export DATAWATCH_API_URL=https://<url>
export DATAWATCH_API_KEY=dw_<key>
python scripts/seed_demo.py --clean
python scripts/seed_demo.py --history

# 3. Verify profiles in UI (Overview should show 3 healthy tables)

# 4. Test LLM narration (dry run)
python scripts/test_llm_prompt.py --fixture pipeline_failure

# 5. Test Slack alert
curl -X POST https://<url>/api/v1/alerts/<config-id>/test \
  -H "Authorization: Bearer <jwt>"

# 6. Run through demo scenario once completely:
python scripts/seed_demo.py --scenario pipeline_failure
curl -X POST https://<url>/api/v1/tables/<orders-id>/run \
  -H "x-api-key: dw_<key>"
# Wait ~30s, then open UI → verify P1 incident appears with LLM narration

# 7. Reset again before the real demo
python scripts/seed_demo.py --clean && python scripts/seed_demo.py --history
```

---

## Rollback

If a deploy breaks production:

```bash
# Railway — roll back to previous deploy
railway rollback --service api
railway rollback --service worker

# If DB migration broke things:
railway run --service api alembic downgrade -1
```

---

## Monitoring (post-PFE)

When DataWatch is real SaaS:
- Set up a `/metrics` endpoint with Prometheus counters for profile runs, anomaly counts, LLM latency
- Add Sentry for error tracking: `pip install sentry-sdk[fastapi]`
- Railway provides basic CPU/memory graphs — sufficient for PFE demo
