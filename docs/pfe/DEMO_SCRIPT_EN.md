# Panopta action demo, timed English narration

Video duration: 03:32. The recording is silent. Speak the text below while it plays.

The timestamps follow the final recording. Start speaking when each caption appears. Keep a measured pace. If an action finishes before your sentence, continue speaking and let the screen remain visible.

## 00:00 to 00:10. PANOPTA  /  From a signal to a controlled response

Panopta monitors data quality. This demonstration uses a synthetic e-commerce workspace, not Oyster production data. I will connect the source, inspect a table, and execute two kinds of monitors.

Screen: `01-operations`. Route: `http://acme-corp.localhost:5173/`.

## 00:10 to 00:16. 01  /  Test the live PostgreSQL connection

The source is a live PostgreSQL database. Connection testing checks that Panopta can actually reach it.

Screen: `02-source`. Route: `http://acme-corp.localhost:5173/settings?tab=sources`.

## 00:16 to 00:23. Capabilities, not interchangeable connector promises

The catalogue exposes different database engines. Support is capability-based, with PostgreSQL as the stable demonstration path.

Screen: `03-connectors`. Route: `http://acme-corp.localhost:5173/settings?tab=sources`.

## 00:23 to 00:31. Discover the schema and configure the profiling cadence

Schema discovery supplies the available structure. The monitoring setup also controls the timestamp, cadence, and sensitivity.

Screen: `04-discovery`. Route: `http://acme-corp.localhost:5173/settings?tab=tables`.

## 00:31 to 00:38. 02  /  Profile 8,500 orders without exporting the table

The table view brings together volume, freshness, and historical profiles. Aggregates are computed on the source, while snapshots support later comparisons.

Screen: `05-profile`. Route: `http://acme-corp.localhost:5173/tables/f98af3f1-2a67-4ec4-ae4a-59917b2f0627`.

## 00:38 to 00:45. Filter the columns and inspect completeness

The payment status column is entirely null in this injected scenario. Filtering isolates the evidence instead of scanning every column.

Screen: `06-columns`. Route: `http://acme-corp.localhost:5173/tables/f98af3f1-2a67-4ec4-ae4a-59917b2f0627`.

## 00:45 to 00:53. Statistical detectors, ML detectors, and explicit exclusions

Built-in checks combine statistical methods with Isolation Forest and seasonal analysis when enough history exists. Operators can tune checks and exclude columns.

Screen: `07-built-in`. Route: `http://acme-corp.localhost:5173/tables/f98af3f1-2a67-4ec4-ae4a-59917b2f0627`.

## 00:53 to 01:04. 03  /  Write a read-only SQL quality rule

Now I define an explicit business rule. The query counts orders whose payment status is missing, and the monitor runs with each profile.

Screen: `08-sql-editor`. Route: `http://acme-corp.localhost:5173/tables/f98af3f1-2a67-4ec4-ae4a-59917b2f0627`.

## 01:04 to 01:11. Test SQL  /  Real violation count before saving

The test executes against PostgreSQL and returns the actual violation count. Saving is gated on testing the current query.

Screen: `09-sql-test`. Route: `http://acme-corp.localhost:5173/tables/f98af3f1-2a67-4ec4-ae4a-59917b2f0627`.

## 01:11 to 01:18. Save the tested rule and execute it again

The tested SQL becomes a persistent monitor. I can run it immediately as well as on the automatic profiling cadence.

Screen: `10-sql-saved`. Route: `http://acme-corp.localhost:5173/tables/f98af3f1-2a67-4ec4-ae4a-59917b2f0627`.

## 01:18 to 01:29. 04  /  Build a typed, schema-bound DSL monitor

The typed DSL is a second approach. I select a completeness metric, bind it to payment status, and define a one-percent breach threshold.

Screen: `11-dsl-rule`. Route: `http://acme-corp.localhost:5173/monitors`.

## 01:29 to 01:40. Severity, execution mode, cadence, and recovery policy

The policy separates the measurement from operational behavior. Here it uses alert mode, high severity, and the profile trigger, with explicit breach and recovery counts. The definition keeps the default sixty-minute cooldown.

Screen: `12-dsl-policy`. Route: `http://acme-corp.localhost:5173/monitors`.

## 01:40 to 01:47. Validate  /  Compile  /  Inspect the immutable definition

Validation checks the schema and connector plan. The canonical JSON and definition hash identify exactly what will be activated.

Screen: `13-dsl-preview`. Route: `http://acme-corp.localhost:5173/monitors`.

## 01:47 to 01:56. Activate revision 1, then run the real worker

Activation makes the revision executable. Run now queues the monitor through the actual asynchronous runtime.

Screen: `14-dsl-active`. Route: `http://acme-corp.localhost:5173/monitors`.

## 01:56 to 02:04. Persist the execution result and its active revision

The table retains the active revision and latest run outcome. This creates a traceable connection between a rule, its execution, and the incident lifecycle.

Screen: `15-run-result`. Route: `http://acme-corp.localhost:5173/tables/f98af3f1-2a67-4ec4-ae4a-59917b2f0627`.

## 02:04 to 02:13. Trigger a fresh profile and continue the investigation

A manual profile uses the same monitoring pipeline as the scheduler. Processing is asynchronous, so the operator does not need to hold the page open.

Screen: `16-profile-run`. Route: `http://acme-corp.localhost:5173/tables/f98af3f1-2a67-4ec4-ae4a-59917b2f0627`.

## 02:13 to 02:20. 05  /  Open the incident and inspect its evidence

The incident connects severity, observed signals, and the affected table. The checks are evidence for investigation, not a diagnosis by themselves.

Screen: `17-incidents`. Route: `http://acme-corp.localhost:5173/incidents/5a34ed25-437f-495d-a020-3a1f28798225`.

## 02:20 to 02:27. Read the failed checks and the observed measurements

I inspect the failing checks and measurements first. This is how the reviewer can challenge the alert using the underlying observations.

Screen: `18-signals`. Route: `http://acme-corp.localhost:5173/incidents/5a34ed25-437f-495d-a020-3a1f28798225`.

## 02:27 to 02:34. AI explanation  /  Hypotheses, not automatic truth

The language model converts the incident context into a readable explanation. Its probable causes remain hypotheses that a person must verify.

Screen: `19-ai-analysis`. Route: `http://acme-corp.localhost:5173/incidents/5a34ed25-437f-495d-a020-3a1f28798225`.

## 02:34 to 02:41. Turn the analysis into concrete diagnostic actions

Recommended actions help the engineer choose what to inspect next. The value is operational guidance anchored in the detected signals.

Screen: `20-actions`. Route: `http://acme-corp.localhost:5173/incidents/5a34ed25-437f-495d-a020-3a1f28798225`.

## 02:41 to 02:48. Assign ownership without pretending the data is repaired

I assign the investigation to Data Engineering. Acknowledging an incident records ownership. It does not mean the underlying data has recovered.

Screen: `21-assignment`. Route: `http://acme-corp.localhost:5173/incidents/5a34ed25-437f-495d-a020-3a1f28798225`.

## 02:48 to 02:54. 06  /  Route alerts by channel and severity

Alert routes carry the incident to the operational team. The local demonstration includes real email delivery.

Screen: `22-alerts`. Route: `http://acme-corp.localhost:5173/settings?tab=alerts`.

## 02:54 to 03:00. An actual alert received in the local mailbox

This message was delivered to the local mailbox. It demonstrates the delivery path without contacting real customers.

Screen: `23-email`. Route: `http://localhost:8025/`.

## 03:00 to 03:06. Reliability reporting beyond a single incident

Reports summarize the workspace reliability and incident history. They provide the broader view after the detailed investigation.

Screen: `24-reports`. Route: `http://acme-corp.localhost:5173/reports`.

## 03:06 to 03:10. Team ownership and notification preferences

Teams structure responsibility. User preferences control how each person receives notifications.

Screen: `25-team`. Route: `http://acme-corp.localhost:5173/teams`.

## 03:10 to 03:13. Delivery preferences remain separate from detection

Notification settings are independent of the underlying detection logic.

Screen: `26-notifications`. Route: `http://acme-corp.localhost:5173/settings?tab=notifications`.

## 03:13 to 03:21. 07  /  AI governance is an observe-only prototype

The AI governance area is a small prototype. It tracks declared systems and evidence in observation mode, without claiming certification or automated compliance.

Screen: `27-governance`. Route: `http://acme-corp.localhost:5173/ai-systems/19409070-4091-5e21-90d3-bc21ee630655`.

## 03:21 to 03:26. Versioned context and an evidence timeline

The evidence timeline makes the declared context inspectable. Extending and validating this prototype remains future work.

Screen: `28-evidence`. Route: `http://acme-corp.localhost:5173/ai-systems/19409070-4091-5e21-90d3-bc21ee630655`.

## 03:26 to 03:32. Measure. Detect. Explain. Act.

The core contribution is this end-to-end chain: source-side profiling, explicit and statistical monitoring, traceable incidents, and assisted investigation.

Screen: `29-finish`. Route: `http://acme-corp.localhost:5173/monitors`.
