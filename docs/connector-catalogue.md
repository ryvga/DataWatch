# Connector Catalogue Completion Contract

DataWatch treats a connector as a product vertical, not a driver import. A catalogue card
may be visible before completion, but its readiness and machine-readable capabilities must
describe only paths backed by executable evidence.

## Target catalogue

| Category | Provider | Target role | Current state | Next completion gate |
|---|---|---|---|---|
| Relational | PostgreSQL / Aurora | Reference operational database | Stable/full, but safety re-audit found unbounded discovery counts and incomplete profile execution budgets | Replace discovery scans with catalogue estimates; verified-identity TLS and read-only statement-timeout profile envelope; persisted live profile test |
| Relational | MySQL | Tier-1 operational database | Experimental/core; required MySQL 8.4 lane and database-read-only typed monitor execution | Add API/worker-persisted live profile proof and percentile capability |
| Relational | MariaDB | Tier-1 operational database | Experimental/core; required MariaDB 11.4 LTS lane sharing the MySQL-family read-only monitor adapter | Add API/worker-persisted live profile proof and percentile capability |
| Relational | SQL Server / Azure SQL | Enterprise operational database | Experimental/core; required SQL Server 2022 lane, packaged ODBC Driver 18, read-only-principal typed monitor execution | Add trusted-certificate live TLS and API/worker-persisted profile proofs; add percentile capability |
| Relational | Oracle | Enterprise operational database | Experimental/core: async thin driver, verified TLS/wallet configuration, bounded connection and call timeouts, exact owner scope, catalogue estimates, deterministic quoted schema, Oracle-native one-query read-only profile, failure cancellation/discard, mocked driver contracts, API/worker persistence, optional Oracle Free lane | Run the opt-in Oracle Free job to record real-engine evidence; add verified TLS/wallet and controlled scale measurements plus typed monitor execution |
| Embedded SQL | SQLite | Application/local source | Beta/core | Restrict hosted paths to a managed allowlist/upload boundary and add persisted API profile test |
| Document | MongoDB | Tier-1 document source | Experimental bounded sampled profile plus immutable typed aggregation monitors; required real Mongo lane and incident recovery vertical | Add trusted-certificate live TLS, repeated-sample drift confirmation, scale evidence, filter/distinct/string-pattern semantics |
| Wide-column | Cassandra | Partition-scoped source | Experimental scoped discovery/schema plus manual immutable monitors with complete partition bindings, prepared statements, a hard row ceiling, required Cassandra 5 lane, and incident recovery proof | Add scheduled native profiling, trusted-certificate TLS, Cassandra 4 compatibility, controlled scale, and Astra bundles |
| Key/value and streams | Redis | TTL/stream health source | Experimental bounded native profile plus immutable metadata-only monitor plans; configured pattern fingerprint, key ceiling, Redis 7 real lane, mutation/ACL failures, and incident recovery are proven | Add trusted-certificate TLS, Redis 8 compatibility, concurrent-mutation characterization, and controlled scale |
| Cloud warehouse | BigQuery | Serverless warehouse | Experimental async/scoped/core profile with dry-run estimate, maximum billed bytes, timeout cancellation, and mocked driver conformance | Run secret-backed smoke with billed-byte evidence; add nested RECORD metrics and persisted API/worker proof |
| Cloud warehouse | Snowflake | Proprietary warehouse | Experimental official-driver connection, scoped discovery/schema, core profile, thread boundary, login/network/socket/statement timeouts, query tag, and mocked cleanup/error conformance | Run secret-backed smoke with measured credits; add key-pair/SSO auth and persisted API/worker proof |
| Cloud warehouse | Redshift | Managed PostgreSQL-compatible warehouse | Experimental optionally scoped discovery/schema and native core profile; DSN fields are driver kwargs | Run secret-backed profile smoke and prove read-only/statement-cost envelope against RA3/serverless |
| Open-source warehouse | ClickHouse | Networked open-source warehouse | Experimental configured-database discovery, safe schema, read-only/time-bounded native core profile, and required real-container vertical | Add verified TLS, controlled scale/cost evidence, and persisted API/worker proof |
| Lakehouse warehouse | Databricks SQL | Managed lakehouse | Experimental async-offloaded discovery/schema/core profile with bound catalogue filters | Run secret-backed SQL Warehouse smoke; add cancellation/cost controls and persisted API/worker proof |
| Federated query engine | Trino / Presto | Multi-catalog query engine | Experimental scoped/bound discovery/schema, native core profile, and required real Trino memory-catalog vertical | Add TLS/auth/catalog matrix, federated cost policy, and persisted API/worker proof |
| Embedded analytics | DuckDB | Managed local analytical file | Beta/full | Move blocking calls off the event loop and enforce the same hosted file boundary as SQLite |

ClickHouse and Trino have reproducible real-engine lanes. Oracle Database Free has an
explicit opt-in Compose profile and manual GitHub Actions job because its image is about
1.2 GB; its mocked and API/worker tests remain required in the ordinary backend suite.
BigQuery, Snowflake, Redshift, and Databricks use deterministic fake-driver tests plus explicit secret-backed smoke steps;
those managed smokes do not claim execution when repository credentials are absent.

## Readiness gates

A connector cannot move beyond experimental until all applicable gates pass:

1. Secure transport verifies server identity by default; insecure local mode is explicit.
2. Connection, discovery, schema, profile, freshness, cleanup, and stable secret-free errors
   are tested through the real driver.
3. Discovery is tenant-scoped and does not scan every asset for row counts.
4. Schema snapshots are deterministic, safely quote adversarial identifiers, and return
   native field names when the driver exposes them.
5. Profiling is connector-native, cost-bounded, timed, read-only where supported, and
   persists exact/estimated/sampled provenance.
6. Freshness configuration is verified for field existence, compatible type, and any
   source-specific index/partition requirement.
7. An API-level test creates a source, discovers an asset, onboards it, runs the worker
   path, and retrieves the persisted profile.
8. Open-source engines have required container lanes. Proprietary services have mocked
   driver contracts plus an opt-in secret-backed live lane.
9. Runtime dependencies exist in API and worker images.
10. README, architecture, development guidance, Linear, and Notion match the evidence.

## Delivery sequence

1. Add API/worker persistence and trusted-certificate lanes to the completed
   connector-level MySQL/MariaDB/SQLite/SQL Server conformance slice.
2. Repair the PostgreSQL reference safety envelope found by the catalogue audit.
3. Add persisted API/worker and production-grade TLS/cost proofs to the completed
   connector-level warehouse planners and real ClickHouse/Trino lanes.
4. Extend the completed Redis metadata-monitor slice with trusted TLS, Redis 8 and
   controlled mutation/scale evidence.
5. Execute and archive the completed Oracle optional real-engine lane, then add live
   verified-TLS/wallet and controlled-scale evidence.
6. Extend Cassandra from the completed manual partition-monitor slice to scheduled native
   profiling, then harden hosted DuckDB/SQLite file access.

This order prioritizes reusable safety contracts and executable verticals over adding
unverified provider badges.
