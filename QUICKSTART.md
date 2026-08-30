# DataWatch — Local Quick Start

## Start and verify

```bash
cp .env.example .env
docker compose up -d --wait
docker compose --profile seed run --rm --entrypoint python seed /scripts/quickstart.py --reset
curl -fsS http://localhost:8000/ready
```

`ready` must report both PostgreSQL and Redis as connected before opening the workspace.

## Seeded workspaces

| Workspace | URL | Login | Plan | Purpose |
| --- | --- | --- | --- | --- |
| Acme Corp | http://acme-corp.localhost:5173 | `mounir@acme.io` / `demo1234` | Growth | Primary e-commerce incident demo |
| Startup.io | http://startup-io.localhost:5173 | `dev@startup.io` / `demo1234` | Growth | Secondary analytics workspace |
| Staff portal | http://admin.localhost:5173 | `admin@datawatch.io` / `admin1234` | Staff | Organization and plan administration |

The Acme seed includes four monitored PostgreSQL tables, profile history, injected data-quality anomalies, an email alert route delivered to MailHog, and AI-governance fixtures. Use [DEMO.md](DEMO.md) for the recording sequence.

## Useful local URLs

| Service | URL |
| --- | --- |
| Landing page | http://localhost:5173 |
| API health | http://localhost:8000/health |
| API documentation | http://localhost:8000/docs |
| Email preview | http://localhost:8025 |

## Reset the presentation state

```bash
docker compose --profile seed run --rm --entrypoint python seed /scripts/quickstart.py --reset
```

Run this before a demo take. It resets the demo workspaces and preserves the running stack.

## Validate the project

```bash
cd frontend && npm run build && npm run test:e2e
cd ../backend && REQUIRE_TEST_SERVICES=1 venv/bin/python -m pytest -q tests
```

The strict backend run requires the PostgreSQL, Redis, and connector test services described in `.github/workflows/ci.yml`.
