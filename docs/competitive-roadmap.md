# Data Observability Product-Parity Roadmap

Status: Public-product research translated into an independent DataWatch roadmap.

This document records behavior visible in public vendor documentation. It is not a plan
to copy proprietary code, text, branding, or internal implementation. DataWatch will
implement compatible product ideas through its own typed DSL, connector contracts, and
incident model.

## Public Monte Carlo capability baseline

The public documentation reviewed on 2026-07-19 describes these product surfaces:

- Table monitors for freshness, volume, schema changes, and JSON structure.
- Validation monitors expressed as row-level predicate trees.
- Metric monitors including row-count change, uniqueness rate/count, duplicate count,
  and segmented metrics.
- Comparison monitors with manual thresholds.
- Custom SQL as a fallback when metric, validation, and comparison monitors cannot
  express the rule; the MaC contract requires exactly one numeric output.
- Scheduled, table-update, and upstream job/task-completion triggers.
- Monitor metadata including owners/audiences, tags, severity/priority, data-quality
  dimension, notes, timeout, and draft state.
- Notification controls, run-failure notification, noise reduction, incident workflow,
  and bounded breached-row evidence for investigation.
- Table health views that combine active-monitor state with incident state.

Primary references:

- [Table monitors](https://docs.getmontecarlo.com/docs/mac-table-monitors)
- [Validation monitors](https://docs.getmontecarlo.com/docs/mac-validation-monitors)
- [Available metrics](https://docs.getmontecarlo.com/docs/available-metrics)
- [Custom SQL monitor](https://docs.getmontecarlo.com/docs/custom-sql)
- [Custom SQL workflow](https://docs.getmontecarlo.com/docs/creating-sql-rules)
- [Table health](https://docs.getmontecarlo.com/docs/using-the-table-health-dashboard)

## DataWatch parity matrix

| Product behavior | Current DataWatch state | Next increment |
|---|---|---|
| Freshness and volume | Legacy profiler/detectors plus typed metric primitives | First-class DSL monitor kinds and scheduler |
| Schema changes | Profile fingerprint and drift detector | Typed schema-change policy and allow/deny lists |
| Row validations | Typed violations measurement and predicate compiler | Incident bridge plus bounded failed-row evidence |
| Numeric/quality metrics | Typed aggregate compiler for PostgreSQL, DuckDB, SQLite, MySQL, and SQL Server core | Warehouse compiled adapters and live version conformance |
| Document metrics | MongoDB bounded native sampling with provenance, field presence/null/type and numeric/text summaries | Repeated-sample schema confirmation and document predicate DSL |
| Compound conditions | Bounded `all`/`any`/`not` predicate tree | UI builder and YAML import/export |
| Consecutive breach/recovery/cooldown | Deterministic evaluator and persisted state | Public lifecycle and incident transitions |
| Custom SQL escape hatch | AST-restricted single scalar for selected local/PostgreSQL paths | Explicit advanced-mode UX, query budgets, audit labels |
| Trigger on profile/manual | Persisted trigger contract | Scheduler and manual-run API |
| Job completion trigger | Not implemented | Connector/query-history event adapter |
| Audience/ownership/tags/severity | Partial teams, owners, labels, severity | DSL audiences and routing policy |
| Run-failure notification | Policy flag persisted in execution errors | Notification dispatcher integration |
| Breached-row evidence | Not implemented | Redacted, bounded, opt-in evidence snapshots |
| Table health view | Existing health/incidents UI | Typed-monitor status and per-dimension rollup |

## Prioritized delivery

1. Finish the safe scheduler/manual-run/incident bridge and activate the persisted DSL.
2. Add first-class freshness, volume, schema, uniqueness, validation, and comparison
   templates on top of the existing typed measurement/predicate model.
3. Add owners, audiences, data-quality dimensions, notes, and notification/run-failure
   routing to definitions and API responses.
4. Add bounded evidence queries with explicit redaction, row limits, retention, and
   tenant controls; never store arbitrary raw rows by default.
5. Add update/job-completion triggers only after connector metadata/query-history
   collection is available and rate-limited.
6. Build the table-health UI and browser system specs from persisted monitor/run/incident
   state rather than synthetic frontend state.

## Non-negotiable differences

- Typed monitors remain the primary path; arbitrary SQL is an explicitly risky fallback.
- Every connector capability is published only after an executable conformance test.
- NoSQL monitors use document, partition, or keyspace-native plans rather than SQL-shaped
  strings.
- Evidence collection is opt-in, bounded, redacted, and retention-controlled.
- Activation stays fail-closed until scheduling, audit, policy, and incident transitions
  are connected end to end.
