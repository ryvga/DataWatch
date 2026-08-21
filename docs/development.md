# DataWatch — Development Guide

## Local Setup

### Prerequisites
- Docker + Docker Compose
- Python 3.12
- Node 20

### First-time setup

```bash
# 1. Clone and enter project
git clone <repo> && cd DataWatch

# 2. Create .env
cp .env.example .env
# Edit .env — minimum required:
#   SECRET_KEY=<openssl rand -hex 32>
#   FERNET_MASTER_KEY=<python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
#   DATABASE_URL=postgresql+asyncpg://datawatch:datawatch@postgres:5432/datawatch
#   REDIS_URL=redis://redis:6379/0

# 3. Start infrastructure
docker-compose up -d

# 4. Run migrations
docker-compose exec api alembic upgrade head

# 5. Register your first org
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"org_name":"Dev","org_slug":"dev","email":"dev@dev.com","password":"devpass"}'
# Save the api_key from the response

# 6. Start frontend (separate terminal)
cd frontend && npm install && npm run dev
# → http://localhost:5173
```

### Running without Docker (API only)

```bash
cd backend
pip install -r requirements.txt

# Override DATABASE_URL to point at a local postgres
export DATABASE_URL=postgresql+asyncpg://localhost/datawatch
export REDIS_URL=redis://localhost:6379/0
export SECRET_KEY=dev-secret-key-not-for-production
export FERNET_MASTER_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

---

## Day-to-Day Workflow

### Starting a work session

1. `git pull` — sync with latest
2. Check Linear for the next ticket: https://linear.app/mounir-gaiby/project/datawatch-77f9ab167670
3. Move ticket to **In Progress** in Linear
4. Create a branch: `git checkout -b feat/mou-XX-short-description`
5. Open Notion 7-Day Build Log and note what you're starting

### Ending a work session

1. Run tests: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://datawatch:datawatch@localhost:5433/datawatch_test ./venv/bin/pytest -q`
2. Commit with correct format (see below)
3. Move Linear ticket to **Done**
4. Update Notion Build Log entry: Done / Decisions / Problems / Numbers

---

## Commit Convention

Format: `type(scope): imperative description`

```
feat(anomaly): add STL seasonal decomposition for row_count
fix(profiler): handle NULL freshness_column gracefully
refactor(llm): extract context assembly to llm_context.py
test(e2e): add auto-resolve scenario
docs(arch): document IsoForest cache TTL decision
chore(deps): bump anthropic to 0.29.0
```

**Types:**
- `feat` — new functionality
- `fix` — bug fix
- `refactor` — restructuring without behavior change
- `test` — adding or fixing tests
- `docs` — documentation only
- `chore` — deps, config, tooling

**Scopes:**
`api` | `frontend` | `anomaly` | `profiler` | `llm` | `alerts` | `auth` | `db` | `infra` | `tests` | `scheduler` | `connectors`

**Rules:**
- One scope per commit — if you touch two scopes, make two commits
- Never `git commit -m "wip"` or `git commit -m "fix"`
- Body is optional but encouraged for non-obvious changes
- Reference Linear ticket: `Closes MOU-8` in body when applicable

---

## Code Conventions

### Python

**Async everywhere.** All DB operations use `AsyncSession`. All connectors are async. Celery tasks use `asyncio.run()` wrappers — do not introduce sync SQLAlchemy.

**No naked `except`.** Always catch specific exceptions or at minimum log before swallowing:
```python
# BAD
try:
    result = await connector.test_connection()
except:
    return False

# GOOD
try:
    result = await connector.test_connection()
except Exception as e:
    logger.warning("Connection test failed: %s", type(e).__name__)
    return False
```

**Credentials never in logs.** If you add a new connector, make sure the DSN/password is never passed to `logger.*`. Use `type(e).__name__` not `str(e)` when logging connector errors.
Public API and persisted profile errors must also use `services/error_safety.py`; driver
messages may contain hosts, query text, or credentials.

Run the optional connector services with `docker compose -f docker-compose.test-dbs.yml
up -d`. MySQL listens on test-only port 3307, MariaDB 11.4 LTS on 3308, and MongoDB on
27018; connector integration tests skip explicitly when those services are unavailable.
For release/CI validation, set `REQUIRE_TEST_SERVICES=1`; an unavailable
PostgreSQL, MySQL-family, or MongoDB service then fails the test run instead of
being reported as a green skip.
Oracle Database Free is deliberately outside the ordinary connector matrix because the
image is about 1.2 GB. Run its exact vertical locally with:

```bash
docker compose -f docker-compose.test-dbs.yml --profile oracle up -d --wait test-oracle
RUN_ORACLE_CONTAINER_TESTS=1 backend/venv/bin/python -m pytest -q \
  backend/tests/test_oracle_connector.py -k database_free_container_vertical
docker compose -f docker-compose.test-dbs.yml --profile oracle down
```

The GitHub Actions `workflow_dispatch` input `run_oracle=true` runs the same test with
`gvenzl/setup-oracle-free@v1`. Oracle production connections default to TCPS identity
verification. Thin wallets must contain `ewallet.pem`, be mounted read-only, and resolve
under `ORACLE_WALLET_ROOT`; `tls_mode=disabled` is limited to the isolated local lane.
The MySQL-family tests pass
`tls_mode=disabled` because that isolated container has no certificate; application
connections default to certificate and hostname verification and accept an optional
`ssl_ca` PEM bundle.
The local MongoDB service likewise requires explicit `tls_mode=disabled`; remote MongoDB
connections default to verified TLS. MongoDB uses PyMongo `AsyncMongoClient` (not Motor),
requires one configured database, bounds `profile_sample_size` to 25–1,000, and never persists
sample values. Sampling additionally caps each returned document at 128 KiB, total sampled
document memory at 8 MiB, arrays at 100 inspected items, nesting at eight levels, and fields
at 500. Sampled document metrics currently drive indexed freshness only; repeated-sample
confirmation is required before enabling drift algorithms. Cassandra remote connections
also require verified TLS by default and pass an explicit `tls_server_name` (defaulting to
the first contact point) to the driver. Keep all caller-provided aggregation pipelines and
CQL outside connector execution paths until typed native planners exist.

**Org isolation is mandatory.** Every query on `data_sources`, `monitored_tables`, `monitors`, `monitor_runs`, `incidents`, `check_results`, and `alert_configs` must include or derive a verified `org_id` filter. Return 404 (not 403) when not found — don't leak existence.

**Pydantic response models strip secrets.** If you add a new endpoint returning a `DataSource`, use `DataSourceResponse` (no `connection_config`). Never filter in the handler — use Pydantic model exclusion.

**Service layer is pure logic.** Routers handle HTTP, services handle business logic. No `HTTPException` in service files — raise domain exceptions that routers translate.

### SQL / Migrations

- Always create a new Alembic migration for schema changes: `alembic revision -m "describe_change"`
- Never modify existing migration files — create a new one
- Index every FK column and every column used in `.where()` filters
- JSONB columns: `postgresql.JSONB` from `sqlalchemy.dialects.postgresql`
- Monitor definition edits append `monitor_revisions`; never update or delete a stored
  revision through application code. Use `expectedRevision` when advancing a monitor.
- Set `active_revision_id` and `status = 'active'` atomically; database ownership and
  lifecycle constraints reject active monitors without an owned immutable revision.
- DSL executions must persist an idempotent `monitor_runs` audit row tied to the exact
  revision before activation can be enabled.
- Claim runs through `monitor_run_service`; commit the claim before connector I/O, execute
  outside a database transaction, and finalize only with the current lease token. Never
  mutate or retry a terminal run.
- Breach and policy evaluation must use the pure `monitor_evaluator`; never coerce missing,
  null, boolean, string, NaN, or infinite measurement values into a passing observation.
- Safe monitor SQL is built only from programmatic SQLGlot AST nodes. Keep SQLGlot pinned
  while snapshots depend on its renderer; never interpolate a user literal or parse a
  user-authored fragment in the typed compiler. API plans remain preview-only; internal
  execution must use the tested connector-specific named-parameter adapter and the
  fail-closed `monitor_runtime` result contract, never a generic query method.
- Compilers require a `RelationBinding` from the connector DDL snapshot. Resolve fields
  by exact name, reject missing fields and incompatible logical types, and bind plans to
  the latest schema fingerprint. Never infer compatibility from a field name alone.

### React / Frontend

- All API calls go through `src/api/endpoints.js` — no inline `axios.get` in components
- Dark theme only — use Tailwind's `gray-*` palette, never hardcode colors
- `@apply` in `index.css` for repeated patterns (`.card`, `.btn-primary`, etc.)
- Error states must be handled — no silent failures on API calls
- Loading states for all async data

---

## Testing

### AI governance phase-one proof

```bash
# API, tenancy, manifest replay, CAS, control semantics, incident dedupe
cd backend
venv/bin/pytest -q tests/test_ai_governance_phase1.py

# Full backend regression
venv/bin/pytest -q tests

# Inventory/detail browser flow (requires the seeded local stack)
cd ../frontend
node tests/playwright/ai-governance.spec.mjs

# Prove the real Alembic chain on a disposable database
docker exec datawatch-postgres-1 createdb -U datawatch datawatch_aigov_migration_test
(cd backend && \
  DATABASE_URL=postgresql+asyncpg://datawatch:datawatch@localhost:5433/datawatch_aigov_migration_test \
  venv/bin/alembic upgrade head)
docker exec datawatch-postgres-1 dropdb -U datawatch datawatch_aigov_migration_test
```

`scripts/quickstart.py` seeds four clearly marked jury fixtures: stale knowledge,
unauthorized effective role, missing embedding, and failed deletion propagation. Fixture
evidence includes `fixture: true`; do not present it as an independently observed production
fact. Use `POST /api/v1/ai/deployments/{id}/evaluate` for connector-backed evidence.
The Compose source credentials (`readonly_user`, `analytics_ro`) are intentionally
different from the bootstrap owners (`acme_admin`, `analytics_admin`) and must remain
`NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE`, `NOINHERIT`, and table-`SELECT` only.

### Unit tests (no DB, fast)

```bash
cd backend
pytest tests/test_anomaly.py tests/test_llm.py -v
# ~5 seconds, no external dependencies
```

Run these before every commit.

### E2E tests (requires postgres test DB)

```bash
# Create test DB once when using the Docker dev Postgres:
docker compose exec -T postgres createdb -U datawatch datawatch_test

export TEST_DATABASE_URL=postgresql+asyncpg://datawatch:datawatch@localhost:5433/datawatch_test
cd backend && ./venv/bin/pytest tests/test_e2e.py -v
```

### Connector matrix suite

Use this when validating SQL, NoSQL, and warehouse-style sources through the public API:

```bash
docker compose -f docker-compose.yml -f docker-compose.test-dbs.yml up -d test-mongo
python scripts/run_connector_matrix.py
```

The MongoDB container seeds itself from `scripts/test_dbs/mongo_seed.js` on first start. The matrix covers demo PostgreSQL, analytics warehouse PostgreSQL, MongoDB preview/create/discover/schema flows, and custom monitor create/run/delete on the demo analytics table.

### Frontend browser tests

```bash
cd frontend
npm run build
npm run test:e2e
```

### CI release gate

`.github/workflows/ci.yml` runs the backend suite on Python 3.12 with PostgreSQL,
Redis, MySQL 8.4, MariaDB 11.4, and MongoDB services, plus the frontend build
and a high-severity dependency audit. It sets `REQUIRE_TEST_SERVICES=1`, so a
missing integration service fails the job instead of silently producing skips.

### LLM prompt testing

```bash
# Fixture-based (no DB, no API key needed for token count):
python scripts/test_llm_prompt.py --fixture pipeline_failure

# With OpenRouter API key (full round-trip):
export OPENROUTER_API_KEY=sk-or-v1-...
python scripts/test_llm_prompt.py --fixture pipeline_failure

# Against a real incident in DB:
python scripts/test_llm_prompt.py --incident-id <uuid>
```

### Test rules

- LLM calls must be mocked in all automated tests — `patch("app.services.llm.generate_narration")`
- External HTTP calls (Slack, PagerDuty) must be mocked — `patch("app.services.alert.send_slack_alert")`
- Use `tests/conftest.py` fixtures — don't create orgs/tables inline in test functions
- Tests use `datawatch_test` DB, never `datawatch` (dev) DB
- DB-backed tests recreate metadata per test because API routes commit through the real dependency

---

## Adding a New Connector

1. Create `app/connectors/<name>.py` implementing the applicable `BaseConnector` methods
2. Add the registry entry, readiness, and truthful capability metadata in `factory.py`
3. Implement and declare a profile dialect only when its generated query has a direct execution test
4. Add connection/discovery/schema tests plus a real discover → profile vertical slice
5. Add any new Python and native runtime dependencies, including container packages
6. Update the README and architecture capability matrices
7. Keep unsupported operations explicit; never silently return an empty successful profile

Connector conformance tests must cover quoted identifiers, cleanup, failure behavior,
and any source-specific cost/scan limit. A registry entry by itself is not feature
completion.

The profiler's one-query invariant includes cost discovery: do not add a preliminary
exact `COUNT(*)` to decide whether to sample. Sampling requires a connector-native
non-scanning estimate, explicit persisted provenance, and anomaly semantics tested
against the true row-count contract.

`custom_monitors=legacy_sql_scalar` requires a separate `execute_monitor_query` path,
database-enforced read-only access where supported, driver and application timeouts,
zero/multi-row detection, and the attack corpus in `test_legacy_sql_monitor.py`. Do not
advertise this capability by reusing the general profile query method.

---

## Adding a New Detection Method

1. Add a `run_<method>_checks(profile, history, table)` function to `app/services/anomaly.py`
2. Return `list[AnomalyResult]`
3. Call it inside `_run_anomaly_checks_async()` in `app/tasks.py`
4. Write unit tests in `tests/test_anomaly.py`
5. Log to Notion → Rapport Material → ML Observations with: what it detects, threshold chosen, any surprising behavior

---

## Migrations Workflow

```bash
# After changing a model:
cd backend
alembic revision --autogenerate -m "describe_what_changed"

# Review the generated file in alembic/versions/ before applying
alembic upgrade head

# Roll back one step:
alembic downgrade -1
```

Never autogenerate and apply without reviewing the generated file. The autogenerator sometimes misses JSONB defaults or index direction.

---

## Useful Commands

```bash
# Tail API logs
docker-compose logs -f api

# Tail worker logs (see task execution)
docker-compose logs -f worker

# Connect to DB
docker-compose exec postgres psql -U datawatch -d datawatch

# Check Redis
docker-compose exec redis redis-cli

# Force-run a profile task manually
docker-compose exec api python -c "
from app.tasks import profile_table
r = profile_table.delay('<table_uuid>')
print('Task ID:', r.id)
"

# Check Celery worker status
docker-compose exec worker celery -A app.worker inspect active

# Run beat scheduler (for testing cleanup task)
docker-compose exec worker celery -A app.worker beat --loglevel=info
```
