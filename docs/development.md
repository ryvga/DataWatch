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
# → http://localhost:3000
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

1. Run tests: `cd backend && pytest tests/test_anomaly.py tests/test_llm.py -v`
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

**Org isolation is mandatory.** Every query on `data_sources`, `monitored_tables`, `incidents`, `check_results`, `alert_configs` must include an `org_id` filter. Return 404 (not 403) when not found — don't leak existence.

**Pydantic response models strip secrets.** If you add a new endpoint returning a `DataSource`, use `DataSourceResponse` (no `connection_config`). Never filter in the handler — use Pydantic model exclusion.

**Service layer is pure logic.** Routers handle HTTP, services handle business logic. No `HTTPException` in service files — raise domain exceptions that routers translate.

### SQL / Migrations

- Always create a new Alembic migration for schema changes: `alembic revision -m "describe_change"`
- Never modify existing migration files — create a new one
- Index every FK column and every column used in `.where()` filters
- JSONB columns: `postgresql.JSONB` from `sqlalchemy.dialects.postgresql`

### React / Frontend

- All API calls go through `src/api/endpoints.js` — no inline `axios.get` in components
- Dark theme only — use Tailwind's `gray-*` palette, never hardcode colors
- `@apply` in `index.css` for repeated patterns (`.card`, `.btn-primary`, etc.)
- Error states must be handled — no silent failures on API calls
- Loading states for all async data

---

## Testing

### Unit tests (no DB, fast)

```bash
cd backend
pytest tests/test_anomaly.py tests/test_llm.py -v
# ~5 seconds, no external dependencies
```

Run these before every commit.

### E2E tests (requires postgres test DB)

```bash
# Create test DB first:
psql -U postgres -c "CREATE DATABASE datawatch_test;"

export TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost/datawatch_test
cd backend && pytest tests/test_e2e.py -v
```

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
- Each test gets a rolled-back transaction — no cleanup needed

---

## Adding a New Connector

1. Create `app/connectors/<name>.py` implementing all 4 `BaseConnector` methods
2. Add the case to `ConnectorFactory` in `app/connectors/factory.py`
3. Add the type string to `valid_types` set in `app/routers/sources.py`
4. Add any new Python deps to `requirements.txt` as `# <connector_name> connector`
5. Update `README.md` connector table
6. Update `docs/architecture.md` connector table

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
