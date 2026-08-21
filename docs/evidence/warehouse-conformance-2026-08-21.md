# Warehouse Connector Conformance — 2026-08-21

## Purpose and claim boundary

This record supports MOU-16 and the PFE report with reproducible evidence for BigQuery,
Snowflake, Redshift, ClickHouse, Databricks SQL, and Trino/Presto. It proves connector
contracts and native core-profile planners. It does **not** claim that every managed
provider was exercised with production credentials on this date.

## Implemented contract

| Provider | Deterministic contract | Execution evidence | Remaining promotion gate |
|---|---|---|---|
| BigQuery | Blocking SDK calls use `asyncio.to_thread`; optional dataset scope; dry run before execution; configured `maximum_bytes_billed`; bounded result wait and cancellation; Standard SQL core planner | Fake-client tests cover below-budget execution, over-budget refusal, timeout cancellation, scope, DDL quoting, cleanup, invalid bounds, and SQL snapshot | Secret-backed run with measured processed/billed bytes; nested RECORD metrics |
| Snowflake | Official connector dependency; SDK thread boundary; configured database/schema/warehouse; login/network/socket/statement timeouts; query tag; scoped discovery; bound schema filters; quoted DDL; core planner | Fake-driver vertical covers connect arguments, discovery, DDL, profile row, cleanup, scope rejection, invalid timeout, and secret-free errors | Secret-backed run with measured credits; key-pair/SSO authentication |
| Redshift | Driver keyword arguments rather than a composed DSN; optional schema scope; bound catalogue filters; quoted DDL; dedicated core planner | Async fake-driver discovery/schema/profile contract and adversarial identifier snapshot | Secret-backed RA3/serverless run; database-enforced profile read-only and scan/cost proof |
| ClickHouse | Configured-database discovery; bound system-catalog parameters; quoted DDL; dedicated planner; profile query settings `readonly=2` and `max_execution_time=120` | Real ClickHouse container creates and profiles a two-row table; fake-client tests verify settings and bindings | Verified TLS and controlled scale/cost measurements |
| Databricks SQL | Synchronous driver offloaded; configured catalog/schema at connection; bound catalogue/schema/table filters; quoted DDL; dedicated Spark SQL planner | Fake-driver vertical and adversarial catalogue payload prove values are not interpolated into SQL | Secret-backed SQL Warehouse run; explicit cancellation/cost policy |
| Trino / Presto | Synchronous driver offloaded; configured catalogue/schema; bound schema/table filters; quoted DDL; dedicated Trino planner | Real Trino memory-catalog container creates and profiles a two-row table; fake-driver binding tests | Production TLS/auth/catalog matrix and federated cost policy |

All six planners emit one aggregate `SELECT` for row count, freshness, null/distinct/
uniqueness ratios, numeric min/max/mean/deviation/rates, timestamp range, and text-length/
empty-rate metrics. Core planners deliberately omit percentile claims where a portable,
verified implementation is not yet available.

## Generated capability matrix

The public API no longer reads manually duplicated capability dictionaries from the
connector registry. `derive_connector_capabilities()` reflects executable method
overrides plus declared profile/monitor dialects. The deterministic generator writes
`docs/evidence/connector-capabilities.generated.json`; a test fails if that artifact is
stale or if a registry entry reintroduces a hand-maintained capability claim.

Generation and verification:

```bash
backend/venv/bin/python backend/scripts/generate_connector_capabilities.py
backend/venv/bin/python backend/scripts/generate_connector_capabilities.py --check
```

## Reproducible test protocol

Credential-free contract suite:

```bash
backend/venv/bin/python -m pytest -q \
  backend/tests/test_bigquery_connector.py \
  backend/tests/test_snowflake_connector.py \
  backend/tests/test_warehouse_dialects.py \
  backend/tests/test_connector_capability_generation.py \
  backend/tests/test_sources_api.py
```

Real open-source warehouse lane:

```bash
docker compose -f docker-compose.test-dbs.yml up -d --wait test-clickhouse test-trino
RUN_WAREHOUSE_CONTAINER_TESTS=1 backend/venv/bin/python -m pytest -q \
  backend/tests/test_warehouse_dialects.py -k container_vertical
```

Managed-provider lane (one example):

```bash
BIGQUERY_SMOKE_CONFIG='{"project_id":"...","dataset":"...","maximum_bytes_billed":1073741824}' \
BIGQUERY_SMOKE_SCHEMA='dataset_name' BIGQUERY_SMOKE_TABLE='small_table' \
backend/venv/bin/python backend/scripts/smoke_managed_warehouse.py \
  --type bigquery --config-env BIGQUERY_SMOKE_CONFIG \
  --schema-env BIGQUERY_SMOKE_SCHEMA --table-env BIGQUERY_SMOKE_TABLE
```

Equivalent secret-gated CI steps exist for Snowflake, Redshift, and Databricks. An absent
secret leaves the relevant step visibly skipped; it is never reported as a successful
managed-provider execution.

## Hosted evidence

[GitHub Actions run 32493957341](https://github.com/ryvga/DataWatch/actions/runs/32493957341)
is green on Python 3.12 at commit `e7ed984`:

- backend: Ruff and scoped mypy passed; **349 passed, 2 skipped in 46.13 s**. The two
  skips are exactly the ClickHouse/Trino container tests delegated to their isolated job,
  not unavailable dependencies hidden by the main suite;
- warehouse containers: **2 passed in 4.38 s** against ClickHouse 25.7 and Trino 476;
- frontend: **2,917 modules** built and the production dependency audit found **0
  vulnerabilities**;
- full-stack browser: all three deterministic flows passed with empty console, page, and
  failed-request diagnostics;
- managed warehouse job: completed successfully, with BigQuery/Snowflake/Redshift/
  Databricks steps visibly skipped because repository credentials were absent. Therefore
  this run is evidence that the credential gates work, not evidence of live managed-cloud
  execution.

## Security and cost observations

- BigQuery refuses execution when its dry-run estimate exceeds the configured ceiling;
  the execution job independently receives the same maximum billed-byte limit.
- Snowflake receives explicit SDK/session timeouts and a Panopta query tag. Logged
  connection failures contain exception class names, not driver messages or secrets.
- Databricks and Trino catalogue filters are parameters. Adversarial strings remain
  values and never become executable SQL.
- ClickHouse profile execution is server-declared read-only and time-bounded.
- The remaining managed-provider cost statements are design guarantees, not measured
  billing claims. Credit/slot/DBU consumption must be captured with real credentials.

## PFE report mapping

Suggested use in the French report:

- **Analyse et conception**: capability-based connector architecture and the distinction
  between connection, discovery, schema, profile, and monitor capabilities.
- **Réalisation**: async boundary pattern, native dialect strategy, generated matrix, and
  provider-specific cost controls.
- **Sécurité**: bound catalogue values, quoted identifiers, secret-safe errors, scopes,
  read-only execution, timeouts, and BigQuery byte ceilings.
- **Validation**: fake-driver mutation/edge tests, real ClickHouse/Trino containers, full
  hosted Python 3.12 suite, frontend build/audit, and deterministic browser checks.
- **Limites et perspectives**: managed credentials, production TLS/auth variants,
  persisted API-to-worker warehouse verticals, controlled scale, and measured cloud cost.

The defensible conclusion is: *Panopta implements and continuously checks six explicit
warehouse profile dialects, with real-engine validation for reproducible open-source
providers and transparent credential gates for managed providers.* It is not defensible
to claim universal production certification or zero cloud cost without the pending live
measurements.
