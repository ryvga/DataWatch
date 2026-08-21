# SQL connector conformance evidence — 2026-08-21

## Purpose

This record supports MOU-18 and the PFE report with executable connection → discovery →
schema → profile → typed-monitor evidence for MySQL, MariaDB, SQLite, and SQL Server. It
records a small deterministic regression baseline; it does not claim production capacity.

## Implementation under test

- Commit: `c8eb0ec18fba79cfdbed84ca72fd3c365f6cad2a`
- MySQL 8.4 and MariaDB 11.4 use separate required services and the shared MySQL-family
  adapter.
- SQL Server 2022 uses Microsoft ODBC Driver 18 from the same Python 3.12 API image used by
  the application. The local self-signed database lane explicitly disables TLS; production
  configuration defaults to certificate and hostname verification.
- SQLite uses a temporary file opened through the connector's read-only URI path.

## Security and capability contract

All four engines compile schema-bound monitor definitions to one deterministic aggregate
`SELECT`, bind literal values through the driver, enforce a conservative complete-storage
scan bound, require exactly one result row with the declared aliases, and roll back after
execution. MySQL/MariaDB start a database read-only transaction. SQL Server checks the
target object's effective permissions and rejects principals with write capability. Both
network adapters cancel timed-out work; SQL Server also discards the cancelled connection.

Core profiles intentionally omit unsupported percentile metrics. Snapshot tests verify
that MySQL and T-SQL queries contain their native aggregate/freshness expressions and do
not contain `PERCENTILE_CONT`. Unsupported connectors remain fail-closed at planning or
execution rather than silently substituting a different metric.

## Verification performed

| Proof | Result |
|---|---:|
| Focused compiler/runtime/dialect/API/connector contracts | 99 passed; live SQL Server lane deselected in this host process |
| MySQL 8.4 + MariaDB 11.4 real-driver verticals | 2 passed |
| SQL Server 2022 + ODBC Driver 18 real-driver vertical | 1 passed |
| Ruff on application, tests, and benchmark harness | Passed |

Hosted CI [run 32483412747](https://github.com/ryvga/DataWatch/actions/runs/32483412747)
passed at head `320966c`: **294 backend tests, 0 skipped** on Python 3.12.14 with all
required connector services, Ruff, scoped mypy, frontend build/audit, and all three
deterministic seeded Playwright flows.

## Timing method

The reproducible harness is `backend/scripts/benchmark_sql_connectors.py`. It ran inside
the API container on Python 3.12.14 against the Compose test services. Each provider used
one warm-up followed by 20 sequential `ProfilerService.profile` calls on the same open
connector. Every source contained the same three-row, four-column `orders` table and a
`created_at` freshness field. Durations are wall-clock `time.perf_counter` observations;
p95 uses the nearest-rank sample.

Host context: Apple M5, 16 GiB RAM, arm64, macOS 26.5, Docker engine 29.1.3. SQL Server's
`linux/amd64` image ran under emulation, so cross-provider timing comparisons should not
be interpreted as database rankings.

| Connector | Runs | p50 | p95 | Min | Max |
|---|---:|---:|---:|---:|---:|
| MySQL 8.4 | 20 | 0.32 ms | 0.53 ms | 0.28 ms | 0.96 ms |
| MariaDB 11.4 | 20 | 0.40 ms | 0.64 ms | 0.30 ms | 1.09 ms |
| SQLite | 20 | 0.19 ms | 0.25 ms | 0.17 ms | 0.28 ms |
| SQL Server 2022 | 20 | 0.74 ms | 1.35 ms | 0.55 ms | 1.49 ms |

Reproduction from the repository root after the test services are healthy:

```bash
docker compose exec -T \
  -e SQLSERVER_TEST_HOST=test-sqlserver \
  -e SQLSERVER_TEST_PORT=1433 \
  api python -m scripts.benchmark_sql_connectors \
  --runs 20 --include-sqlserver
```

## Interpretation and limitations

The results show that the warmed tiny-table profile path is deterministic and inexpensive
enough for regression detection on this machine. They do not measure cold connection
setup, concurrent workers, 10k/100k/1m-row tables, wide schemas, WAN latency, trusted-chain
TLS handshakes, query-plan variance, or sustained throughput. They are not an SLA.

Before promoting these connectors beyond experimental/beta, add API → worker → persisted
profile verticals, a trusted-certificate SQL Server lane, and controlled scale benchmarks
with repeated cold/warm trials and confidence intervals. The exact observations used here
are available in `sql-connector-conformance-2026-08-21.json`.
