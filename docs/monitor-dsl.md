# Safe Monitor DSL Specification

Status: Validation, immutable revisions, schema-bound previews, attestations, internal relational execution, evaluation, persisted run state machine, activation, profile scheduling, manual runs, and incident integration implemented for PostgreSQL, DuckDB, and SQLite (`datawatch.io/v1alpha1`)

Tracking: Linear MOU-15 (parent), MOU-19 (runtime)
Implementation plan: Notion “DataWatch Connector & Safe Monitor DSL Overhaul”

## Current implementation

`POST /api/v2/monitors/validate` accepts strict JSON definitions for typed metric and
row-validation measurements. It rejects unknown fields, versions, predicate shapes,
duplicate IDs, unknown references, non-finite/complex literals, oversized values,
excessive predicate depth/node counts, and cross-measurement references inside violation
predicates. The response contains canonical JSON, a stable SHA-256 definition hash,
structural statistics, tenant-owned asset resolution, and a truthful capability plan.

Draft creation and compare-and-swap revision APIs persist canonical definitions in an
append-only revision table. Preview returns a five-minute HMAC attestation bound to the
organization, asset, definition hash, latest schema fingerprint, and planner version.
Revision history and the run audit collection are readable through tenant-scoped APIs.

Validation now distinguishes structural validity from connector compatibility. The API
parses the asset's connector DDL snapshot into a typed relation, checks field existence
and operation/type compatibility, and reports structured compiler issues. Preview emits
the deterministic plan only when compilation succeeds.

Activation is supported only when the connector capability contract advertises the
internal read-only compiled runtime. Activating a revision binds that immutable
snapshot to the table's existing profile cadence; each successful profile enqueues
typed DSL runs with the persisted idempotency/lease state machine. `POST
/api/v2/monitors/{id}/run` provides the same lifecycle for an operator-triggered
manual run and requires a client idempotency key.

The PostgreSQL, DuckDB, and SQLite parameter adapters execute one compiler-produced
read-only statement with a bounded timeout and exact result contract. A breach that
passes its policy threshold is bridged to the existing incident service using a
typed `monitor_dsl` check; recovery transitions auto-resolve the matching incident.
Execution errors remain persisted and never auto-resolve an incident.

The first pure relational compiler constructs SQLGlot AST nodes programmatically for
PostgreSQL, DuckDB, and SQLite. It emits one aggregate `SELECT`, short deterministic
output aliases, ordered named placeholders, typed parameter metadata, output bindings,
and a stable plan hash. API payloads remain preview-only. Internally,
`monitor_runtime.py` re-parses the statement as exactly one `SELECT`, verifies the
placeholder/output contract, calls a connector-specific named-parameter adapter, and
accepts only one exact row of finite numeric-or-allowed-null results.

`monitor_evaluator.py` evaluates `breachWhen` without coercion, dynamic expressions, or
side effects. It advances explicit healthy/breached policy state using consecutive breach,
recovery-pass, and cooldown rules and returns a stable decision payload. Missing outputs,
wrong types, non-finite values, unsupported output operators, corrupt prior state, and
naive timestamps fail closed. Successful and error decisions can now be finalized
atomically with persisted policy state, and breach/recovery actions bridge into the
existing typed `monitor_dsl` incident service.

The schema-bound subset includes row/null/distinct metrics; numeric min/max/mean/sum;
PostgreSQL/DuckDB stddev; timestamp/date freshness; typed equality and ordered
comparisons; field-to-field comparisons; between/membership; escaped string matching;
null/zero/negative/empty/whitespace/boolean/time checks; filtered metrics; duplicate,
non-null, text-length, and completeness/validity metrics; and nested boolean predicates.
SQLite explicitly rejects stddev. Relational `is_missing`, portable NaN semantics, and
regular-expression predicates remain fail-closed until a connector-specific contract is
available.

Planner version `datawatch-v1alpha1-relational-2` binds the compiled preview to the
latest successful profile fingerprint, or a deterministic DDL fingerprint before the
first profile. The version bump invalidates attestations created by the unbound planner.

## Authoring model (2026-08-21)

The authoring language is intentionally declarative YAML/JSON. DataWatch does **not**
accept embedded Python, JavaScript, `eval`, `exec`, user database functions, or free-form
expression strings. A Python helper may generate a definition for CI, but the server only
accepts the bounded typed document, canonicalizes it, and compiles it into an allowlisted
read-only plan.

The model follows a monitor-as-code workflow: define, compile, preview, review the target
and capability plan, then activate an immutable revision. It has four useful authoring
families even though they share one execution contract:

- **Table health:** row volume and freshness measurements tied to the existing profile
  cadence.
- **Metric quality:** null/non-null, distinct/duplicate, empty/whitespace, zero/negative,
  boolean, numeric, text-length, and filtered metrics.
- **Row validation:** bounded predicate trees for completeness, validity, and business
  rules, with count/rate outputs.
- **Operational policy:** alert or track-only mode, severity, audience, consecutive
  breach/recovery windows, cooldowns, ownership metadata, quality dimensions, and
  profile/manual triggers.

Metric measurements can include `filterWhen`, which is the safe equivalent of a `WHERE`
scope. Its fields and literals are typed against the current schema and its literals are
always bound as parameters. The filter never changes the declared target asset and cannot
reference another measurement.

`policy.mode: track` records measurements and policy state without opening or resolving
incidents. This makes it possible to observe a metric before enabling alerting. Interval
triggers, anomaly baselines, segmentation, and cross-asset comparisons remain explicit
capability-gated extensions rather than silently falling back to unsafe execution.

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

Filtered metric example (the filter is compiled into the aggregate and remains
parameterized):

```yaml
apiVersion: datawatch.io/v1alpha1
kind: Monitor
metadata:
  name: paid-order-email-completeness
  qualityDimension: completeness
spec:
  target: {assetId: 8efef403-4c5d-4930-a2dd-f289c16f41a9}
  trigger: {type: on_profile}
  measurements:
    - id: paid_email_null_rate
      type: metric
      metric: null_rate
      field: email
      filterWhen:
        op: eq
        left: {field: status}
        right: {literal: paid}
  breachWhen: {op: gt, left: {ref: paid_email_null_rate}, right: {literal: 0.01}}
  policy:
    mode: alert
    severity: P2
    audience: [payments]
```

## Grammar

Top-level fields are exactly `apiVersion`, `kind`, `metadata`, and `spec`. Unknown fields
are rejected at every level.

Measurement types currently executable by the relational v1 planner:

- `metric`: row count; null/non-null count/rate; distinct/duplicate count/rate; min, max,
  mean, stddev, sum; freshness seconds; empty-string/whitespace, zero/negative, true/false,
  and text-length metrics. Metric measurements may include a typed `filterWhen` predicate.
- `violations`: a typed predicate tree producing count and/or rate.

Schema-change, cross-asset comparison, metadata-only, distribution-baseline, and
segmented measurement families are reserved for later capability contracts; they are not
silently interpreted as relational SQL.

Predicate nodes are limited to `all`, `any`, `not`, comparison operators, `between`,
set membership, null/missing/NaN/zero/negative/empty/whitespace/boolean/time checks, and
bounded text matching. Safe transforms and regular-expression predicates are reserved
until each connector has a typed implementation.
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
mutation or deletion path. `current_revision` is the edit head; nullable
`active_revision_id` is the independently activated runtime snapshot. `monitor_runs`
stores tenant-scoped idempotency, trigger ordering, plan/definition/schema hashes, claim
leases, attempts, sanitized errors, measurements, and versioned decisions. Mutable
streak/cooldown state and the complete `(sequenceAt, idempotencyKey)` ordering cursor live
separately in `monitor_evaluation_states`. Composite ownership constraints prevent
cross-monitor audit links. PostgreSQL triggers reject revision mutation and any update or
deletion of a terminal run; terminal runs are never re-queued by the service.

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
- `POST /api/v2/monitors/{id}/activate` verifies preview context and activates the
  attested revision on the existing table-profile cadence
- `POST /api/v2/monitors/{id}/run` queues one manual run with client idempotency

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
