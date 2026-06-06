# DataWatch — Quick Start & Demo Credentials

## 1. Start the stack

```bash
# First time
cp .env.example .env          # fill SECRET_KEY, FERNET_MASTER_KEY, STAFF_PASSWORD=admin1234
docker-compose up -d
cd backend && venv/bin/alembic upgrade head
python scripts/seed_demo.py --full

# Subsequent starts
docker-compose up -d
```

Frontend: `http://localhost:5173` (landing) or `http://<slug>.localhost:5173` (workspace)

---

## 2. Demo Workspaces

### 🛒 acme-corp — Agency plan (live DB, active incidents)
| Field | Value |
|---|---|
| URL | http://acme-corp.localhost:5173 |
| Email | `mounir@acme.io` |
| Password | `demo1234` |
| Plan | Agency |
| What's seeded | Live PostgreSQL source (demo-db), 4 incidents: P1 payment null spike, P2 duplicate emails, P2 negative prices, P3 freshness breach |

### 📊 startup-io — Growth plan (analytics DB, mixed incidents)
| Field | Value |
|---|---|
| URL | http://startup-io.localhost:5173 |
| Email | `dev@startup.io` |
| Password | `demo1234` |
| Plan | Growth |
| What's seeded | Analytics PostgreSQL source (analytics-db on port 5435), 4 incidents: P1 event null spike, 2× P2/P3 active, 1× P2 resolved |

### 🏪 retail-demo — Starter plan (mocked data, healthy state)
| Field | Value |
|---|---|
| URL | http://retail-demo.localhost:5173 |
| Email | `admin@retail.demo` |
| Password | `demo1234` |
| Plan | Starter |
| What's seeded | Mocked warehouse source, 3 incidents: P1 payment null, P2 schema drift, P2 email cardinality drop |

---

## 3. Staff Admin Portal

| Field | Value |
|---|---|
| URL | http://admin.localhost:5173 |
| Email | `admin@datawatch.io` |
| Password | `admin1234` |
| Access | Manage all orgs, change plans, set per-org LLM keys, manage staff accounts |

> The admin subdomain is set via `ADMIN_SUBDOMAIN=admin` in `.env`. Change it to anything — it is never guessable from the app code.

---

## 4. Demo Database Sources (read-only)

These are seeded automatically. Connection details if you need to connect manually:

| Source | Host | Port | DB | User | Password |
|---|---|---|---|---|---|
| Shop Demo DB (acme-corp) | `demo-db` (Docker) / `localhost` | 5433 | `demodb` | `demo_ro` | `readonly_pass` |
| Analytics DB (startup-io) | `analytics-db` (Docker) / `localhost` | 5435 | `analyticsdb` | `analytics_ro` | `readonly_pass` |

---

## 5. API (direct access)

Base URL: `http://localhost:8000`

```bash
# Get a JWT for acme-corp
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"mounir@acme.io","password":"demo1234","org_slug":"acme-corp"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# List sources
curl http://localhost:8000/api/v1/sources -H "Authorization: Bearer $TOKEN"

# List team members
curl http://localhost:8000/orgs/me/members -H "Authorization: Bearer $TOKEN"
```

---

## 6. Re-seed (after a clean wipe)

```bash
# Wipe all data and re-seed with fresh demo state
python scripts/seed_demo.py --clean --full
```

Flags:
- `--clean` — drop and recreate all demo orgs/sources/tables/incidents
- `--full` — seed all workspaces (default is acme-corp only)
- `--history` — generate 30 days of historical profiles (needed for IsoForest/STL/CUSUM)
- `--scenario spike` — inject a live anomaly scenario for demo purposes
