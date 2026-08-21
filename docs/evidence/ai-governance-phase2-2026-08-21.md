# AI governance phase-two evidence — 2026-08-21

## Claim boundary

This increment proves an immutable, metadata-only evidence ledger and continuous
observe-mode controls. It does not prove legal purpose, actual workload use, regulatory
compliance, model fairness, or a production SLA. `unknown`, stale, unavailable, and
`unsupported` observations remain visible evidence gaps and never count as passing.

## Delivered vertical

1. A successful table profile enqueues governance reevaluation on the same configured
   monitoring cadence.
2. The runner resolves every active release manifest containing that exact tenant-owned
   asset and uses a profile-derived idempotency key.
3. Ownership, purpose/declaration, schema/freshness, data availability, evidence age,
   sensitivity ceiling, database privileges, and vector consistency produce typed results.
4. Every evaluation links to one immutable evidence descriptor with producer, provenance,
   content hash, evaluator version, validity window, redaction class, and retention class.
5. A deterministic summary exposes inherent-risk components, control coverage, evidence
   confidence, residual risk, headline state, and the exact non-passing reasons.
6. Confirmed failures open one deduplicated governance incident; clean evidence resolves
   it through the existing governance incident and alert workflow.

## Security and database proof

- Migration `015` adds `ai_evidence`, bringing the application schema to 29 tables.
- Fresh Alembic `001 → 015` completed on a disposable PostgreSQL database. Head was `015`;
  PostgreSQL reported six AI append-only triggers.
- A direct `UPDATE ai_evidence ...` probe against the local PostgreSQL instance was
  rejected by `reject_ai_governance_mutation()` with `AI governance audit records are
  append-only`; the attempted mutation was not applied.
- Composite `(evidence_id, org_id, system_id)` ownership prevents an evaluation from
  linking another tenant's evidence.
- Evidence descriptors pass the same raw-row/prompt/output/embedding/secret rejection
  contract as manifests and evaluations. Local JSONPath inspection of seeded evidence
  found zero forbidden raw keys.
- The seed and API use `metadata_only` redaction and `governance_indefinite` retention.
  Descriptors contain IDs, hashes, timestamps, bounded counts, classifications, reason
  codes, and grants—not database samples.
- Jury reset is an explicit local-only destructive workflow. It temporarily disables the
  append-only triggers, deletes governance rows in dependency order, restores trigger
  enforcement, then recreates deterministic fixtures. Two consecutive full resets passed.

## Verification snapshot

- Hosted CI for commit `86f88a2` passed all required lanes:
  [`DataWatch CI #32503556957`](https://github.com/ryvga/DataWatch/actions/runs/32503556957)
  (backend 3m57s, browser 3m19s, warehouse 1m39s, frontend 24s; managed
  warehouse credentials and the large Oracle lane remained explicitly gated).
- Full backend regression: 368 passed, 4 optional service skips in 24.67 seconds.
- Focused governance and Oracle regression: 20 passed, 1 credential-gated Oracle skip.
- CI-equivalent Ruff and the scoped governance/monitor mypy boundary passed.
- Focused lifecycle: deterministic replay reuses evaluation and evidence IDs; a scheduled
  refresh produces new evidence; two control failures remain deduplicated; a clean refresh
  resolves both incidents.
- Frontend build: 2,918 modules in 1.74 seconds; production audit found zero vulnerabilities.
- Four browser flows passed after the governance test added headline reasons, evidence
  confidence, evaluation-to-evidence links, and the observe-only boundary. Diagnostics were
  empty after correcting the evidence-link assertion.
- Fresh schema: 29 application tables plus `alembic_version`; six AI append-only triggers.
- Live local worker proof: profiling the governed products asset increased evidence rows
  from 4 seeded fixtures to 12 in one task chain; all eight phase-two evaluations linked
  metadata-only, indefinite-retention evidence. The final clean fixture run produced five
  pass, two explicit unsupported, and one fail result—no connector errors. The profile
  itself took 23 ms; the first profile-linked evidence row was committed 0.692 seconds after
  `collected_at`, well within
  the table's 15-minute monitoring interval. This single local observation is correctness
  evidence, not a latency distribution or SLA.

## Performance measurements

The raw measurements are in
[`ai-governance-phase2-benchmark-2026-08-21.json`](ai-governance-phase2-benchmark-2026-08-21.json).
Across 5,000 warm local calls, evidence descriptor canonicalization/hashing measured
0.0053 ms p50 and 0.0054 ms p95. Explainable risk-summary calculation measured 0.0016 ms
p50 and 0.0017 ms p95. These are isolated CPU costs, excluding database, connector,
Celery, network, and alert latency.

## PFE report mapping

- **Analyse / besoins:** why assertions, observations, validity, and uncertainty must remain distinct.
- **Conception:** immutable ledger, composite tenancy, idempotency, content hashes, validity windows.
- **Réalisation:** profile-to-governance task chain, typed controls, risk summary, incident reuse.
- **Sécurité:** metadata-only evidence, forbidden payload contract, append-only triggers, retention.
- **Validation:** fail/replay/dedupe/recovery lifecycle, fresh migration, UI provenance, live worker proof.
- **Limites / perspectives:** policy revisions, signed workload events, blocking approvals,
  exceptions, framework packs, exports, controlled end-to-end latency, and production scale.
