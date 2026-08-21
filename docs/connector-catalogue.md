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
| Relational | Oracle | Enterprise operational database | Planned, not implemented | `python-oracledb` thin-mode connection, discovery, deterministic schema, Oracle core dialect, live Oracle Free lane |
| Embedded SQL | SQLite | Application/local source | Beta/core | Restrict hosted paths to a managed allowlist/upload boundary and add persisted API profile test |
| Document | MongoDB | Tier-1 document source | Experimental bounded sampled core | Live verified-TLS lane, repeated-sample drift confirmation, typed document monitor DSL |
| Wide-column | Cassandra | Partition-scoped source | Experimental discovery/schema only | Required partition bindings and internally prepared, bounded native plans; Cassandra 4/5 lanes |
| Key/value and streams | Redis | TTL/stream health source | Experimental bounded native profile: `SCAN`, TTL, memory, type, Hash size, Stream length/group pending/lag; no values | Add typed immutable monitor plans, incident bridge, mutation corpus, and dedicated Redis 7/8 lanes |
| Cloud warehouse | Snowflake | Proprietary warehouse | Planned 501 stub | Official driver with bounded login/network/statement timeouts, discovery/schema, native core dialect, secret-backed nightly conformance |
| Open-source warehouse | ClickHouse | Networked open-source warehouse | Experimental discovery/schema shell | Verified TLS, query budgets, ClickHouse core profiler, container-backed persisted profile test |
| Embedded analytics | DuckDB | Managed local analytical file | Beta/full | Move blocking calls off the event loop and enforce the same hosted file boundary as SQLite |

ClickHouse is the primary open-source server warehouse paired with Snowflake. DuckDB is
kept as an embedded analytical engine, and Trino remains a federated query-engine category.

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
3. Complete ClickHouse as the open-source warehouse vertical.
4. Implement Redis native TTL/Streams monitoring without relational emulation.
5. Implement Snowflake, then Oracle, as full driver-to-persisted-profile verticals.
6. Add Cassandra partition-bound monitoring and harden hosted DuckDB/SQLite file access.

This order prioritizes reusable safety contracts and executable verticals over adding
unverified provider badges.
