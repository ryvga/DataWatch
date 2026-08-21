# Release verification baseline — 2026-08-21

## Purpose

This evidence record establishes a reproducible local baseline for MOU-21 and the PFE report. It records observed behavior, not production capacity claims.

## Environment

- Commit under measurement: `28d2653719111bfb390a845f33d58084dda56fc7`
- Application: local Docker Desktop stack
- API runtime: Python 3.12.14
- Data services: PostgreSQL 16 and Redis 7
- Seed: deterministic Acme/Startup demo workspaces from `scripts/quickstart.py`
- Measurement client: sequential requests from the host to `localhost:8000`

## Method

1. Authenticate once against the seeded `acme-corp` workspace.
2. Execute 30 sequential requests per endpoint with response bodies fully read.
3. Measure wall-clock duration with `time.perf_counter()`.
4. Report median and nearest-rank p95, plus observed minimum and maximum.
5. Read the latest persisted table profiles through the API and summarize their recorded `profiling_duration_ms` values.

No warm-up samples were discarded. These measurements include local networking and serialization, but not WAN latency. They are suitable for regression comparison on the same environment; they are not a production SLA.

## Results

| Operation | Samples | p50 | p95 | Min | Max |
|---|---:|---:|---:|---:|---:|
| Liveness `/health` | 30 | 2.40 ms | 2.72 ms | 2.02 ms | 2.97 ms |
| Readiness `/ready` | 30 | 2.33 ms | 2.55 ms | 1.85 ms | 2.98 ms |
| List sources | 30 | 2.28 ms | 2.59 ms | 1.94 ms | 2.61 ms |
| List monitored tables | 30 | 3.89 ms | 4.30 ms | 3.63 ms | 4.91 ms |
| List incidents | 30 | 3.49 ms | 3.91 ms | 3.27 ms | 4.27 ms |
| Compute organization health | 30 | 129.05 ms | 144.27 ms | 88.05 ms | 237.96 ms |
| Persisted profile execution | 120 | 49 ms | 410 ms | 20 ms | 574 ms |

## Interpretation

- CRUD/list endpoints remain below 5 ms at p95 in the seeded local environment.
- Organization health is the most expensive synchronous read path because it aggregates multiple reliability dimensions; its p95 is 144.27 ms locally.
- Persisted profiling has a wide distribution (49 ms median, 410 ms p95), consistent with different table widths, row counts, and connector work.
- Readiness adds no material latency relative to liveness while preventing traffic and seed jobs from reaching an API with unavailable dependencies.

## Verification results

- Backend strict matrix: 270 passed, integration services required.
- Frontend production build: passed (2,917 modules).
- Browser release suite: three flows passed with zero console, page, or request diagnostics.
- Alembic: one head at migration 013.

## Limitations and next measurements

- This run does not measure concurrency, sustained throughput, production network latency, LLM token/cost behavior, or detector precision/recall.
- The persisted profile sample combines several seeded tables; future studies must stratify by connector, row count, and schema width.
- Production claims require a controlled 10k/100k/1m-row benchmark with repeated cold/warm runs and confidence intervals.
- LLM and alert latency need a deterministic provider fixture plus a separate real-provider cost study with secrets and payloads excluded from artifacts.

The machine-readable observations are stored in `docs/evidence/release-baseline-2026-08-21.json`.
