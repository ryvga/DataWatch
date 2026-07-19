# Safe Monitor DSL Specification

Status: Validation, draft persistence, immutable revision history, and preview attestations implemented; compiler/activation draft (`datawatch.io/v1alpha1`)

Tracking: Linear MOU-15 (parent), MOU-19 (runtime)
Implementation plan: Notion “DataWatch Connector & Safe Monitor DSL Overhaul”

## Current implementation

`POST /api/v2/monitors/validate` accepts strict JSON definitions for `metric` and
`violations` measurements. It rejects unknown fields, versions, predicate shapes,
duplicate IDs, unknown references, non-finite/complex literals, oversized values,
excessive predicate depth/node counts, and cross-measurement references inside violation
predicates. The response contains canonical JSON, a stable SHA-256 definition hash,
structural statistics, tenant-owned asset resolution, and a truthful capability plan.

Draft creation and compare-and-swap revision APIs persist canonical definitions in an
append-only revision table. Preview returns a five-minute HMAC attestation bound to the
organization, asset, definition hash, latest schema fingerprint, and planner version.
Revision history and the run audit collection are readable through tenant-scoped APIs.

Execution remains deliberately disabled: `activationSupported=false` and
`dsl_compiler_not_implemented` stay explicit until typed dialect compilers and the run
orchestrator are implemented. The run table exists for that audit trail but no DSL runs
are created yet.

## Purpose

The DSL lets customers express monitoring intent without executing Python, JavaScript,
arbitrary database functions, or user-authored query plans. YAML is an authoring format;
DataWatch validates it and stores canonical JSON plus a definition hash.

Legacy custom SQL remains a separately labelled advanced escape hatch during migration.
It is restricted by AST validation, single-asset scope, read-only connector execution,
timeouts, and an exact scalar result contract, but it is still not equivalent to the
typed DSL and must not be described as a general-purpose security sandbox.

## Example

```yaml
apiVersion: datawatch.io/v1alpha1
kind: Monitor
metadata:
  name: paid-orders-require-reference
  labels:
    team: payments
spec:
  target:
    assetId: 8efef403-4c5d-4930-a2dd-f289c16f41a9
  trigger:
    type: on_profile
  measurements:
    - id: invalid_orders
      type: violations
      violationWhen:
        all:
          - op: eq
            left: {field: status}
            right: {literal: paid}
          - op: is_null
            value: {field: payment_reference}
      output: [count, rate]
  breachWhen:
    op: gt
    left: {ref: invalid_orders.rate}
    right: {literal: 0.01}
  policy:
    severity: P2
    consecutiveBreaches: 2
    recoveryPasses: 2
    cooldownMinutes: 60
    notifyOnExecutionError: true
  execution:
    timeoutSeconds: 30
    maxBytesScanned: 1000000000
    maxDocumentsScanned: 1000000
    sampling: {mode: auto}
```

## Grammar

Top-level fields are exactly `apiVersion`, `kind`, `metadata`, and `spec`. Unknown fields
are rejected at every level.

Measurement types:

- `metric`: row count, null count/rate, distinct count/rate, min, max, mean, stddev,
  sum, percentile, duplicate count, freshness seconds, document count, key count, TTL,
  and connector-approved metadata metrics.
- `violations`: a typed predicate tree producing count and/or rate.
- `schema`: added, removed, type-changed, required, and forbidden field rules.
- `comparison`: absolute or relative difference between two typed measurements.
- `metadata`: source-native metrics that do not require a data scan.

Predicate nodes are limited to `all`, `any`, `not`, comparison operators, `between`,
set membership, null/missing/NaN/zero/negative checks, bounded text matching, and safe
transforms (`lower`, `upper`, `trim`, `length`, `abs`, `date`, `date_trunc`, `coalesce`).
Values are only `{field}`, `{literal}`, or `{ref}`. Free-form expression strings are not
part of the grammar.

Algorithms are selected from a versioned registry: fixed threshold, relative change,
z-score, robust z-score, IQR, EWMA, CUSUM, STL, Mann-Kendall, and Isolation Forest.
Algorithm evaluation is deterministic application code over persisted measurements.

## Validation and Planning

1. Structural validation uses strict discriminated models with bounded strings, lists,
   numeric ranges, definition size (64 KiB), predicate nodes (100), depth (10),
   measurements (20), signals (10), and regex length (256).
2. Semantic validation resolves an org-owned asset, fields, types, references, and cycles.
3. Capability planning compares the monitor with the source capability contract. An
   incompatible monitor fails before activation with `CAPABILITY_NOT_SUPPORTED`.
4. Compilation creates a typed internal plan. SQL compilers parameterize literals and
   quote identifiers. MongoDB compilers emit only allowlisted read stages. Cassandra
   planners require complete partition-key bounds for row scans. Redis planners use a
   bounded `SCAN`, never arbitrary commands or Lua.
5. Preview returns a short-lived attestation over tenant, asset, definition hash, schema
   fingerprint, and compiler version. Edits invalidate the attestation.

## Execution Security

- Use least-privilege, database-enforced read-only credentials.
- Enforce server-side statement timeout/cancellation and per-org concurrency/rate limits.
- Enforce source-appropriate scan/cost budgets (including BigQuery maximum bytes billed).
- Tag queries with monitor/run IDs for auditability.
- Restrict a monitor to its declared asset unless it is a typed comparison monitor.
- Accept exactly the typed result contract. Empty, multi-row, multi-column, string,
  boolean, NaN, or infinite scalar output is an execution error, never a pass.
- Persist execution errors and never auto-resolve an incident from an error result.
- Forbid imports, loops, recursion, file/network access, `eval`, `exec`, database UDFs,
  and user-supplied Mongo stages such as `$out`, `$merge`, `$function`, and `$where`.

## Persistence and API

`monitors` stores stable identity and current mutable lifecycle state. Every accepted edit
creates a new `monitor_revisions` row containing canonical `definition`,
`definition_version`, `definition_hash`, revision number, validation status, and the
schema fingerprint observed during validation. The application exposes no revision
mutation or deletion path. `monitor_runs` is the append-only execution audit schema with
tenant-scoped idempotency; the compiler/runtime will populate it in the next phase.

Implemented endpoints:

- `POST /api/v2/monitors/validate`
- `POST /api/v2/monitors/preview`
- `POST /api/v2/assets/{id}/monitors`
- `GET /api/v2/assets/{id}/monitors`
- `GET /api/v2/monitors/{id}`
- `PUT /api/v2/monitors/{id}` with optimistic revision
- `GET /api/v2/monitors/{id}/revisions`
- `GET /api/v2/monitors/{id}/revisions/{revision}`
- `GET /api/v2/monitors/{id}/runs`
- `POST /api/v2/monitors/{id}/activate` verifies preview context, then returns the
  explicit compiler-not-implemented guard

Planned endpoints and formats:

- `POST /api/v2/monitors/{id}/run`
- `GET /api/v2/connectors/{type}/monitor-capabilities`
- YAML import/export with canonical JSON responses

## Legacy Migration

Simple `COUNT(*) ... WHERE ...` checks may be translated only when an AST parser proves
they map to a typed violation predicate. Other definitions become `legacy_sql`, run under
read-only/time/result controls, and require review. Cross-object and side-effect-function
definitions are disabled. Cost budgets remain required before legacy SQL can be enabled
on cloud warehouses. Existing IDs and history are preserved. The LLM recommendation layer
must return DSL JSON, never executable SQL.

## Acceptance Tests

- Grammar rejects unknown versions, kinds, fields, aliases/tags, duplicate YAML keys,
  oversize definitions, cycles, excessive depth, and unsafe regex.
- Injection-shaped literals remain parameters; malicious identifiers remain identifiers.
- Every SQL dialect has compiler snapshots and a container-backed conformance case.
- Mongo plans cannot contain write/code stages; Cassandra requires partition bounds;
  Redis respects key scan budgets.
- Empty/malformed scalar results are errors.
- Timeouts cancel server-side and leave workers healthy.
- Duplicate task delivery is idempotent.
- Monitor rename does not change incident identity or recovery.
- End-to-end profile → batched measurements → incident → narration → alert → recovery.
- One hundred compatible monitors are batched into a bounded query and measured.

## Public Product Inspiration

DataWatch may reproduce publicly documented product capabilities, not proprietary code,
copy, or branding. Useful references include Monte Carlo Monitors as Code and validation
monitor categories, MongoDB aggregation-stage safety documentation, PostgreSQL read-only
transactions, and BigQuery cost controls. The initial parity order is typed validation and
metrics, scheduling/noise policies, schema/comparison rules, then lineage-aware impact and
query-performance monitoring.
