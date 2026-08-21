# AI governance phase-one evidence — 2026-08-21

## Claim boundary

This increment proves an observe-only PostgreSQL/pgvector RAG supply-chain contract. It
does not prove legal purpose, actual workload use, regulatory compliance, or production
deployment approval. Manual declarations are `customer_assertion`; database facts are
`connector_observation`. No raw row, prompt, output, embedding, password, API key, or token
is accepted in governance JSON.

## Delivered vertical

1. Register a stable AI system with business, technical, and risk accountability.
2. Append a canonical version containing provider/model identities and hashes only.
3. Append a declaration bound to an organization-owned monitored table, verified fields,
   and the stored schema fingerprint.
4. Create or deterministically replay an immutable release manifest.
5. Register a deployment and activate the exact manifest ID/hash with compare-and-swap.
6. Evaluate ownership, schema/freshness, effective roles, and vector missing/orphan/stale/
   deletion propagation counts.
7. Persist terminal results and open/resolve one active incident per stable dedupe key.
8. Reuse org-wide Slack/email/PagerDuty/webhook routes and render the provenance timeline.

## Database proof

- Alembic chain `001 → 014` ran on a fresh disposable PostgreSQL database.
- Head reported `014`.
- PostgreSQL reported five append-only triggers: system versions, data-use revisions,
  release manifests, reviewer attestations, and control evaluations.
- Composite foreign keys cover tenant ownership of owners, teams, system/version,
  source/table, deployment/manifest, and evaluation/incident relationships.
- A partial unique index permits history after resolution while preventing concurrent open
  incidents for the same organization/dedupe key.
- Phase-one retention is explicit and conservative: governance records are indefinite and
  organization deletion is `RESTRICT`, pending a separately authorized export/purge flow.

## Verification snapshot

- Targeted governance and monitor-runtime suite: 29 passed in 2.32 seconds.
- Full backend regression: 365 passed, 4 skipped in 23.51 seconds.
- Frontend production build: 2,918 modules transformed in 1.71 seconds; production dependency audit found zero vulnerabilities.
- AI-governance Playwright flow: inventory, system detail, data map, evidence provenance,
  and observe-only boundary passed with zero console errors, page errors, failed requests,
  or failed responses.
- Migration test database was removed after verification; the additive migration was also
  applied to the local demo database.

## Bounded connector and least-privilege proof

- The demo source databases now bootstrap with separate administrative owners
  (`acme_admin`, `analytics_admin`) and dedicated read roles (`readonly_user`,
  `analytics_ro`). The read roles are explicitly `NOSUPERUSER`, `NOCREATEDB`,
  `NOCREATEROLE`, and `NOINHERIT`; public schema creation is revoked.
- Existing local demo volumes were repaired in place without deleting source data. Role
  inspection returned `rolsuper=false`, `rolcreatedb=false`, and `rolcreaterole=false` for
  both read roles, whose table-grant inventory contained `SELECT` only.
- A live PostgreSQL governance observation ran through the production connector as
  `readonly_user`, inside its read-only transaction, five-second statement timeout, and
  ten-megabyte relation budget. It returned only aggregate zero counts and the effective
  grant `{role: readonly_user, privilege: SELECT}`. No row or embedding payload crossed
  the connector boundary.
- A regression test prevents either read role from becoming the Compose bootstrap owner
  again and asserts the least-privilege initializer contract.

## PFE measurements

The raw machine-readable result is
[`ai-governance-phase1-benchmark-2026-08-21.json`](ai-governance-phase1-benchmark-2026-08-21.json).
Across 5,000 warm calls, a 50-data-use canonical manifest took 0.0602 ms p50 and 0.0728 ms
p95; pure vector-control evaluation took 0.0038 ms p50 and 0.0048 ms p95. These values
exclude database/network/alert latency and must not be generalized as end-to-end latency.

## Jury scenarios

The `acme-corp` seed contains four deterministic records with `fixture: true`: stale
knowledge (172,800 s vs 86,400 s), unexpected `exporter` role, seven missing embeddings,
and three failed deletion propagations. They exist to make the UI and remediation narrative
repeatable. They are demonstration fixtures, not connector-observed production evidence.
