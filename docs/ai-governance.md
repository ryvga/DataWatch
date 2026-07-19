# DataWatch AI Governance Control Plane

Status: product and architecture proposal

Date: 2026-07-19

Audience: product, engineering, PFE jury, security, data, and AI governance teams

## Executive thesis

DataWatch should evolve from a data-observability product into a database-native AI
governance control plane. Its job is not to certify that an organization is legally
compliant. Its job is to produce continuous, reviewable evidence that an AI system:

1. uses declared data for a declared purpose;
2. has accountable owners and an approved active version;
3. satisfies explicit data, model, security, and human-oversight controls;
4. is monitored after deployment for data, retrieval, behavior, and control drift; and
5. leaves an immutable audit trail of evidence, decisions, exceptions, and incidents.

The differentiated wedge is **AI data governance with live evidence**, not a generic
survey or document repository. Databases, warehouses, document stores, vector stores,
and retrieval indexes are where an AI system's permissions, provenance, quality, and
purpose limitations become technically enforceable and continuously measurable.

Every claim is labeled as exactly one evidence class:

- `customer_assertion` — a declared purpose, processing basis, owner, or procedure;
- `connector_observation` — a bounded fact observed from a supported data system;
- `signed_workload_event` — an event from an authenticated deployed workload;
- `reviewer_decision` — a human approval, rejection, or exception;
- `external_assessment` — a referenced assessment produced outside DataWatch.

A declaration can prove that an asset exists and matches a recorded schema. It cannot
prove that a workload uses the asset, why it uses it, or that the use is lawful. Observed
use requires query/audit lineage or a signed workload event.

## Why DataWatch can credibly build this

The current platform already owns several difficult primitives:

- capability-aware database connectors and schema snapshots;
- exact and sampled profiles with explicit provenance;
- typed, versioned monitor definitions and schema-bound compilation;
- immutable monitor revisions and ordered execution audit records;
- anomaly detection, incidents, alerts, teams, and ownership;
- AI-assisted recommendations and incident explanations.

AI governance should reuse those primitives. It should not create a second scheduler,
incident system, expression language, or evidence store with weaker invariants.

## Product boundary

### DataWatch will be

- an inventory of AI systems, versions, owners, vendors, purposes, and risk context;
- a map from AI systems to database assets and declared data uses;
- a policy-as-code engine for AI data and operational controls;
- a continuous evidence and exception ledger;
- a release approval gate backed by current evidence;
- a post-deployment monitoring and incident surface;
- an exporter of evidence packs mapped to selected governance frameworks.

### DataWatch will not initially be

- a legal opinion or automated compliance certification;
- a replacement for a privacy counsel, DPO, model validator, or human risk committee;
- a full enterprise data catalog or automatic code-level lineage engine;
- an inline proxy for every model call;
- a fairness oracle when protected-class labels and outcome data are unavailable;
- a store for raw prompts, outputs, training records, or production samples by default.

## Standards anchor

The product model follows NIST AI RMF's continuous **Govern, Map, Measure, Manage**
functions. ISO/IEC 42001 supplies the management-system and continual-improvement frame.
EU AI Act concepts guide risk context, data governance, technical documentation, logging,
human oversight, post-market monitoring, and incident evidence. OWASP GenAI risks guide
technical controls for prompt injection, sensitive disclosure, supply chain, poisoning,
and excessive agency. Morocco's Law 09-08 supplies a locally relevant privacy lens around
purpose, proportionality, data quality, notification, and third-party processing.

Framework mappings are versioned content packs. A mapping says which DataWatch evidence
supports a control outcome; it never says that passing a monitor proves legal compliance.

## Core user journeys

### Register an AI system

An owner records the intended purpose, affected users, autonomy, consequences, lifecycle
stage, jurisdictions, provider/model dependencies, human review, and prohibited uses.
DataWatch derives an initial risk context and highlights missing accountability data.

### Declare how data is used

The owner links monitored assets or fields to a system version as training, fine-tuning,
validation/testing, RAG, online inference, feedback/outcome labels, or telemetry logs.
Each declaration records purpose, necessity, sensitivity ceiling, retention, residency,
customer-declared processing basis, allowed transformations, and an accountable steward.

### Apply a governance policy pack

A policy pack generates controls appropriate to the risk and data-use context. Examples:

- every production system has business, technical, and risk owners;
- restricted fields cannot be used for training without a recorded exception;
- RAG sources meet freshness and provenance requirements;
- inference features satisfy quality and schema contracts;
- model/provider choices belong to an allow-list;
- high-impact releases require independent approval and current evaluations;
- evidence must be newer than a configured maximum age;
- production events retain decision context without raw sensitive data.

### Review a release

An immutable system-version snapshot assembles its data map, policies, evaluations,
exceptions, unresolved incidents, and evidence freshness. A reviewer approves, rejects,
or requests changes. The active version changes only after required approvals and hard
controls pass. Emergency overrides are time-bound, justified, and separately audited.

### Monitor after deployment

DataWatch checks data quality, schema, freshness, sensitivity, provenance, retrieval index
freshness, evaluation regression, provider changes, evidence age, and runtime policy events.
Control failures create governance incidents with impact, ownership, evidence, and
remediation state.

## Domain model

All tenant-owned tables include `org_id`, timestamps, ownership constraints, and explicit
retention behavior. Stable identity is separate from immutable version/audit records.

### `ai_systems`

- stable identity, lifecycle status, team, and business/technical/risk owners;
- intended purpose, prohibited uses, affected population, autonomy, and human oversight;
- impact dimensions, jurisdictions, inherent risk, and residual-risk status;
- `current_version_id` points to the edit head; active state belongs to deployments.

### `ai_system_versions`

- append-only version number and canonical definition hash;
- model/provider/artifact identifiers independent of a deployment environment;
- prompt/config/evaluation-suite hashes, never raw secrets or prompt content by default;
- capabilities, limitations, fallback, human-oversight procedure, and risk snapshot;
- author and change rationale.

### `ai_data_use_revisions`

- system version to source/table/field binding;
- use kind, purpose, necessity, steward, and sensitivity ceiling;
- retention, residency, allowed transformations, and third-party transfer context;
- schema fingerprint at declaration time;
- immutable ordinal, author, rationale, and canonical representation.

The initial release supports manual declarations backed by verified connector assets.
Automatic lineage ingestion is a later adapter surface.

### `ai_release_manifests`

- immutable canonical manifest of system-version definition, data-use revision IDs,
  policy-revision assignments, evaluation-suite identities, and evidence cutoff;
- schema version, normalization rules, hash/HMAC algorithm identifiers, and manifest hash;
- approvals and activation always reference this manifest hash, never mutable current rows;
- changing any governed input creates a new manifest and invalidates prior approval for the
  changed release context.

### `ai_deployments`

- system, environment, region/tenant scope, workload identity, and deployment status;
- active manifest/version pointer updated with compare-and-swap semantics;
- mutable operational posture kept separate from immutable release approval;
- dev, staging, production, and regional deployments may coexist.

### `ai_governance_policies` and `ai_governance_policy_revisions`

- stable identity plus append-only canonical revisions;
- scope selectors for system, version, environment, risk, data use, source, and tags;
- typed controls, severity, evidence requirements, enforcement mode, and framework links;
- draft, active, and deprecated lifecycle with review and attestation.

### `ai_control_evaluations`

- idempotent evaluation for one policy revision, control, subject, input-manifest hash,
  evidence cutoff/trigger, and evaluator version;
- observation status: pass, fail, unknown, unsupported, not-applicable, or error;
- evidence references, observed metadata, expected contract, and evaluator version;
- immutable terminal result with no raw source records.

### `ai_evidence`

- typed evidence class, descriptor, keyed content HMAC/hash, producer, collection time, and
  validity window;
- source profile/run/evaluation IDs, redaction level, and retention class;
- optional encrypted bounded attachment for customer-supplied documents;
- supersession chain without destructive rewrite during its defined retention period;
- bounded canonical evidence manifest remains replayable after source profiles expire.

### `ai_approvals` and `ai_exceptions`

- subject, reviewer role, decision, rationale, and evidence snapshot hash;
- separation of duties: authors cannot satisfy independent approval requirements;
- exception owner, compensating control, expiry, and review cadence;
- an exception never rewrites an observation; effective disposition is derived from the
  immutable evaluation plus a separately immutable, time-bounded decision;
- expiry creates a new state transition rather than mutating historical evidence.

### Existing primitives to reuse

- reuse monitor patterns—canonicalization, revisions, compare-and-swap, ordered runs,
  leases, and deterministic evaluation—not the current table-bound monitor rows;
- add a governance evaluation runner with generic subject kind/ID, control ID, manifest
  hash, sequence, and idempotency key;
- add a governance-incident subject/dedupe model keyed by deployment, policy revision,
  control, and scope; reuse alert delivery and workflow rather than table-only deduplication;
- users, teams, invites, and on-call ownership;
- table profiles and schema snapshots as evidence sources;
- connector capabilities to declare what can actually be verified.

### Database invariants

- unique `(system_id, version_number)` and `(policy_id, revision_number)`;
- composite foreign keys prove organization/system ownership for every relationship;
- current and deployment-active pointers can reference only versions/manifests owned by the
  same system;
- terminal versions, data-use revisions, manifests, approvals, and evaluations are protected
  by PostgreSQL append-only triggers within retention;
- one active governance incident per stable dedupe key;
- org deletion, legal deletion, tombstones, export, cryptographic erasure, delayed purge,
  and `RESTRICT`/anonymize/cascade behavior are explicit in the retention threat model.

## Governance policy DSL

AI governance needs a distinct document kind while reusing current canonicalization,
revision, attestation, evaluation, and audit patterns.

```yaml
apiVersion: datawatch.io/aigov/v1alpha1
kind: AISystemPolicy
metadata:
  name: production-rag-baseline
spec:
  scope:
    environments: [production]
    dataUses: [rag]
  controls:
    - id: ownership-complete
      type: metadata.required
      fields: [businessOwner, technicalOwner, riskOwner]
    - id: rag-source-freshness
      type: data.freshness
      maximumAge: 24h
    - id: restricted-data-denied
      type: data.sensitivity
      maximum: confidential
    - id: evidence-current
      type: evidence.maximumAge
      evidenceTypes: [retrieval-evaluation, security-evaluation]
      maximumAge: 30d
    - id: independent-release-review
      type: approval.required
      roles: [risk_owner]
      independentFrom: [version_author]
  enforcement:
    mode: observe
    onFailure: open_incident
```

### DSL safety rules

- no general-purpose code, SQL, JavaScript, templates, or network calls;
- strict schema with unknown fields rejected;
- typed durations, enums, identifiers, and bounded arrays;
- selectors resolve only tenant-owned registry objects;
- data controls compile through connector-specific typed planners;
- metadata controls execute as pure deterministic evaluators;
- unknown evidence is not coerced to pass;
- activation binds a canonical hash, evaluator/compiler version, and evidence context;
- `block` remains unavailable until dry-run, approval, rollback, and failure-mode system
  tests pass.

## Control catalog

### Governance and accountability

- required owners, reviewers, intended purpose, prohibited use, and human oversight;
- risk assessment, review cadence, vendor inventory, and contractual evidence;
- AI literacy or training acknowledgements;
- exception expiry and separation of duties.

### Data and database controls

- sensitivity and PII classification;
- declared-purpose and allowed-use matching;
- minimization: only declared fields may feed a use;
- effective database roles, service accounts, grants, and privilege drift;
- row-level security, column masking/tokenization, and approved-view enforcement;
- query/audit-log coverage and last observed workload access;
- connector-observed retention/TTL/partition policies, replica/backup residency, provenance,
  and schema binding where the connector exposes those capabilities;
- freshness, completeness, validity, uniqueness, drift, and label quality;
- training snapshot identity, reproducibility, temporal split leakage, and feature-store
  online/offline parity where identifiers exist;
- RAG source/vector missing, orphaned, stale, and deleted-document propagation;
- embedding model/config identity, metadata-filter enforcement, and unauthorized field
  exposure;
- sampled controls retain count/schema provenance and never treat an unobserved field as
  proof of absence.

### Model and application controls

- approved model/provider/version and supply-chain inventory;
- evaluation thresholds and approved-baseline regression;
- explainability/reason-code, fallback, escalation, and kill-switch evidence;
- prompt/config hash drift;
- prompt injection, disclosure, poisoning, and excessive-agency test evidence;
- tool allow-lists and least-privilege data access.

### Operational controls

- production logging coverage, retention, and telemetry gaps;
- unresolved serious incidents and remediation deadlines;
- stale evaluation/evidence and unapproved version changes;
- monitoring coverage and exception expiry.

Every control type publishes a connector evidence contract: required capability, exact or
sampled provenance accepted, confidence/minimum sample, supported subject scope, result
semantics, and explicit unsupported reason. A declaration of retention, residency, least
privilege, or absence is not machine evidence unless the selected connector can verify it.

## Risk and status model

Do not hide governance behind one opaque score. Display four explainable components:

1. **Inherent risk** — impact, scale, autonomy, population, and sensitive domains.
2. **Control coverage** — applicable controls with an implemented verification path.
3. **Evidence confidence** — freshness, provenance, scope, and evaluator reliability.
4. **Residual risk** — failures, accepted exceptions, and mitigating controls.

The headline state is `not_assessed`, `needs_review`, `approved`, `degraded`, `blocked`, or
`retired`. Control observations separately distinguish `unknown`, `unsupported`, and
`not_applicable`; connector capability and sampling confidence are part of the result.
Every state includes reasons. A percentage may help ordering, but it must never erase
mandatory failures or incomplete evidence. Computed tiers are operational governance
tiers, not inferred EU AI Act legal classifications.

## Enforcement ladder

1. **Observe** — collect evidence and show gaps; no workflow interruption.
2. **Warn** — incidents and notifications; releases remain possible.
3. **Require approval** — active-version promotion needs named roles.
4. **CI/CD gate** — a signed, short-lived decision attestation gates deployment.
5. **Runtime containment** — only narrow controls with tested failover may block access.

The SaaS should launch with observe/warn. Making application availability depend
synchronously on DataWatch would create unacceptable safety and reliability coupling.

## API surface

Proposed tenant-scoped endpoints:

- `GET/POST /api/v1/ai/systems`
- `GET/PATCH /api/v1/ai/systems/{id}`
- `POST /api/v1/ai/systems/{id}/versions`
- `GET/POST /api/v1/ai/system-versions/{id}/data-use-revisions`
- `POST /api/v1/ai/system-versions/{id}/release-manifests`
- `GET/POST /api/v1/ai/systems/{id}/deployments`
- `POST /api/v1/ai/deployments/{id}/activate-manifest`
- `GET/POST /api/v1/ai/governance-policies`
- `POST /api/v1/ai/governance-policies/{id}/preview`
- `POST /api/v1/ai/governance-policies/{id}/activate`
- `GET /api/v1/ai/system-versions/{id}/controls`
- `GET /api/v1/ai/system-versions/{id}/evidence`
- `POST /api/v1/ai/system-versions/{id}/review`
- `POST /api/v1/ai/exceptions`
- `GET /api/v1/ai/system-versions/{id}/evidence-pack`

Bulk export and event ingestion require separate rate limits, idempotency keys, signed
producers, payload size limits, and retention policies.

## Product experience

### AI systems inventory

A searchable list with owner, lifecycle, risk, active version, governance state, open
failures, evidence age, and linked assets.

### System detail

- Overview — purpose, risk context, owners, active version, state;
- Data map — training/RAG/inference/logging assets and field declarations;
- Controls — applicability, result, evidence, exception, and remediation owner;
- Versions — immutable changes and release approvals;
- Evidence — provenance timeline and framework mapping;
- Incidents — governance and data-quality failures;
- Documentation — generated system card, data card, and evidence pack.

### Governance dashboard

Prioritize production systems without approved versions, high-consequence systems with stale
evidence, restricted data outside declared purpose, versions changed after approval,
expiring exceptions, unresolved incidents, and framework coverage by evidence confidence.

## Phased delivery

### Phase 0 — Foundation specification

Domain model, tenancy/retention threat model, control taxonomy, framework mappings,
schemas, API contracts, migration review, and fixture-driven PFE scenarios.

Exit: accepted ADRs, API schemas, risk model, security review, and test plan.

### Phase 1 — Inventory and AI data map

System/version/deployment registry; owners, purpose, operational risk, lifecycle, and
model/provider inventory; immutable release manifests; manual declared links to verified
data assets; generated draft system/data cards; API and initial UI.

Exit: an organization can version an AI system, declare its data uses, and verify that the
declared database assets exist and match a schema snapshot without exposing secrets or raw
data. It does not yet claim observed workload use.

### Phase 2 — Continuous data evidence

Evidence and immutable evaluations; profile/schema/monitor evidence; freshness, quality,
provenance, evidence-age, and sensitivity controls; observe/warn policies and incidents.

Exit: a database change updates control state and evidence automatically and can open a
deduplicated governance incident.

### Phase 3 — Reviews, exceptions, and release gates

Policy revisions/preview, separation-of-duties approvals, time-bound exceptions, active
version promotion attestations, evidence exports, and framework mappings.

Exit: governed activation requires valid controls, evidence, approvals, and exceptions.

### Phase 4 — Runtime and evaluation telemetry

Signed OpenTelemetry/SDK events; redacted provider/model/prompt-config hashes; retrieval,
grounding, drift, security, cost, and latency evidence; vendor/model change detection.

Exit: deployment and production evidence share one immutable version context.

### Phase 5 — Ecosystem and compliance packs

Lineage/catalog/vector-store adapters, CI/CD and model-registry integrations, versioned
NIST/ISO/EU/OWASP/Morocco mappings, and assessor workflows.

Exit: mappings are traceable and distinguish automated evidence, customer assertions,
and external professional assessment.

## First vertical slice

The sharper database-native wedge is a **PostgreSQL/pgvector RAG data-supply-chain
contract**:

**Register system and production deployment → create an immutable release manifest → bind
approved source/view fields and vector table → evaluate ownership, schema/freshness,
effective database privileges, and vector consistency → render evidence and incidents.**

It includes:

- migrations for systems, versions, deployments, immutable data-use revisions, and release
  manifests;
- tenant-safe CRUD with separate edit head and per-deployment active manifest;
- canonical manifest hash and append-only database contracts;
- verified source/table/field binding using existing schema snapshots;
- four controls: owner assertion, schema/freshness evidence, effective database privilege
  drift, and vector missing/orphan/stale/deletion propagation;
- governance-specific runner and incident dedupe key, reusing alert workflow;
- evidence timeline distinguishing assertions, connector observations, and reviewer decisions;
- IDOR/property isolation matrix, stale schema, mutation-attempt, forged ownership,
  manifest CAS, incident-concurrency, and deterministic-replay tests;
- frontend inventory and system-detail shell;
- seeded jury scenarios: stale knowledge, unauthorized field/grant, missing embedding, and
  failed deletion propagation.

The slice remains `observe` only. Policy authoring, compliance exports, runtime ingestion,
and deployment blocking are later phases. MongoDB and external vector stores follow once
the PostgreSQL contract is proven.

## Security and privacy invariants

- never persist raw training rows, prompts, outputs, embeddings, or credentials by default;
- collect keyed tenant-scoped HMACs for guessable prompt/config content, counts,
  classifications, aggregates, and bounded redacted evidence;
- content attachments require opt-in, allow-lists, redaction, size/retention bounds, and
  encryption;
- enforce organization ownership at every query and composite relationship;
- separate edit head, approved manifest, deployment-active manifest, and current posture;
- make terminal evidence, approvals, evaluations, manifests, and versions append-only within
  explicit retention; preserve bounded replay manifests when source profiles expire;
- never call an LLM to decide whether a mandatory control passed;
- AI may recommend classifications or mappings, but rules and humans approve;
- unknown, stale, unavailable, or unsupported evidence never silently passes;
- every framework pack and evaluator carries a version;
- exports separate assertions, automated observations, and reviewer decisions.
- signed workload manifests define identity, key rotation/revocation, sequence,
  nonce/idempotency, replay window, and clock-skew behavior;
- uploaded evidence stays outside core PostgreSQL where practical and requires malware
  scanning, content allow-lists, encryption, bounds, and deletion policy.

## PFE evaluation plan

### Research question

Can database-native continuous evidence reduce the time and ambiguity required to assess
AI governance readiness compared with a static questionnaire?

### Experiments

- seed an internal summarizer, RAG support assistant, and high-consequence scoring workflow;
- inject stale RAG data, schema drift, undeclared sensitive fields, expired evidence,
  model-version drift, and expired exceptions;
- measure detection time, evidence completeness, reviewer decision time, false positives,
  unsupported/unknown rate, and remediation time;
- compare a manual checklist with the DataWatch evidence pack using randomized or
  counterbalanced task order, seeded ground truth, a declared participant count, and
  inter-rater agreement;
- document which controls are automated, asserted, or human-assessed.

### Success metrics

- a fixed IDOR/property-test matrix produces zero unauthorized reads or writes;
- database mutation attempts fail for every terminal version, manifest, evidence,
  evaluation, and approval table;
- automated scans find zero raw values in API payloads, evidence JSON, logs, traces,
  exports, errors, and exception paths;
- byte-identical evaluation results replay from a content-addressed input manifest and
  pinned evaluator version;
- event-to-incident p50/p95 includes scheduler and queue delay;
- report precision, recall, false-positive rate, unsupported rate, task-completion time,
  inter-rater agreement, and confidence intervals against seeded ground truth;
- every status links to reasons and evidence;
- no compliance or certification claim generated by the product.

## Key product decisions

1. Lead with **AI data governance and continuous evidence**, not broad GRC.
2. Use AI for recommendations and documentation assistance, never mandatory-control
   adjudication.
3. Ship observe/warn before approval gates, and approval gates before runtime blocking.
4. Separate assertions, machine evidence, reviewer decisions, and framework mappings.
5. Reuse typed-monitor patterns and connector planners, not table-bound monitor/incident
   rows that cannot represent governance subjects.
6. Treat framework mappings as versioned evidence-mapping packs, not compliance coverage
   or a universal score. ISO normative content requires appropriate licensing.
7. Make Morocco 09-08 meaningful for the PFE/local market while keeping the architecture
   suitable for NIST, ISO, EU, and OWASP mappings.

## Open questions before Phase 1

- **Version vs deployment:** version is the release definition; deployments become a
  Phase 4 table when runtime telemetry exists.
- **Sensitive-field classification:** start with names, types, customer labels, and opt-in
  bounded detectors; never retain matched values.
- **Legal risk tier:** store operational risk separately from customer/legal classification;
  never infer binding legal status.
- **Approval roles:** configurable business, technical, data, and risk owners; independent
  risk review only in higher-risk packs.
- **First runtime integration:** signed OpenTelemetry-compatible evaluation events, not an
  inline model proxy.

## Primary references

- [NIST AI Risk Management Framework 1.0](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-ai-rmf-10)
  and [Generative AI Profile](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf)
- [NIST AI RMF Playbook](https://airc.nist.gov/airmf-resources/playbook/)
- [ISO/IEC 42001:2023 AI management systems](https://www.iso.org/standard/42001)
- [Regulation (EU) 2024/1689](https://eur-lex.europa.eu/eli/reg/2024/1689/oj?locale=en)
- [OWASP Top 10 for LLM and Generative AI Applications 2025](https://genai.owasp.org/llm-top-10/)
- [Morocco Law 09-08 and CNDP guidance](https://www.cndp.ma/textes-et-lois/)

Future framework packs must preserve source, version, publication date, mapping rationale,
and review date.
