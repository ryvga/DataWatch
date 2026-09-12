# Panopta, English slide script and presenter notes

Main presentation: slides 1 to 20. Reserve slides: 21 to 25. Suggested speaking time outside the video: 9 minutes. Rehearse the actual timed video script separately.

Keep the presentation concise. Read the SAY passages aloud, not the study notes or source references. Pause the video if the jury interrupts.

## Slide 1. Panopta

Target: 35 seconds.

### Say

Good morning. I am Mounir Gaiby, a Big Data and Artificial Intelligence student at ISGA Casablanca. I also work as a Software Engineer in Oyster’s Payments team. Today I will present Panopta, a data quality monitoring platform that combines configurable controls, anomaly detection and AI-assisted investigation. I thank Allah, my supervisor Professor HANINE MOHAMED, and everyone who supported this project.

### Presenter cue

Introduce yourself. Pause before naming the project.

### Understand before presenting

This is your final-year project, informed by your employment context. The demonstration uses synthetic data, not Oyster payment records.

### Likely jury question

Is Panopta deployed at Oyster?

This defense demonstrates an academic prototype locally. I do not claim an Oyster production deployment.

### Source pointers

Report introduction and professional context. Original ISGA and Oyster assets in docs/pfe/assets. Oyster media kit: https://www.oysterhr.com/media-kit

## Slide 2. Defense outline

Target: 15 seconds.

### Say

I will explain the problem and the main engineering choices, then show the application in action. The demonstration focuses on monitoring rather than a tour of menus. I will finish with the prototype’s limits and the next steps.

### Presenter cue

Keep the agenda brief. Detailed explanations come later.

### Understand before presenting

The order follows the report: context, analysis and design, implementation, validation and conclusion. Slides 21 to 25 are optional reserves.

### Likely jury question

What is the main contribution?

A traceable monitoring workflow that links source measurements, configurable checks, incident handling and structured AI explanations.

### Source pointers

docs/pfe/report_source.json and scripts/pfe/build_rapport_word.py

## Slide 3. Oyster and my Payments role

Target: 25 seconds.

### Say

At Oyster, I work as a Software Engineer in the Payments team, handling payment-related tasks. That context made data reliability a concrete engineering concern for me. A missing status can leave a payment difficult to interpret even when the system responds normally. Panopta explores how a monitoring tool can make those problems visible.

### Presenter cue

Say employment, not internship. Connect your work to the problem without sharing confidential systems.

### Understand before presenting

Oyster is the professional context. Acme is the synthetic demonstration workspace. They are not the same organization.

### Likely jury question

Did you use company data?

The recorded scenario uses local synthetic data. It illustrates payment-quality issues without exposing company records.

### Source pointers

User-provided professional role. Report section 1.1. Logo from https://www.oysterhr.com/media-kit

## Slide 4. Bad data can fail silently

Target: 25 seconds.

### Say

Consider the payment_status column. The table can remain available while an unusual number of values become null. Availability monitoring would miss that distinction. I need to observe the contents, compare them with explicit expectations or previous profiles, and preserve enough evidence for an engineer to investigate.

### Presenter cue

Point to the column name. Explain availability versus quality.

### Understand before presenting

A database health check answers whether the service responds. A quality monitor asks whether its data satisfies a rule or behaves as expected.

### Likely jury question

Why not check the application logs?

Logs explain application events, but they do not necessarily detect missing or inconsistent data produced by another pipeline or source. These checks complement logs.

### Source pointers

scripts/quickstart.py, backend/app/services/anomaly.py

## Slide 5. Requirements that shape the product

Target: 25 seconds.

### Say

The main user is an engineer responsible for a dataset. They need a connection that works, controls they understand, and a useful incident when something fails. Around that workflow, I added organization isolation, team ownership, notifications and reports. Those requirements determine both the data model and the interface.

### Presenter cue

Describe a user’s job, not a list of technologies.

### Understand before presenting

Functional requirements describe actions. Nonfunctional requirements include isolation, bounded execution, traceability and responsiveness.

### Likely jury question

What makes this a SaaS architecture?

Organizations share the platform while access and records remain scoped to a workspace. Roles, plans and staff administration support that shared-service model.

### Source pointers

Report analysis and architecture chapters, backend/app/models, frontend/src/App.jsx

## Slide 6. Three months of development, then continued work

Target: 20 seconds.

### Say

The report covers June through the end of August. I organized the work in increments, starting with the SaaS foundation and moving into profiling, detection, monitors and validation. The overlapping bars reflect iterative work. Panopta continues beyond that three-month period, especially around measurement and production readiness.

### Presenter cue

Show June to August, then point to the continuation line.

### Understand before presenting

This is a work-package summary, not a daily time sheet or a claim that every milestone finished on an exact date.

### Likely jury question

Why iterative development?

Each increment produced something testable, such as a migrated model or a browser flow. Feedback could influence the next implementation step.

### Source pointers

Report project organization, Git history and docs/tracking.md

## Slide 7. Source connection and discovery

Target: 25 seconds.

### Say

Monitoring begins at the source. The connector tests access and discovers the available structure. I then choose the tables and configure their cadence and freshness column. Capabilities are explicit because different database engines support different operations. PostgreSQL is the reference source in this demonstration.

### Presenter cue

Point to the discovered tables. Do not claim every advertised connector was tested in the video.

### Understand before presenting

Connection testing, discovery, profiling and typed execution are separate connector capabilities. A catalogue entry is not proof of production readiness.

### Likely jury question

How would you add another database?

Implement its connector contract, declare supported capabilities, test discovery and profiling, then validate execution and operational limits against a real instance.

### Source pointers

backend/app/connectors, backend/app/routers/sources.py, report implementation chapter, local screenshot

## Slide 8. Architecture and asynchronous execution

Target: 40 seconds.

### Say

React calls the FastAPI application. PostgreSQL stores organizations, monitored assets and their history. Long-running profiling work goes to Celery through Redis, so the browser does not wait for a full source scan. The worker calls the connector, saves the profile and evaluates the checks. A language model contributes an explanation after detection. This separation keeps the user interface independent from background execution.

### Presenter cue

Trace browser, API, worker, source and persistence in that order.

### Understand before presenting

Redis is the broker and cache. PostgreSQL is the durable application database. Celery workers execute tasks. The scheduler determines when profiling work starts.

### Likely jury question

Why Celery instead of Kafka?

The implemented workload is scheduled background work. Celery fits that requirement. Kafka would need a justified event-streaming use case and additional operational design.

### Source pointers

docker-compose.yml, backend/app/tasks.py, backend/app/scheduler.py, backend/app/worker.py

## Slide 9. A SQL check for missing payment statuses

Target: 35 seconds.

### Say

Here is a concrete business rule. This SELECT counts rows with a missing payment status. The legacy SQL monitor expects one nonnegative integer, so zero means no violations. The application validates the SQL structure and restricts its scope before execution. The aggregate stays close to the source. I receive a measurement rather than copying the entire business table into Panopta.

### Presenter cue

Read the query in plain language. Explain zero versus a positive count.

### Understand before presenting

The legacy SQL path is distinct from the typed DSL. It does not have the same immutable revision and run-history architecture.

### Likely jury question

Can users execute arbitrary SQL?

The supported rule is a restricted read-only SELECT with structural validation and source constraints. It is not a general SQL console.

### Source pointers

backend/app/routers/custom_monitors.py, backend/tests/test_legacy_sql_monitor.py

## Slide 10. Profiles preserve the table’s history

Target: 30 seconds.

### Say

A profile is a snapshot of measured properties, including row count, freshness and column statistics. Keeping those snapshots gives the table a history that the detectors can compare. The source performs aggregate work where possible. Some distributions need additional queries, so I do not claim that every profile always uses exactly one query.

### Presenter cue

Point to a trend and a column metric. Explain what the metric measures.

### Understand before presenting

Null rate is missing values divided by rows. Cardinality describes distinct values. Freshness measures time since a configured timestamp, subject to the source and timestamp semantics.

### Likely jury question

Does profiling copy all customer rows?

The main persisted evidence is aggregate profiles and metadata. Some profiling paths read bounded distributions. That differs from replicating the full source table.

### Source pointers

backend/app/services/profiler.py, backend/app/models/table_profile.py, local screenshot

## Slide 11. Typed monitors and traceable runs

Target: 40 seconds.

### Say

The DSL expresses a monitor as structured data. It separates the measurement, the breach condition and the operational policy. Preview validates and compiles a plan linked to the observed schema. It does not execute the data query. Activation pins a revision. An actual run then evaluates that revision and preserves its measurements and outcome. This makes a rule change explainable after the fact.

### Presenter cue

Clearly distinguish Preview, Activate and Run.

### Understand before presenting

DSL means domain-specific language. Here it is an allow-listed typed document, not Python or JavaScript execution. Track mode records outcomes without producing alert incidents.

### Likely jury question

What happens if I edit an active monitor?

A new draft revision does not silently replace the active revision. Activation is a separate action, so runs remain linked to the definition they used.

### Source pointers

backend/app/routers/monitor_dsl.py, backend/app/services/monitor_dsl.py, backend/tests/test_monitor_dsl_persistence_api.py

## Slide 12. Detection combines rules, statistics and ML

Target: 40 seconds.

### Say

Different defects leave different signals. Rules catch explicit conditions such as an empty table or a freshness breach. Statistical checks compare measurements with history. Isolation Forest adds a multivariate view when enough profiles exist. STL separates trend and seasonal structure before examining residuals. These methods produce signals for the incident workflow. Their presence alone does not establish accuracy. Precision and false positives still need an annotated evaluation.

### Presenter cue

Explain one example per family. Keep the deeper maths for questions.

### Understand before presenting

Z-score is a standardized deviation. Isolation Forest is unsupervised anomaly detection. STL is time-series decomposition. Its configured period is seven observations, not automatically seven days.

### Likely jury question

Is this supervised learning?

Isolation Forest does not require labeled anomaly examples for fitting. Labels would still be needed for an honest evaluation of detection quality.

### Source pointers

backend/app/services/anomaly.py and backend/tests/test_anomaly.py

## Slide 13. The LLM supports investigation

Target: 30 seconds.

### Say

Once the checks identify an incident, the narration service constructs a context from the available evidence. The language model returns a structured explanation with possible causes and recommended actions. The application validates that response. I treat the proposed cause as a hypothesis. The engineer still needs to inspect the pipeline or source and confirm what happened.

### Presenter cue

Point to a concrete recommendation and describe it as a next investigative step.

### Understand before presenting

Detection and narration are different components. The LLM does not establish the original failure by guessing from a screenshot.

### Likely jury question

What if the model hallucinates?

The prompt is grounded in measured context and the response has a validated structure, but that does not eliminate hallucinations. Human verification remains necessary.

### Source pointers

backend/app/services/llm.py, backend/tests/test_llm.py, local screenshot

## Slide 14. An incident connects evidence to ownership

Target: 25 seconds.

### Say

The incident page brings the evidence and the operational response together. I can inspect the signals, return to the affected table, read the analysis and assign responsibility. Acknowledgement means someone has taken notice. It does not prove that the data has recovered. That distinction matters when interpreting the incident state.

### Presenter cue

Point to signals, then ownership. Avoid equating acknowledgement with resolution.

### Understand before presenting

Deduplication limits repeated incident noise. Source measurements, run outcomes and incident lifecycle state answer different questions.

### Likely jury question

How do you avoid repeated alerts?

The incident and monitor policies use deduplication, consecutive-breach or recovery rules and cooldown behavior where supported. The exact policy belongs to the monitor path.

### Source pointers

backend/app/services/incident.py, frontend/src/pages/IncidentDetail.jsx, local screenshot

## Slide 15. AI governance is an exploratory prototype

Target: 35 seconds.

### Say

AI governance asks who owns an AI system, which version is in use, what data use is declared and what evidence supports the controls. In Panopta, this is a small observe-only prototype. It connects an inventory with versioned records, evidence and explainable control results. It does not certify compliance, measure fairness or block a model at runtime. Its purpose here is to test traceability and make missing evidence visible.

### Presenter cue

Lead with the purpose, then the prototype boundary. Do not apologize for a clearly scoped experiment.

### Understand before presenting

An evidence coverage score is not the probability that a model is safe. A declared data use is a customer assertion, not proof of actual runtime behavior.

### Likely jury question

How is this different from your LLM feature?

Narration uses AI to explain data incidents. Governance stores and evaluates information about AI systems and their supporting evidence. One consumes a model, the other tracks accountability.

### Source pointers

docs/ai-governance.md, backend/app/services/ai_governance.py, local screenshot

## Slide 16. Organization isolation and access control

Target: 30 seconds.

### Say

Each customer works within an organization context. The API uses authenticated identity and organization filtering to scope access. Roles control privileged operations, and the staff portal is separate from the customer workspace. Source credentials are encrypted with organization-derived keys. This is an application isolation design that must be tested with cross-organization requests, not assumed from the subdomain alone.

### Presenter cue

Separate routing, authentication, authorization and data scoping.

### Understand before presenting

A subdomain identifies the workspace but is not sufficient authorization. JWT claims need verification. A compromised master encryption key remains a serious compromise.

### Likely jury question

Do tenants have separate physical databases?

The application uses shared tables with organization scoping. The demo does not claim one physical application database per tenant.

### Source pointers

backend/app/auth.py, backend/app/routers/auth.py, backend/app/services/crypto.py

## Slide 17. Verification at several levels

Target: 25 seconds.

### Say

I use different checks for different questions. Unit tests exercise calculations and contracts. The browser demonstration verifies visible actions against the local stack. Integration tests are needed for persistence, authorization and background execution. I keep those forms of evidence separate. A successful local walkthrough does not establish a production service level or the accuracy of a detector.

### Presenter cue

Do not quote a historical count as a new full-suite result.

### Understand before presenting

Skipped tests are not passing feature evidence. Validation counts in the report have a date, environment and scope.

### Likely jury question

How would you test the detectors properly?

Use labeled scenarios and time-ordered evaluation, then report precision, recall, false positives and detection delay. Test different data shapes and drift conditions.

### Source pointers

backend/tests, frontend/playwright, docs/evidence and report validation chapter

## Slide 18. Panopta in action

Target: 10 seconds.

### Say

I will now show the monitoring workflow in the application. The data is synthetic. Watch how a configured rule becomes an executed result, then how the incident supports investigation and ownership.

### Presenter cue

Start Demo_Panopta_PFE_Action.mp4. Use DEMO_SCRIPT_EN.md for the timed narration. Resume at slide 19.

### Understand before presenting

Keep the video beside the PPTX. The slide contains a relative link. Open the MP4 directly if PowerPoint blocks it.

### Likely jury question

Is this a simulated interface?

The recording captures the local application and real actions on synthetic demo data. It is not a rendered product mockup.

### Source pointers

scripts/pfe/record_demo.mjs and the recorded demo manifest

## Slide 19. What the prototype still needs

Target: 30 seconds.

### Say

The next work is measurable. I need an annotated evaluation for the detectors, realistic concurrency tests for profiling, and more operational evidence for experimental connectors. The governance prototype needs broader controls and stronger evidence collection. Those tasks continue after the PFE period. They are also how I would judge whether Panopta is ready for a real customer workload.

### Presenter cue

Name the next evaluation, not just a feature wish list.

### Understand before presenting

Production readiness includes security, backups, monitoring of the monitoring service, failure recovery and operating costs.

### Likely jury question

What would you prioritize first?

Validate one complete customer workflow under realistic load, with tenant-isolation tests, source budgets and clear recovery behavior. Then expand capabilities based on measured needs.

### Source pointers

Report limitations and perspectives, README.md, docs/connector-catalogue.md

## Slide 20. A foundation for reliable data operations

Target: 25 seconds.

### Say

Panopta brings data engineering, anomaly detection and AI assistance into one investigation workflow. The contribution is the connection between measured data quality, configurable controls, traceable execution and an engineer’s response. The prototype gives me a working foundation and a clear set of measurements for the next stage. Thank you. I am ready for your questions.

### Presenter cue

Stop here. Open reserve slides only when they answer a question.

### Understand before presenting

Your central claim is a demonstrated prototype workflow, with explicit engineering choices and limitations.

### Likely jury question

What did you learn?

How to connect source-level data checks with asynchronous execution, durable evidence and an interface that helps an engineer act on a failure.

### Source pointers

Report conclusion and demonstrated application workflow

## Slide 21. The core database relationships

Reserve slide, use only when asked.

### Say

An organization owns sources. A source has monitored tables. Each table accumulates profiles, check results and incidents. Foreign keys connect those records, while organization scope constrains access. Additional families cover user access, alert routing, versioned monitors and AI governance. The study guide lists the complete application schema and its responsibilities.

### Presenter cue

Use this when asked about the database. Distinguish source data from Panopta metadata.

### Understand before presenting

PostgreSQL stores operational evidence and configuration. JSONB stores flexible structured metrics, while relational columns and constraints carry identities and relationships.

### Likely jury question

Why JSONB and relational tables together?

Column metrics vary by data type, which suits JSONB. Ownership, identity and lifecycle relationships need relational constraints and joins.

### Source pointers

backend/app/models, backend/alembic, docs/pfe/database_evidence.json

## Slide 22. A monitor run keeps its execution context

Reserve slide, use only when asked.

### Say

The user activates a validated revision, then requests a run. The API enqueues execution. The worker loads the pinned definition, uses the supported connector plan and persists measurements and evaluation state. Incident behavior then follows the policy. Keeping revision and plan identity lets me explain which rule produced a particular result.

### Presenter cue

Describe each stage without claiming exactly-once delivery.

### Understand before presenting

Queue delivery, idempotency and transactional persistence are related but different. A retry must not create contradictory duplicate state.

### Likely jury question

Why keep definition and plan hashes?

They identify the exact content and compiled plan associated with a run. They support comparison and audit, but are not a substitute for access control.

### Source pointers

backend/app/routers/monitor_dsl.py, backend/app/tasks.py, backend/app/models/monitor.py

## Slide 23. The rule, threshold and operational policy

Reserve slide, use only when asked.

### Say

This example measures the null rate of payment_status. A rate above one percent is a breach. The policy independently determines severity, consecutive breaches, recovery passes and cooldown. That separation matters because a measurement is a fact, while alerting behavior is an operational decision. The schema and supported connector capabilities still constrain execution.

### Presenter cue

Explain that 0.01 means one percent. The excerpt is illustrative and omits the outer document.

### Understand before presenting

The full document also needs the API version, kind, metadata and actual table identity. The internal datawatch.io/v1alpha1 namespace remains a compatibility identifier.

### Likely jury question

Why not let users write Python?

A typed, allow-listed document limits the executable surface and makes validation, compilation and audit more predictable. Arbitrary code would require a different isolation model.

### Source pointers

backend/app/services/monitor_dsl.py and backend/tests/test_monitor_dsl_persistence_api.py

## Slide 24. Collaboration and operational follow-up

Reserve slide, use only when asked.

### Say

The surrounding features support the operational workflow. Reports summarize reliability, teams make ownership explicit, and routing determines where an alert goes. MailHog provides local email-delivery evidence in the demonstration. That local receipt is useful verification, but it does not prove production email deliverability.

### Presenter cue

Use the video or app for detailed options rather than expanding the main presentation.

### Understand before presenting

Each integration needs its own delivery evidence. A visible channel option alone does not prove a live external integration.

### Likely jury question

What happens when an alert destination fails?

Delivery failures should remain visible and isolated from the stored incident. The incident evidence should not disappear because an external service is unavailable.

### Source pointers

backend/app/services/alert.py, frontend/src/pages/Reports.jsx, local screenshots

## Slide 25. The Big Data and AI contribution

Reserve slide, use only when asked.

### Say

The project fits Big Data and AI through its processing choices and model use. Aggregation near the source reduces data movement. Asynchronous workers separate collection from the interface. Historical profiles support statistical and multivariate detection. The LLM helps interpret incidents, while governance explores traceability around AI systems. I have not yet demonstrated distributed big-data throughput at production scale.

### Presenter cue

Explain the mechanism before naming a technology.

### Understand before presenting

Kafka is not implemented in this version. Large-scale processing suitability and measured large-scale performance are different claims.

### Likely jury question

Why call it Big Data if the demo is small?

The work applies relevant engineering patterns to heterogeneous data and monitoring workloads. The demo verifies behavior. A separate controlled benchmark is needed to establish scale.

### Source pointers

Report architecture and conclusion, backend/app/connectors, backend/app/services/anomaly.py, docker-compose.yml
