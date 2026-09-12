# Panopta PFE defense study guide

Prepared on 12 September 2026 for Mounir Gaiby, ISGA Casablanca, 3CI Big Data et Intelligence Artificielle. Academic supervisor: Pr. HANINE MOHAMED.

This is a learning guide, not a script to recite. The presentation and spoken defense are in English. The written report remains in French. These explanations help you answer the question behind a jury question. They describe the repository inspected for this revision, not a claim that every test or deployment passed today.

## 1. The project in one minute

Panopta is a multi-tenant data quality monitoring application. It connects to a customer's source, profiles selected assets, evaluates technical and business rules, opens incidents, and helps a person investigate them. Statistical detectors identify unusual profiles. A language model turns incident context into hypotheses, proposed checks and recommended actions.

The person still decides. A generated explanation does not prove the cause. A resolved incident does not repair a source table.

My professional context is software engineering in the Payments team at Oyster. I work on payment-related tasks. This is employment, not an internship. That context explains why incomplete, stale or inconsistent payment data matters to me. It does not mean Oyster uses Panopta in production. The demo uses synthetic data, not Oyster customer records.

The strongest PFE contribution is the complete engineering chain. I connect heterogeneous systems, reduce their contents to useful measurements, apply statistical and explicit business controls, preserve execution evidence, and expose the result through an investigation workflow. The typed monitor lifecycle is particularly defensible because it turns an editable rule into a validated, versioned and traceable execution.

Evidence: `CLAUDE.md`, `backend/app/tasks.py`, `backend/app/routers/monitor_dsl.py`, `scripts/pfe/build_rapport_word.py`.

## 2. How the report becomes an oral argument

Follow the report's progression rather than describing every navigation item. Start with the professional context and the reliability problem. State requirements. Explain the architecture and data model. Demonstrate the implemented monitoring chain. Finish with validation, limits and improvements.

The three-month realization period runs from June through the end of August. It describes the initial project phase. Development continues afterward. Do not compress later engineering into an invented historical date.

The demo should answer four questions. What is monitored? How is a rule defined? What happens when it fails? What evidence can the operator inspect? Sources, table profiles, DSL, SQL, execution history and incidents deserve more time than billing or staff administration.

Prepare two levels of explanation. At the first level, say what the screen lets someone do. At the second, explain the request, stored state and background work behind the action. For example, clicking Run is not merely refreshing a number. For a typed monitor, it requests an execution pinned to an active revision and leaves an audit record.

Evidence: `docs/pfe/reference/Structure_Rapport_ISGA.pdf`, `scripts/pfe/build_rapport_word.py`, `frontend/src/App.jsx`.

## 3. Architecture without hand-waving

React renders the workspace. FastAPI exposes authenticated routes and coordinates services. SQLAlchemy maps application objects into PostgreSQL tables. PostgreSQL stores organizations, monitoring configuration, profiles, incidents and audit records. Redis supports queued work and caches. Celery performs background tasks. APScheduler supplies monitoring cadence.

The monitored source and the application database have different jobs. A source may contain orders or payments. Panopta's database records how that source is configured, what was measured and what failed. An `orders` table in the demonstration source is not one of Panopta's application tables.

A normal profile cycle starts with a scheduled or manual request. The worker loads the table and its source, decrypts connection configuration in the organization context and invokes the connector. It persists a profile, then queues anomaly evaluation. Check results can create or update an incident. Narration and alerting operate after the technical incident exists.

That separation keeps a slow database scan or external model call out of the ordinary page request. It does not make the workload free. Workers, source connections, network calls and PostgreSQL still have finite capacity.

An asynchronous Python function allows other work while waiting on I/O. A Celery task moves work to another execution process. Those are different mechanisms. Calling an API asynchronously does not itself distribute computation over a cluster.

APScheduler's in-memory scheduling requires reconstruction after restart. The recovery logic uses stored monitoring state to restore jobs and handle overdue work. For production, inspect process topology carefully. Several API processes each starting the same scheduler can create duplicate scheduling pressure unless leadership is controlled.

Evidence: `backend/app/main.py`, `backend/app/scheduler.py`, `backend/app/worker.py`, `backend/app/tasks.py`, `docker-compose.yml`.

## 4. Where Big Data actually appears

The strongest connection is data engineering. Panopta handles heterogeneous source capabilities, performs computation close to the data, separates background collection from the interface and builds a time series of profiles for later analysis.

Pushdown means asking the source database to calculate values such as COUNT, AVG and standard deviation. Returning a compact profile avoids transferring the entire business table into the API process. A table can have millions of records while the profile contains a manageable set of measurements.

There are costs on the source side. Exact distinct counts and percentiles can require expensive scans. Connector-specific limits, sampling and capability contracts matter. Some paths gather bounded distribution values or metadata. Never say the application never reads any source value, or that every connector uses exactly one query.

Volume is addressed through aggregation and execution boundaries. Variety appears in relational, analytical and native source adapters. Velocity is currently periodic profiling and queued execution, not a demonstrated high-throughput event stream. Veracity is the product's central concern: whether data is complete, fresh, structurally stable and plausible.

Kafka is not part of this version. Redis and Celery solve task dispatch. Kafka would make sense for durable event ingestion, replay and independent consumers if the product needed those properties. Adding Kafka purely to name a Big Data tool would create operational burden without establishing a useful requirement.

The honest scaling answer is specific. Measure scan cost and queue delay. Limit concurrent work per source. Scale workers only while sources and the application database can sustain the load. Bound retention and index time-based access. Test large datasets and concurrent tenants before making throughput claims.

The connector registry exposes capabilities rather than pretending every adapter is equivalent. PostgreSQL is the strongest reference path. Experimental adapters require their own runtime and conformance evidence. A visible connector option is not proof of production maturity.

Evidence: `backend/app/connectors`, `backend/app/services/profiler.py`, `docs/connector-catalogue.md`, `backend/tests/test_relational_monitor_connectors.py`.

## 5. Profiles and data quality vocabulary

A profile is a dated observation, not a copy of the table. `row_count` measures volume. `freshness_seconds` measures age relative to a configured timestamp. A schema fingerprint summarizes observed structure. `column_metrics` stores measurements whose availability depends on type and connector.

Null rate is the fraction of missing values. If 85 of 8,500 rows have a null status, the rate is 0.01, or 1 percent. Distinct count measures different values. A distinct-to-row ratio can help reveal duplicate concentration, but interpretation depends on the field. Repeated country codes are normal. Repeated transaction identifiers may be a problem.

For numerical columns, mean describes the center and standard deviation describes spread. Percentiles show where values sit in an ordered distribution. A p95 shift may reveal tail behavior that an unchanged average hides. None of these metrics alone explains why a pipeline changed.

Freshness is easy to misread. A successful profile taken now can describe a source whose newest business record is days old. The time of observation and the time of the newest data are different clocks. The demo's fixed synthetic dates can produce very large freshness values. Explain that openly.

Schema drift concerns changes in fields or types. A fingerprint mismatch is evidence of structural change, not a complete semantic diagnosis. Sampled native observations require care because an absent field in a sample does not prove a field disappeared everywhere. The detector checks provenance to avoid treating some approximate observations as exact.

Evidence: `backend/app/models/table_profile.py`, `backend/app/services/profiler.py`, `backend/app/services/anomaly.py`.

## 6. SQL controls and the typed DSL

### 6.1 The historical SQL path

The scalar SQL monitor answers a narrow question: how many rows violate this rule?

```sql
SELECT COUNT(*) AS violations
FROM public.orders
WHERE payment_status IS NULL
```

The query returns a single nonnegative integer. Zero passes. A positive value fails and can enter the incident workflow. A string, negative number, fractional number, multiple columns or multiple rows is not silently interpreted as success.

SQL validation uses an abstract syntax tree rather than checking whether the text happens to contain a forbidden word. A literal containing the word DELETE is still data. A real DELETE statement is prohibited. The rule must read its monitored table, include the monitored schema and avoid other assets, prohibited functions, writes and locks. Read-only connector execution and timeouts provide additional boundaries.

The legacy model stores query text, severity, activation state, whether it runs on profiling, and the latest result. It is useful and implemented. It does not provide the same revision and execution model as the typed DSL.

### 6.2 Why introduce a DSL?

A domain-specific language gives a rule a strict shape. It identifies a target, measurements, a breach predicate, a policy and execution constraints. Unknown fields, invalid references, unsupported versions and excessive expression complexity are rejected.

For example, the following fragment measures missing payment statuses and breaches above 1 percent:

```json
{
  "measurements": [{
    "id": "missing",
    "type": "metric",
    "metric": "null_rate",
    "field": "payment_status"
  }],
  "breachWhen": {
    "op": "gt",
    "left": {"ref": "missing"},
    "right": {"literal": 0.01}
  }
}
```

This is an excerpt, not a complete API document. The complete definition includes `apiVersion`, `kind`, metadata and the actual target UUID. `datawatch.io/v1alpha1` remains the stable internal protocol namespace although the product is called Panopta.

The expression separates field references from literal values and measurement references. A compiler can bind identifiers against the observed schema and generate a connector-compatible plan. SQL parameter binding keeps literal values separate from executable statement structure.

### 6.3 Lifecycle to remember

Create a draft. Validate the contract. Preview the compiled plan. Activate a specific revision. Run it. Inspect its persisted result.

Preview is not a query against the source. The endpoint returns `compiled_validation_only` when compilation succeeds. It also issues an attestation tied to organization, asset, definition hash, schema fingerprint and planner version. Its default lifetime is 300 seconds. This binds activation to the plan context that was checked, not to an imaginary successful data measurement.

Saving an edit creates another revision. An active monitor continues executing the previously activated revision until the replacement is explicitly activated. That distinction prevents an unreviewed edit from silently changing a control already used in an investigation.

`consecutiveBreaches` requires repeated failures before opening an incident. `recoveryPasses` requires repeated successes before recovery. `cooldownMinutes` limits repeated notifications. Track mode records observations without the same alert behavior. Manual and profile-triggered execution are supported paths. An interval trigger has a structural representation, but the API rejects activation with `interval_trigger_not_supported` until its scheduler-backed implementation exists.

Run records have idempotency keys and exact revision references. Repeated delivery must not become repeated logical execution. A claim token and lease support worker ownership. Ordered evaluation state prevents a late result from blindly replacing a newer decision.

Evidence: `backend/app/services/legacy_sql_monitor.py`, `backend/app/routers/custom_monitors.py`, `backend/app/services/monitor_dsl.py`, `backend/app/services/monitor_compiler.py`, `backend/app/services/monitor_attestation.py`, `backend/app/services/monitor_run_service.py`, `backend/app/services/monitor_evaluator.py`, `backend/tests/test_monitor_dsl_persistence_api.py`.

## 7. Detection methods and the mathematics worth knowing

### Z-score

The formula is z = (x - mean) / standard deviation. The implementation takes up to 14 previous valid observations for each metric and needs at least 7. The table's sensitivity supplies the threshold, commonly 3. A value outside mean ± threshold × standard deviation fails.

Fourteen observations are not automatically fourteen days. The task loads a history interval, while the detector selects observation counts inside it. Hourly profiling changes what those counts mean. If historical standard deviation is zero, this implementation skips that z-score calculation rather than dividing by zero. Separate rules can still detect obvious problems.

### Direct rules

An exact row count of zero fails. A configured freshness column can breach an age limit. The basic freshness rule uses `check_interval_minutes × 60 × 1.5`, so a 60-minute cadence implies a 5,400-second threshold on that path. Other explicit freshness configuration should be explained from the selected screen and check name rather than assuming every freshness control shares one threshold.

A null spike compares against the previous profile and uses a 0.20 absolute change, meaning 20 percentage points. Going from 2 percent to 23 percent is a 21-point rise. It is not merely a 21 percent relative increase. Schema changes compare trustworthy fingerprints.

### Isolation Forest

Isolation Forest is unsupervised. It isolates unusual points through randomized partitions. Panopta builds multivariate vectors from profile measurements rather than predicting individual payment fraud. The code needs at least 21 history profiles, uses contamination 0.05 and random state 42, and tests a decision-function score below -0.1.

Contamination is a model setting, not a measured 5 percent real failure rate. A score is not a calibrated probability. Cached models reduce repeated training work, but cache validity and changing feature sets still need attention.

### STL

STL decomposes a series into trend, seasonal and residual components. The implementation uses row counts, at least 21 observations, `period=7` and robust fitting. It checks unusual residual behavior at a three-standard-deviation threshold. Seven observations only represent a week when observations are daily and regular enough for that interpretation.

### Other implemented checks

Cardinality drop uses a relative reduction greater than 30 percent against historical values, with sufficient history. Row growth applies statistical reasoning to differences between row counts. Enum drift compares observed category sets against recent profiles, requiring at least three historical profiles.

Numeric distribution drift compares the current column mean against historical means, using at least seven usable observations from the recent window and a three-standard-deviation threshold. This is not a full distribution-distance test over raw samples.

Null-rate trend looks for a sequence of increasing rates across five historical profiles and the current profile. Uniqueness drop compares recent ratios and flags a relative drop greater than 5 percent, with guards for insufficient history and already-low uniqueness.

CUSUM accumulates normalized deviations. The implementation needs ten historical exact row counts, uses allowance k = 0.5 and decision threshold h = 5. It can expose a gradual shift that individual points do not make obvious. Constant historical series are skipped in this path.

The trend check named Mann-Kendall calls SciPy's Kendall tau against ordered observation positions. It requires eight historical exact row counts and fails when absolute tau exceeds 0.6 and p-value is below 0.05. This signals a strong monotonic trend, not proof that growth is undesirable.

Percentile drift uses historical percentile values, a 30 percent relative change threshold and at least five usable history observations. Availability depends on the profiler supplying those metrics.

Do not memorize an outdated count of seven detectors. The current task invokes a broader set. Explain representative methods well and distinguish a function existing from that function being applicable to every source and dataset.

### How to evaluate them properly

Build labelled scenarios with normal variation, genuine failures and recovery. Precision is true positives divided by all positive alerts. Recall is true positives divided by all actual failures. False positives consume operator attention. False negatives leave problems undetected. Measure detection delay as well.

A seeded incident proves the pipeline can react to that scenario. It does not establish precision, recall or superiority over another product. Thresholds need validation against cadence and domain behavior. Normal business growth can be statistically unusual and still be correct.

Evidence: `backend/app/services/anomaly.py`, `backend/app/tasks.py`, `backend/tests/test_anomaly.py`.

## 8. The LLM layer in practical terms

The detector establishes a technical signal first. Context assembly then gathers incident details, fired checks and profile history. A compact history representation keeps the prompt focused on relevant changes. The OpenAI-compatible client calls the configured provider endpoint, normally through OpenRouter.

The current call uses temperature 0 and a maximum of 4,096 output tokens. Do not repeat the older module comment saying 1,024. Temperature 0 reduces sampling variation but does not guarantee identical output or factual correctness across requests and provider changes.

The output is a Pydantic-validated object. It includes a summary, likely causes, impact, recommended actions, debug queries, a client-safe summary, suggested monitors, ownership hints, pattern notes and a qualitative confidence label. Causes have high, medium or low labels. Those labels are generated assessments, not measured probabilities.

The parser strips formatting and attempts limited repair of truncated JSON before validation. Invalid content can trigger a retry with a stronger format instruction, then a smaller fallback prompt. The code can make three attempts. API failures can return an explicit narration error. With no configured key it returns no narration.

A code limitation deserves attention: the initial call passes organization-specific key and model overrides, but later format retries call the helper without those overrides and therefore use global defaults. That should be hardened before promising strict per-organization provider routing across every retry. It is not fixed by this study guide.

Narration is cached by incident identifier in Redis for 24 hours. Caching lowers repeated latency and cost. Invalidation matters when the underlying incident changes. PostgreSQL also stores the narration associated with the incident, so the interface is not merely displaying an ephemeral chat response.

The model does not automatically repair the warehouse or execute every generated debug query. Suggestions require review. Source metadata and values included in context deserve privacy review before sending them to an external provider. Aggregate-centric context is helpful, but it is not a universal guarantee that no sensitive information can enter a prompt.

Evidence: `backend/app/services/llm.py`, `backend/app/services/llm_context.py`, `backend/app/tasks.py`, `backend/tests/test_llm.py`.

## 9. AI governance, explained carefully

### What the term means here

AI governance is the operating discipline around an AI system: who owns it, what it is for, what data it claims to use, which version is deployed, what evidence supports that description and what should happen when evidence becomes stale or contradictory.

That is different from using AI to explain incidents. Panopta has an AI-assisted feature and a prototype for governing registered AI systems. These are related topics, not the same module.

Imagine a registered assistant that uses a RAG knowledge base. Someone declares the relevant source, fields, purpose, retention, expected database roles and vector contract. Panopta records those declarations against a system version. It can then compare supported observations with that declared context and retain the results.

### What the prototype implements

The inventory stores a system's purpose, prohibited uses, affected population, autonomy, oversight and responsible people. Versions capture provider, model and configuration-related hashes with a change rationale. Declared data uses connect a version to source assets and fields.

A release manifest freezes a canonical release context and evidence cutoff. A deployment identifies an environment and region and points to an active manifest. Compare-and-swap activation uses a generation value to reject stale competing changes. It records which manifest is considered active, not a universal gate in front of every model invocation.

Evidence descriptors retain producer, provenance, content hash, evaluator version, validity and retention information. Sensitive-payload rejection and redaction rules aim to keep governance evidence metadata-focused. A hash identifies content and supports integrity checks. It does not prove that the content was true when submitted.

Control evaluations preserve observed and expected values, status, reason code and input hash. Failures can create deduplicated governance incidents and use existing alert routing. Supported refresh paths can follow profile cadence, so evidence is not limited to a one-time form submission.

### Declaration is not observation

`customer_assertion` means the customer declared something. `connector_observation` means a supported connector observed something. `reviewer_decision` records a person's review. Other evidence classes exist in the schema, including external assessments and signed workload events, but an enum value is not proof of a complete ingestion or verification product for that class.

A purpose field cannot establish that all real-world usage respects that purpose. An approval cannot establish legal compliance. A matching vector dimension cannot establish that retrieved documents are accurate or fair. Keep the evidence boundary next to the claim.

### Controls you can explain to the jury

Ownership checks whether accountable roles are supplied. Schema freshness compares declared context with available profile evidence and age. Evidence-age checks distinguish current from stale or missing evidence. Data-quality evidence examines supported profile availability and basic condition, not every possible quality property.

Sensitivity-boundary evaluation compares declared limits with available field sensitivity information. Purpose-declaration evaluation checks declared purpose-related content, not the legality of actual use. Effective database-role drift compares observed privileges with expected roles where supported. Vector consistency checks supported RAG/vector observations against a declared contract.

The PostgreSQL and pgvector path gives concrete material for this extension. It is not a blanket guarantee for every source type. Unsupported observations should remain unsupported, not become a green pass.

### Reading the score

The statuses are pass, fail, unknown, unsupported, not_applicable and error. Unknown means evidence is missing or inconclusive. Unsupported means the required observation is not implemented for that context. Neither means safe.

The summary score is an explainable heuristic. Inherent risk adds components for autonomy, production status, affected population and data sensitivity, capped at 100. Coverage is the percentage of applicable controls with a pass or fail result. Evidence confidence gives full weight to pass and fail, partial weight to errors and none to unknown or unsupported results.

Residual risk combines inherent risk, passing coverage and missing confidence. The expression is `min(100, inherent × (1 - 0.65 × pass_ratio) + (100 - confidence) × 0.15)`. A failed control can therefore have high evidence confidence. We may be confident that a problem exists.

These coefficients are engineering choices. They are not a scientifically calibrated probability of harm or a legal risk classification. The screen should support investigation, not replace domain judgment.

### Why call it a prototype?

Its scope is inventory, release context, evidence and observation. It does not certify compliance, measure fairness comprehensively, prove model safety, trace every runtime request or block unsafe inference across external systems. Reviewer approvals are non-gating. The manifest explicitly uses observe mode.

The next useful work is stronger evidence collection, authenticated workload integration, better evaluation coverage and tests of stale, contradictory and missing evidence. Any enforcement mode would need a separate design for failure behavior, authorization, bypasses and operational responsibility. Do not promise that it already exists.

Evidence: `backend/app/models/ai_governance.py`, `backend/app/services/ai_governance.py`, `backend/app/routers/ai_governance.py`, `docs/ai-governance.md`.

## 10. Database structure and relationships

The inspected ORM contains 29 application tables. Alembic also maintains migration bookkeeping. Business tables such as demo orders live in source databases and should not be added to this application-table count. Most entities use UUID identifiers. Time fields record lifecycle or observation timestamps. JSONB holds heterogeneous definitions, metrics and evidence while relational keys preserve identity and ownership.

### Identity and collaboration, eight tables

1. `organizations` is the tenant root. Fields include name, slug, plan, encrypted LLM key, LLM model, Stripe customer identifier, PayPal subscription identifier, billing period, subscription status and trial end. One organization owns many users, sources and incidents.
2. `users` belongs to an organization. It stores email, password hash, role, full name, active state, creation time and last login. It participates in team memberships and incident ownership.
3. `staff_users` is a separate staff identity store with email, password hash, name and active state. It is not a customer role inside an ordinary organization.
4. `api_keys` belongs to an organization and stores name, key hash, creation time and last-use time. The stored hash is not the reusable plaintext key.
5. `invites` stores organization, email, proposed role, token, inviter, expiry and acceptance time. An invitation and a user account are separate lifecycle objects.
6. `teams` belongs to an organization and stores name, description and color. Teams can own tables and receive incident assignments.
7. `team_members` links a user to a team, with membership role and joining time. This is the join entity for the many-to-many relationship.
8. `oncall_schedules` links a team and user over start and end timestamps. It represents scheduled responsibility, not an incident itself.

### Monitoring and investigation, ten tables

9. `data_sources` stores organization, name, type, encrypted connection configuration, status and last connection time. A source exposes many monitored assets.
10. `monitored_tables` references a source and identifies schema and table names. Configuration includes freshness column, interval, sensitivity, active state, dbt YAML, autopilot JSON, check configuration, last-profile time and owner team/user references.
11. `table_profiles` references a monitored table and stores collection time, row count, freshness, schema fingerprint, column metrics, provenance, duration and error. One table has many profiles.
12. `check_results` references a table and optionally a profile. It stores check type/name, optional column, status, observed value, expected range, deviation and check time. A custom SQL check can exist without an ordinary profile reference.
13. `incidents` references organization and table. It stores severity, status, title, fired checks and narration, plus creation, acknowledgement and resolution timestamps. User and team assignment fields preserve responsibility.
14. `custom_monitors` stores the transitional SQL definition, organization/table scope, name, description, severity, active and run-on-profile flags, creator and latest execution result.
15. `monitors` provides stable typed-monitor identity, organization/table scope, name, mode, lifecycle status, current revision number and active revision pointer. Current editable head and active revision can differ.
16. `monitor_revisions` stores monitor reference, revision number, protocol version, canonical definition, definition hash, validation status and schema fingerprint, with authorship and creation time.
17. `monitor_runs` references organization, monitor, exact revision, table and optional profile. Fields include idempotency key, trigger, sequence and queue times, plan hash, planner version, definition hash, schema fingerprint, status, attempt, claim token, lease expiry, measurements, result, error and execution timestamps.
18. `monitor_evaluation_states` is the mutable policy state for a monitor. It stores revision, phase, breach and recovery streaks, cooldown, last run, last ordering data and a version counter. Separating this from run history preserves both fast evaluation and an audit trail.

### Delivery, two tables

19. `alert_configs` belongs to an organization and optionally a specific table. It contains channel, configuration JSON, active state and creation time. Optional table scope distinguishes broader routing from table-specific routing.
20. `user_notification_prefs` links user and organization. It stores assignment, team and status-change preferences, daily digest flag/hour and mute-until time. Preference storage alone does not prove every possible notification path is fully implemented.

### Governance, nine tables

21. `ai_systems` holds stable identity, organization, slug, name, lifecycle, intended purpose, prohibited uses, population, autonomy, oversight, business/technical/risk owners, team, risk context and current-version pointer.
22. `ai_system_versions` references the owning system and organization. It preserves version number, canonical definition/hash, provider, model, artifact hash, prompt configuration hash, evaluation-suite hash and change rationale.
23. `ai_data_use_revisions` ties a version to source and table. It stores use kind, fields, purpose, necessity, steward, sensitivity ceiling, retention, residency, transformations, expected roles, vector contract, schema fingerprint, canonical definition/hash and assertion class.
24. `ai_release_manifests` references a system version and stores schema version, canonical manifest, manifest hash and evidence cutoff. The manifest is a release snapshot, not a mutable settings screen.
25. `ai_deployments` records system, environment, region, workload identity hash, status, active manifest identifier/hash and activation generation. Many deployments may refer to one system across environments.
26. `ai_approvals` ties a reviewer to a manifest. It records reviewer role, decision, rationale, evidence snapshot hash and evidence class. These are recorded attestations, not runtime gates.
27. `ai_evidence` binds deployment and manifest to an evidence descriptor, optionally referencing data-use revision and source profile. Fields include type, class, producer, provenance, content hash, evaluator version, redaction, retention, validity, collection time and idempotency key.
28. `ai_control_evaluations` references deployment, manifest, data use and optional evidence. It stores control identifier, status, evidence class, observed/expected JSON, reason code, evaluator version, input hash and idempotency key.
29. `ai_governance_incidents` references system, deployment and evaluation. It stores control identifier, deduplication key, severity, status, title, creation and resolution time.

### Constraints worth defending

Composite foreign keys in governance connect identifiers with organization and system context. This prevents a valid identifier from being attached to the wrong tenant or AI system. Unique constraints prevent duplicate version numbers, conflicting scoped identities and repeated idempotency keys. Check constraints restrict lifecycle and evaluation values.

Append-only models protect historical meaning. They do not mean every row in the database is immutable. A deployment pointer, user preference, incident status and evaluation state must change. The design separates current operational state from historical records whose meaning should remain stable.

Evidence: `backend/app/models`, especially `monitor.py` and `ai_governance.py`, and `backend/alembic/versions`. For an exact deployed schema, run migrations and inspect that database. This guide describes checked-in models, not an assertion about an unknown remote database.

## 11. Security, failure and operations

Workspace routing is a user experience boundary. Authorization is enforced on the server. A JWT carries identity and organization context, and protected queries must use that context. Another tenant's UUID must not become readable merely because someone guesses it. Staff authentication uses a separate identity type and portal.

Passwords and API keys are hashed. Source credentials must be decrypted for connection, so they use encryption rather than one-way hashing. HKDF derives a per-organization key from the master key and organization identifier. Fernet encrypts the serialized configuration.

The source comment claiming protection even if the master key leaks is too strong. With the master key and organization identifiers, an attacker can derive those keys. Per-organization derivation provides domain separation, not immunity to master-secret compromise. Key management, rotation, access restriction and incident response remain necessary.

Read-only database credentials limit source risk. SQL validation, timeouts and connector capability checks add layers. They do not remove the need for least-privilege source accounts, network controls or resource limits.

Retries require idempotency. A worker may crash after doing work but before acknowledgement. The typed run model has reservation and claim mechanisms to coordinate execution and preserve state. Inspect the actual implementation before claiming exactly-once behavior across the whole application. Exactly-once is a demanding end-to-end property, not a synonym for using a queue.

An external LLM outage should not erase the incident already persisted. Notification failure is separate from detection failure. The UI must make missing narration or delivery errors visible enough for an operator to act. Assignment notification still has known implementation debt in the project documentation.

Evidence: `backend/app/auth.py`, `backend/app/routers/auth.py`, `backend/app/services/crypto.py`, `backend/app/services/monitor_run_service.py`, `backend/app/tasks.py`.

## 12. Validation and evidence discipline

Use three layers of evidence. Unit tests isolate formulas, parsing and validation. Integration tests exercise database constraints, connectors and API behavior. Browser tests demonstrate the user-visible chain. A screenshot proves the displayed state at capture time, not the correctness of every backend branch.

The repository's minimum pre-commit command is `pytest tests/test_anomaly.py tests/test_llm.py` from the backend environment. That is not the full integration suite. Service-dependent tests can be skipped when dependencies are absent. A green result with skipped service lanes does not prove the Docker-backed paths work.

For a monitor demo, preserve the definition, validation result, activation, execution record and resulting incident. For alert delivery, show a real received local test email or corresponding delivery evidence. For governance, inspect provenance and status rather than only a colored score.

No fresh all-tests-passed claim is made here. Use dated evidence files and the current run's actual output. Historical local latency measurements are not a production SLA, concurrency benchmark or sustained-load result.

Evidence: `backend/tests`, `frontend/playwright`, `docs/evidence`, `docs/pfe/SOUTENANCE_MODE_EMPLOI.md`.

## 13. Likely jury questions with model answers

### Why is this a Big Data and AI PFE?

It combines heterogeneous data access, source-side aggregation, asynchronous processing and profile histories with statistical and multivariate detection. The language model assists investigation. I do not claim a distributed-volume benchmark that I have not run. The engineering is designed around controlling data movement and preserving useful evidence.

### What did you build beyond an ordinary dashboard?

The dashboard is the visible endpoint. Behind it are connector contracts, profiling, detector evaluation, typed monitor validation and compilation, immutable revisions, execution state and incident handling. The strongest demonstration is creating a rule and following its actual run, not displaying a pre-seeded count.

### Why both SQL and DSL?

SQL gives experienced users a precise scalar violation query within a restricted scope. The DSL makes policy and execution semantics explicit and allows versioning, schema binding and portable planning. They are separate paths with different audit guarantees, not two identical editors.

### Does Preview prove the rule passes?

No. It validates and compiles the plan. Activation binds a revision to that checked context. A subsequent run produces measurements. Confusing these steps would hide the most useful part of the lifecycle.

### Does the AI know the root cause?

It receives technical context and proposes likely causes and checks. The measured failure comes from the monitoring layer. A person verifies the explanation against source systems. Confidence labels are qualitative output, not established causal probabilities.

### Why not use only machine learning?

A missing table or explicit business constraint does not need a learned model. Rules are immediate and interpretable. Statistical methods help with unexpected changes when history exists. Combining methods covers different failure shapes, although it also requires controlling alert noise.

### How accurate are the detectors?

I can explain the formulas, thresholds and tested scenarios. I cannot honestly provide a global precision or recall number without labelled evaluation. The next evaluation should include normal business variation, injected failures, recovery and detection delay.

### Is AI governance complete?

No. It is an observe-only prototype for inventory, declared data use, release context, evidence and supported controls. It does not certify compliance or block every model request. Its value is making responsibility and evidence gaps visible instead of hiding them behind a green label.

### Why can a failed control have high confidence?

Confidence describes evidence quality in this heuristic. A reliable observation can clearly show a failure. Risk and confidence answer different questions.

### What happens if two users edit a monitor?

The API checks the expected revision. A stale edit can be rejected as a conflict. New revisions do not automatically replace the active revision. This preserves the execution contract until explicit activation.

### What happens if a worker crashes?

Queued execution and persisted run state provide recovery material. Claims and leases coordinate typed monitor ownership, and idempotency protects logical run identity. I would inspect retries and actual terminal state rather than promise exactly-once behavior for every side effect.

### Is customer data copied to your database?

The application primarily stores configuration, profiles and evidence rather than replicating business tables. Some connector paths inspect bounded values and metadata. That is why source permissions, context construction and external model privacy still require review.

### Is this deployed at Oyster?

The problem is informed by my software engineering work in the Payments team. The presented application uses synthetic demonstration data. I do not claim an Oyster production deployment.

### What would you improve first?

I would harden the core monitoring experience, repair known retry and notification gaps, build labelled detector evaluation and measure concurrent source workloads. I would expand connector support using conformance evidence. Governance enforcement would be a separate future project, not a checkbox added to the prototype.

## 14. Final rehearsal checklist

Explain the source and the application database as two different systems. Know the payment-status SQL query. Explain why the DSL threshold is 0.01. Distinguish Preview, Activate and Run. Show the run history before making a success claim.

Know z-score, Isolation Forest and STL well enough to state their inputs and limitations. Remember that seven observations are not automatically seven days. Explain the LLM as an assistant, not a cause detector. Explain governance as evidence and accountability, not certification.

Keep synthetic data clearly labelled. Avoid claiming every connector is equally mature. Preserve the line between implemented behavior, demonstrated behavior and planned improvement. That line makes the defense stronger because each claim has somewhere concrete to stand.
