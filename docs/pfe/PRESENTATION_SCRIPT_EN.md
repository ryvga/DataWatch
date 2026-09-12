# Panopta PFE presentation, full English script

## Slide 1. Panopta

Good morning. My name is Mounir Gaiby. I am presenting Panopta, my final-year engineering project at ISGA Casablanca. Panopta is a multi-tenant SaaS for data quality monitoring and AI-assisted incident investigation. The project grew from a concrete concern in payment systems, where a database can remain available while the data inside it becomes unusable.

## Slide 2. Presentation structure

I will begin with the professional context and the problem. I will then explain the functional scope, the architecture, the asynchronous runtime, and the database model. After that, I will follow the product itself, from a connected source to a table profile, a monitor, an incident, and an operational response. I will finish with governance, validation, and the demonstration.

## Slide 3. Oyster and my role in Payments

I work at Oyster as a Software Engineer in the Payments team. This is a professional role, not an internship. Payment work depends on tables that describe amounts, currencies, statuses, references, and settlement dates. A service may answer normally while one of those fields becomes stale or empty. That gap between system availability and data reliability motivated Panopta.

## Slide 4. The silent data failure

Consider an orders table with 8,500 rows. The database responds, the API remains online, and no infrastructure alarm fires. Yet payment_status is null for every order. Operational dashboards become misleading, reconciliation loses meaning, and engineers discover the damage late. Panopta focuses on this exact class of failure, where the system runs but its data no longer supports the business process.

## Slide 5. Project objective and scope

The objective is to make a data problem visible, explainable, and assignable. Panopta connects to a source, discovers its schema, profiles selected tables, evaluates quality rules, and opens an incident when evidence crosses a defined threshold. The platform also routes alerts and stores the investigation history. It does not repair customer data automatically. The engineer remains responsible for diagnosis and remediation.

## Slide 6. Three-month development plan

The PFE development period ran from June through the end of August. June established the SaaS foundation, authentication, source connections, and profiling. July concentrated on detectors, monitor execution, and incident handling. August added the typed DSL, stronger connector contracts, AI governance, validation, and report evidence. Panopta remains an ongoing product, so performance studies and production hardening continue after the academic period.

## Slide 7. Panopta functional workflow

This workflow provides the structure for the rest of the presentation. First, an organization connects a source. Panopta discovers tables and stores the selected monitoring configuration. Profiling then produces compact measurements. Rules and detectors evaluate those measurements. A failure creates or updates an incident. Finally, the platform explains the evidence, assigns ownership, and sends the alert to the configured operational channel.

## Slide 8. System architecture

The React interface communicates with an asynchronous FastAPI backend. PostgreSQL stores tenants, source metadata, profiles, monitor revisions, runs, incidents, and governance evidence. APScheduler decides when tables are due. Celery workers execute profiling, detection, narration, and alert tasks through Redis. Source connectors perform bounded read-only operations. The language model receives structured incident context only after Panopta has persisted the observed checks.

## Slide 9. Asynchronous monitoring execution

A request does not hold the browser open while a large table is profiled. The API validates the request and queues a job. The worker loads the organization and source context, executes one aggregate profile query, persists the snapshot, and runs the configured checks. If those checks fail, Panopta updates the incident, generates the AI narration, and dispatches alerts. Every stage leaves a database record that can be inspected later.

## Slide 10. Database structure

The application database contains 29 ORM tables grouped into five domains. Identity and tenancy manage organizations, users, roles, keys, and invitations. Monitoring configuration covers sources, tables, and monitor definitions. Observation tables preserve profiles, check results, runs, and evaluation state. Operations store incidents, alert routes, notification preferences, and on-call ownership. The governance domain stores versioned AI systems, manifests, approvals, evidence, controls, and governance incidents.

## Slide 11. Core monitoring relationships

At the center of the model, an organization owns data sources. A source exposes monitored tables. Each profile belongs to one table and contains row count, freshness, schema fingerprint, and column metrics. Check results reference the observed profile. A typed monitor points to an immutable revision, while each run records the exact revision it executed. Failed evidence reaches an incident, which can accumulate repeated checks without creating duplicate open incidents.

## Slide 12. Tenant isolation and credential security

Every protected request resolves an organization from the user session. Queries then scope customer records with org_id. Roles separate owners, administrators, and members, while staff authentication uses a different portal. Panopta encrypts each source configuration with a key derived from the master secret and the organization identifier. This prevents one tenant from decrypting another tenant's source credentials through an ordinary application path.

## Slide 13. Sources and connector maturity

The product journey begins with a source. Panopta has adapters for relational databases, warehouses, document stores, Cassandra, and Redis. The catalogue does not pretend that every connector has the same maturity. PostgreSQL is the stable path used in this defense. DuckDB and SQLite are beta. The remaining implemented adapters are marked experimental until their operational promotion gates are satisfied.

## Slide 14. Connection and schema discovery

After storing the encrypted connection configuration, the operator tests the live connection. Panopta then discovers schemas and tables through the connector. The user selects public.orders, and the captured schema confirms that created_at is available for freshness monitoring. The table configuration stores the cadence, sensitivity, and freshness field. Discovery is the first product action built on top of the connector and tenant model.

## Slide 15. Table profiling

Once the table is registered, Panopta profiles it. The profiler builds a single aggregate query rather than loading rows into the application. It collects row count, freshness, null rates, distinct counts, numeric summaries, timestamp ranges, and text-length metrics. The application stores a compact snapshot for historical comparison. In this scenario, public.orders contains 8,500 rows and payment_status has reached a 100 percent null rate.

## Slide 16. Data quality detection

Panopta combines explicit expectations with historical detection. Rule checks catch empty tables, freshness breaches, schema drift, and large null-rate changes immediately. Z-scores compare current metrics with recent profiles. Isolation Forest looks for multivariate outliers after enough history exists. STL separates seasonal structure from unexpected residuals on daily series. The engine records the observed value, expected range, status, and deviation score for every check.

## Slide 17. Read-only SQL monitors

Some quality expectations are easiest to express with SQL. This monitor counts orders where payment_status is null. Panopta accepts a restricted, read-only scalar query and requires the current SQL to pass a test before saving. During the recorded run, PostgreSQL returned 8,500 violations. The rule can execute on demand and after each scheduled profile, but it cannot modify the source database.

## Slide 18. Typed monitor definition

The typed DSL provides a safer alternative to free-form SQL. This definition binds the null_rate metric to payment_status and marks a breach above 0.01, which means one percent. The policy sets P2 severity, requires one failing run, requires two passing runs for recovery, and applies a 60-minute cooldown. The compiler validates the field against the captured schema before activation.

## Slide 19. Monitor revisions and traceable runs

Validation produces a canonical definition and a stable hash. Activation freezes that document as revision 1 and points the monitor to it. A run records the revision, connector plan, idempotency key, timing, status, and measurements. This design lets an engineer answer two precise questions later. Which rule ran, and what evidence did that exact rule produce?

## Slide 20. Incident evidence and lifecycle

A failed check becomes operational through the incident lifecycle. Panopta opens one active incident per table, then appends repeated evidence instead of flooding the team with duplicates. Severity depends on the failed checks. The detail view shows the affected table, observed signals, status history, and ownership. Acknowledgement means that someone has taken responsibility. Resolution requires later recovery evidence or an explicit operational decision.

## Slide 21. AI-assisted incident analysis

For P1 and P2 incidents, Panopta builds a compact context from the table profile and fired checks. The language model returns structured JSON containing a summary, probable causes, impact, and recommended diagnostic actions. The backend validates that structure before storing it. These causes remain hypotheses. The model helps the engineer read the evidence faster, but it does not claim that a suggested cause has been proven.

## Slide 22. Operational response

The incident must reach a person who can act. Alert routes support email, Slack, PagerDuty, and signed webhooks with severity thresholds. Teams and on-call schedules define responsibility. Notification preferences control delivery without changing the detector itself. Reports then summarize health and incident history across the workspace. In the local demonstration, Panopta delivers a real alert to MailHog without contacting an external customer.

## Slide 23. AI governance prototype

Panopta also contains a small AI governance prototype. It records an AI system, its version, declared data uses, release manifests, deployments, approvals, evidence, and control evaluations. The interface calculates evidence confidence and residual risk from the available records. This module operates in observe-only mode. It surfaces missing or failed evidence and can create an incident, but it does not certify legal compliance and it does not block a deployment.

## Slide 24. Big Data, AI, and validation evidence

The Big Data contribution lies in connector-aware, source-side aggregation and asynchronous execution. Panopta stores measurements rather than copying full customer tables. The AI contribution combines anomaly detection with a structured LLM explanation layer and an evidence-oriented governance prototype. For this delivery, 67 targeted backend tests passed. The 26-slide package passed integrity and geometry checks. The recorded browser journey produced zero page errors and zero failed Panopta API responses.

## Slide 25. Product demonstration

I will now show the complete path in the running application. The demonstration uses a synthetic e-commerce workspace. It starts with the source and table, creates SQL and typed monitors, executes them, opens the incident, reviews the AI analysis, and finishes with alerting and governance.

## Slide 26. Conclusion and next work

Panopta proves the complete chain from a source measurement to an owned investigation. The current prototype connects real databases, profiles tables, evaluates explicit and statistical controls, preserves monitor revisions, opens incidents, and produces AI-assisted explanations. The next work is measurable. I need controlled scale tests, detector precision and recall studies, production recovery exercises, and broader governance evidence coverage. Thank you for your attention.
