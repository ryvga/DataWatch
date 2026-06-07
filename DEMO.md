# Panopta — Demo Runbook

---

## Quick Start

```bash
# 1. Start everything — migrations run automatically before api/worker start
docker compose up -d

# 2. Seed demo data (run once, or after --reset to wipe and re-seed)
python scripts/seed_demo.py --full

# 3. Open the app
open http://acme-corp.localhost:5173
```

> **Hot-reload dev mode** (live reload for api/frontend):
> ```bash
> docker compose up -d postgres redis mailhog demo-db analytics-db
> docker compose run --rm migrate
> cd backend && venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
> # (separate terminal)
> cd backend && venv/bin/celery -A app.worker worker --loglevel=info --pool=threads --concurrency=4
> # (separate terminal)
> cd frontend && npm run dev
> ```

---

## Credentials

### Workspace Users

| Workspace | URL | Email | Password | Role | Plan |
|---|---|---|---|---|---|
| **Acme Corp** | http://acme-corp.localhost:5173 | mounir@acme.io | demo1234 | owner | Growth |
| — | — | alice@acme.io | demo1234 | admin | — |
| — | — | bob@acme.io | demo1234 | member | — |
| **Startup.io** | http://startup-io.localhost:5173 | dev@startup.io | demo1234 | owner | Growth |
| — | — | carol@startup.io | demo1234 | member | — |
| **Retail Demo** | http://retail-demo.localhost:5173 | admin@retail.demo | demo1234 | owner | Starter |

### Staff / Admin

| Portal | URL | Email | Password |
|---|---|---|---|
| **Staff Admin** | http://admin.localhost:5173 | admin@datawatch.io | admin1234 |

> **Note:** Staff password is set via `STAFF_PASSWORD` env var. Default in dev: `admin1234`.

### Database Access (direct)

| Service | Host | Port | Database | User | Password |
|---|---|---|---|---|---|
| Main (DataWatch) | localhost | 5433 | datawatch | datawatch | datawatch |
| Demo DB (acme e-commerce) | localhost | 5434 | shopDemo | readonly_user | readonly_pass |
| Analytics DB (startup SaaS) | localhost | 5435 | analyticsdb | analytics_ro | readonly_pass |

---

## What Gets Seeded

Running `python scripts/seed_demo.py --full` creates:

- **3 organizations** (acme-corp/growth, startup-io/growth, retail-demo/starter) with plan enforcement
- **Multiple users per org** — owner + admin + member (see credentials above)
- **1 staff admin account** — admin@datawatch.io
- **Data sources** pointing to the demo Docker containers
- **Monitored tables** with realistic column schemas
- **60–360 historical profile snapshots** per table (6-hour and 12-hour cadence)
- **Teams** with colored avatars, members, and on-call schedules
- **Incident assignments** — P1s assigned to teams; some assigned to specific users
- **Table ownership** — each monitored table assigned to a team
- **User notification preferences** — per-user toggles (notify on assign, team incidents, status changes, daily digest)
- **Anomaly check results** on current profiles
- **AI-generated LLM narration** on P1/P2 incidents
- **Alert configs** (email routes)

---

## Incident Scenarios (what to show)

### acme-corp — E-commerce workspace

| Severity | Table | Incident | Status |
|---|---|---|---|
| **P1** | `orders` | `payment_status` null rate spiked from 0.8% to 18.4% (~9,200 rows affected) | Open |
| **P2** | `users` | Email uniqueness dropped 99.5% to 95.2% (duplicate emails inserted) | Open |
| **P3** | `orders` | Freshness warning — 3.2h since last update, expected <1h | Open |

The P1 incident has a full AI narration: summary, likely causes with probability ratings, impact assessment, recommended actions, and debug SQL queries ready to copy.

### startup-io — SaaS analytics workspace

| Severity | Table | Incident | Status |
|---|---|---|---|
| **P1** | `events` | `user_id` null rate spiked (tracking pipeline broken) | Open |
| **P2** | `sessions` | Row count dropped to near-zero | Open |
| **P2** | `sessions` | Schema drift detected | Open |
| **P3** | `api_logs` | Row count dropped ~40% | Open |

### retail-demo — Retail workspace

| Severity | Table | Incident | Status |
|---|---|---|---|
| **P1** | `payments` | Null spike detected | Open |
| **P2** | `inventory` | Schema drift | Open |
| **P2** | `users` | Email cardinality drop | Open |

---

## Demo Walkthrough (jury script)

### Step 1 — Landing page (30s)

Open http://localhost:5173

- Show the hero section: "100 eyes on your data"
- Show the Panoptes mythology section (name origin story)
- Show the FAQ section and footer links (Privacy, Terms, HelpCenter)

### Step 2 — Login (30s)

- Enter workspace: `acme-corp` → click Go
- Login with `mounir@acme.io` / `demo1234`
- Point out: the subdomain (`acme-corp.localhost`) is set automatically — this is subdomain-first multi-tenancy. Each customer gets their own isolated workspace at `{slug}.datawatch.io`.

### Step 3 — Dashboard / Overview (1m)

- Show the Overview page: health score badge, open incident count, recent profile activity
- Point out the P1 badge — immediately visible that something critical needs attention
- Explain: health score is 0–100 weighted across all checks in the last 24h. A drop here triggers alert routing.

### Step 4 — Incidents (2m)

- Open the Incidents page
- Show the P1 `orders.payment_status` incident at the top
- Open the incident detail:
  - Show the AI narration panel: summary, likely causes with probability ratings, impact assessment, recommended actions, debug SQL
  - Explain: this narration is generated by an LLM (via OpenRouter API) using profile metrics and check results as context — fires automatically on P1/P2 incidents via a Celery task
- Show the severity badge, fired checks timeline, deviation scores

### Step 5 — Tables (1m)

- Open the Tables page
- Click on the `orders` table
- Show the profile history chart — row count trend over 90 days of seeded history
- Show the column metrics panel — the `payment_status` null rate visible spiking in the latest snapshot
- Explain: DataWatch runs a single SQL aggregate query per profile run (one `SELECT` per table — never row-by-row), then stores column metrics as JSONB in PostgreSQL

### Step 6 — Teams (1m)

- Open the **Teams** page
- Show the "Data Engineering" team (blue badge) with its members
- Click into the team → show the **Members tab** (alice + bob with their roles)
- Show the **On-call tab** — current on-call user highlighted, upcoming schedule visible
- Show the **Assigned Incidents tab** — P1 incidents routed to this team
- Back on Incidents → open the P1 detail → show the **Assignment card** in the sidebar
  - Assignee picker + Team picker — demonstrate live assignment
  - Explain: teams are routing/ownership units (open visibility model — all org members see all data, teams are for assignment + notification, not access control)

### Step 7 — Settings (1m)

- Open Settings → **Notifications**: show 4 per-user toggles (assigned to me, team incidents, status changes, daily digest with hour picker)
- Open Settings → **Alerts**: show alert channel configuration (email, Slack, PagerDuty), plan gating
- Open Settings → **Billing**: show plan entitlements card (sources, tables, retention days)
- Explain the plan model: free / starter / growth / enterprise — hard limits enforced at the API layer (HTTP 402 on breach, with `upgrade_url` in the response)

### Step 9 — Staff Portal (1m)

- Open http://admin.localhost:5173
- Login: `admin@datawatch.io` / `admin1234`
- Show the organization list with plan badges (acme-corp: growth, retail-demo: starter)
- Show plan management: how staff can upgrade or downgrade an org
- Show per-org LLM key management — staff set the OpenRouter API key per org; organizations never touch it
- Explain: the staff portal lives at a secret subdomain set in env (`ADMIN_SUBDOMAIN=admin`) — not discoverable from the public domain

### Step 10 — Public pages (30s)

- Open http://localhost:5173/about — About page
- Open http://localhost:5173/help — 3-panel HelpCenter with search
- Show Privacy and Terms links in footer
- These exist to demonstrate the product feels production-complete, not a prototype

---

## Service URLs

| Service | URL | Purpose |
|---|---|---|
| Acme Corp workspace | http://acme-corp.localhost:5173 | Primary demo workspace |
| Startup.io workspace | http://startup-io.localhost:5173 | Secondary demo workspace |
| Landing page | http://localhost:5173 | Marketing + workspace picker |
| Staff portal | http://admin.localhost:5173 | Admin panel |
| API (FastAPI) | http://localhost:8000 | Backend API |
| API docs (Swagger) | http://localhost:8000/docs | Interactive API reference |
| MailHog (email preview) | http://localhost:8025 | View sent alert emails in dev |

---

## Useful Commands

```bash
# View logs
docker compose logs -f api
docker compose logs -f worker

# Re-seed (wipe demo orgs + re-run full seed)
python scripts/seed_demo.py --reset

# Check what's seeded (counts by severity/status)
python scripts/seed_demo.py --status

# Run tests (no DB required)
cd backend && venv/bin/pytest tests/test_anomaly.py tests/test_llm.py -v

# Run migrations manually
cd backend && venv/bin/alembic upgrade head

# Connect to main DB
psql postgresql://datawatch:datawatch@localhost:5433/datawatch

# Connect to demo DB (acme e-commerce)
psql postgresql://readonly_user:readonly_pass@localhost:5434/shopDemo

# Connect to analytics DB (startup SaaS)
psql postgresql://analytics_ro:readonly_pass@localhost:5435/analyticsdb

# Rebuild a service after code changes
docker compose build api && docker compose up -d api
docker compose build worker && docker compose up -d worker
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Workspace not found / login fails | Check `.env` has `ADMIN_SUBDOMAIN=admin`. Check `frontend/.env.local` has `VITE_ADMIN_SUBDOMAIN=admin`. |
| Staff login fails during seed | Ensure `STAFF_PASSWORD=admin1234` is in `.env` |
| Email alerts not arriving | Check MailHog at http://localhost:8025 — SMTP listens on port 1025 |
| Worker not processing tasks | `docker compose logs worker` — check Celery can reach Redis |
| Seed fails with import error | Run from the project root with the venv active: `venv/bin/python scripts/seed_demo.py --full` |
| Profile history missing | Seed ran but `--full` flag was omitted. Run `python scripts/seed_demo.py --reset` to wipe and re-seed. |
| Migration errors | May need: `cd backend && venv/bin/alembic downgrade base && venv/bin/alembic upgrade head` |

---

## Architecture Summary (oral defense bullet points)

- **Backend:** Python 3.12, FastAPI (async), SQLAlchemy 2.0 async, Alembic migrations
- **Task queue:** Celery + Redis — task chain: profile → anomaly → LLM narration → alerts
- **Scheduler:** APScheduler embedded in FastAPI lifespan — one job per monitored table, crash-recovery on restart (tables overdue by >2x interval get immediate re-profile)
- **Database:** PostgreSQL 16 — JSONB for column metrics, narration, fired checks
- **Anomaly detection:** 7 methods — Z-Score, Isolation Forest (Redis-cached model, 7-day TTL), STL Seasonal, Cardinality Drop, Row Growth Rate, Rule-Based, Enum/Category Drift
- **LLM narration:** OpenRouter API — per-org key (staff-managed), global fallback via env var. Fires on P1/P2 incidents automatically.
- **Security:** HKDF per-org Fernet keys for credential encryption (cross-org decryption impossible even if master key leaks). JWT (15-min) + API key auth. Admin subdomain is env-only, never guessable.
- **Multi-tenancy:** Subdomain-first — `{slug}.datawatch.io`. Login always requires `org_slug`. Plan limits enforced at API layer (HTTP 402 with `upgrade_url`).
- **Connectors:** 13 database types — PostgreSQL, MySQL, MongoDB, ClickHouse, BigQuery, Snowflake, Redshift, SQL Server, Cassandra, Databricks, Trino, DuckDB, SQLite
- **Frontend:** React 18, Vite, Tailwind CSS, Recharts — SPA with subdomain routing
- **Dev infra:** Docker Compose — 3 PostgreSQL containers (main + 2 demo databases), Redis, MailHog
- **Production:** Railway deploy (`railway.toml`), prod multi-stage Dockerfiles (non-root), `docker-compose.prod.yml`
