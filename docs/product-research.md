# DataWatch — Product Research & Vision

> Saved from session 2026-06-05. Full reference for feature roadmap and product decisions.

## Product Thesis

DataWatch should become: **A cheaper, simpler, AI-first database observability tool for SaaS teams, agencies, SMBs, and client-facing developers.**

**Not:** A full enterprise Monte Carlo clone, full data catalog, full BI lineage platform, or full OpenMetadata replacement.

**Wedge:**
- Less setup
- Lower price
- Better AI explanations
- Better client reports
- Works directly on operational databases, not only data warehouses

---

## MVP Promise

> "Connect your database, DataWatch scans it, detects silent data problems, explains them with AI, and sends clean alerts/reports to your team or clients."

**MVP modules (8):**
1. Connectors
2. Schema discovery
3. Monitor engine
4. Metric snapshots
5. Anomaly detection
6. Incident system
7. Notifications
8. Reports

---

## Connector Tier Strategy

| Database | Launch Tier | Reason |
|---|---|---|
| PostgreSQL | **Tier 1** | Most important for SaaS, Rails, startups |
| MySQL / MariaDB | **Tier 1** | Very common in SMBs, Laravel, WordPress, e-commerce |
| MongoDB | **Tier 1** | Popular app DB, document drift is valuable differentiator |
| ClickHouse | Tier 2 | Popular analytics DB, important differentiator |
| SQL Server | Tier 2 | Common in traditional businesses |
| BigQuery | Tier 2 | Important warehouse |
| Snowflake | Tier 2 | Enterprise credibility |
| Cassandra | Tier 2/3 | Harder, partition-key aware queries needed |
| Redis | Tier 3 later | Not normal analytical source |
| Elasticsearch | Tier 3 later | Useful but not core MVP |
| Oracle | Later | Enterprise-heavy |
| Databricks | Later | Enterprise data stack |

---

## Core Monitor Types (Non-Negotiable)

| Monitor | SQL | MongoDB | Cassandra | ClickHouse |
|---|---|---|---|---|
| Freshness | Yes | Yes | Partial | Yes |
| Row/doc count | Yes | Yes | Partial | Yes |
| Null/missing rate | Yes | Yes | Yes | Yes |
| Duplicate key | Yes | Yes | Hard/partial | Yes |
| Schema drift | Yes | Yes | Yes | Yes |
| Type drift | Partial | Yes | Yes | Yes |
| Value range | Yes | Yes | Yes | Yes |
| Enum/category drift | Yes | Yes | Yes | Yes |
| Custom SQL | Yes | No | CQL later | Yes |
| Distribution drift | Yes | Yes | Later | Yes |

---

## AI Features (Workflow-Integrated)

### AI Feature 1: Incident Explainer
**Input:** metric history, current/expected values, table metadata, column metadata, recent schema changes, previous incidents

**Output:** Plain-English summary, business impact, likely causes, debug queries, client-safe explanation, technical explanation

### AI Feature 2: Monitor Generator
User clicks "Generate recommended monitors" → AI reads schema → proposes freshness/null/uniqueness/enum/range/business rule monitors → user approves

### AI Feature 3: Natural Language Rule Builder
```
User: "Every paid order should have a payment reference."
AI: SELECT COUNT(*) FROM orders WHERE status = 'paid' AND payment_reference IS NULL;
```

### AI Feature 4: Report Writer
3 versions: Technical | Executive | Client-safe (no internal table names)

### AI Feature 5: Debug Query Generator
Per incident: "Run this query to inspect affected rows."

---

## Monitor Detail Specs

### Freshness Monitor
```
table: orders
timestamp_column: created_at
expected_update_interval: 1 hour
grace_period: 15 minutes
severity: high
```

### Volume Monitor
Modes: total row count, rows inserted/updated last hour/day, partition count (ClickHouse)
Baseline: previous hour, same hour yesterday, same weekday average, rolling 7/30-day median
Alert if: z-score > threshold, value outside rolling min/max band, % change > threshold

### Schema Drift Monitor
Detect: column added/removed/renamed/type changed/nullable changed, index changed, FK changed
MongoDB: field added/disappeared/nested field type changed

### Distribution Drift Monitor
Track: min, max, avg, median approx, distinct count, top values, top value percentages
MongoDB: field presence %, field type %, top categorical values

### Duplicate Monitor
SQL: `GROUP BY ... HAVING COUNT(*) > 1`
MongoDB: aggregation pipeline
Support: single-column, composite uniqueness, approximate count, sample values

### Business Rule Monitor
SQL custom check + NL-to-SQL + failed row sample
Examples: `total_amount >= 0`, `paid orders must have paid_at`, `status IN ('active','cancelled','trialing')`

---

## Incident System MVP

**Lifecycle:** Detected → Open → Acknowledged → Investigating → Resolved → Ignored → Muted

**Incident page must show:**
- Title, Severity, Affected source/table/column
- Metric chart (expected vs actual vs historical baseline)
- First detected / last checked times
- AI explanation, suggested fix, sample failed records (if allowed)
- Notification history, comments, owner assignment
- Resolve button, Mute monitor button

---

## Reports MVP

| Report | Audience | Frequency |
|---|---|---|
| Daily digest | Internal team | Daily |
| Weekly reliability | Client/business | Weekly |
| Incident report | Client/team | Per incident |
| Monthly health | Client/management | Monthly |

**Weekly report must include:**
- Overall health score, tables monitored, incident counts by severity
- Resolved/open incidents, worst affected tables, top recurring issues
- Data freshness status, schema changes, recommended actions, AI summary

**Health score formula:**
```
weighted_score =
  critical_pass_rate * 0.50
  + high_pass_rate * 0.30
  + medium_pass_rate * 0.15
  + low_pass_rate * 0.05
```

---

## Multi-Client / Agency Mode

**Critical differentiator.** Most tools assume one company monitors its own data.

**Entities:** Organization → Workspace → Client → Project → Data source

**Roles:** Owner, Admin, Engineer, Analyst, Client Viewer, Report-Only Viewer

**Client sees:** Health score, open incidents, resolved incidents, reports, high-level summary
**Client does NOT see:** Database credentials, raw sensitive records, internal debug comments

---

## MVP UI Pages (Priority Order)

1. Dashboard (health score, open incidents, freshness failures, top risky tables)
2. Data Sources (CRUD, connection test, discovery)
3. Tables / Collections (list with health status)
4. Table Detail (row count trend, freshness, column list, monitors, incidents, AI monitor recommendations)
5. Monitors (dedicated monitor management page - **currently missing**)
6. Incidents (list with filters)
7. Incident Detail (full AI report + debug queries + history)
8. Reports (health score, weekly report, incident reports)
9. Notification Settings (alerts routing)
10. Workspace / Client Settings

**Currently missing from DataWatch UI:**
- Monitors page (create/manage/view individual monitors)
- Table description / owner fields
- MongoDB collection-specific detail view
- Client portal view

---

## Data Model (Recommended Additions)

```
data_assets (replaces monitored_tables for MongoDB support):
  source_id, asset_type (table/view/collection), database_name, schema_name,
  name, full_name, estimated_row_count, importance, owner, description

data_fields (replaces column_metrics JSONB):
  asset_id, name, path, data_type, nullable,
  detected_presence_rate, is_primary_key, is_indexed

monitors (dedicated monitor model - currently implicit):
  workspace_id, source_id, asset_id, field_id,
  monitor_type (freshness/volume/null_rate/duplicate/schema_drift/value_range/enum_drift/custom_sql),
  name, config_json, severity, enabled, schedule, last_run_at

metric_snapshots (persist individual metric values):
  monitor_id, asset_id, field_id,
  metric_name, metric_value, sample_size, measured_at, metadata_json
```

---

## Sampling Strategy

For every monitor, support:
- Full scan, Limited scan, Recent rows only, Sampled scan, Partition scan, Custom WHERE clause

Default: recent rows only where timestamp column exists, sampled scan otherwise

For big tables: warn "This table has 200M rows. Use recent-window monitoring or custom filters."

**Selling point:** Safe monitoring that does not overload production databases.

---

## Security Must-Have

- Read-only database users (warn if write permissions detected)
- Encrypted credentials (HKDF per-org Fernet keys — already implemented)
- No data modification (DataWatch cannot change your data)
- Query timeouts
- Row sample redaction
- PII masking in reports
- Workspace-level permissions

---

## Notification Channels (Priority)

**Must have now:** Email, Slack, Webhook
**Strong differentiator for MENA:** WhatsApp (later)
**Enterprise:** Microsoft Teams, PagerDuty (already implemented)

**Notification content:**
```
[High] orders.payment_status null spike
What happened: Nulls increased from 0.8% to 17.2%.
Impact: Payment reporting may be wrong.
Likely cause: Recent checkout/webhook change.
Actions: View incident | Acknowledge | Mute
```

---

## What NOT to Build (Yet)

- Full data catalog / column-level lineage
- BI integrations (Metabase, Tableau, Looker)
- Kafka / streaming observability
- Oracle connector
- SAML/SSO (post-Enterprise customers)
- dbt integration (post-first-paid-users)
- CDC-based deletion tracking
- Full OpenMetadata-style governance
- Complex agent framework

---

## Target Customers

### 1. SaaS Founders & Small Engineering Teams (2–20 engineers)
**Pain:** Dashboards break silently. Billing data goes wrong. No data engineer.
**Message:** *Know when your product data breaks before customers or investors notice.*

### 2. Agencies & Freelancers
**Pain:** Maintain client databases with no professional monitoring layer.
**Message:** *Give every client a professional database health report. Automatically.*

### 3. E-commerce & Operations
**Pain:** Orders, payments, inventory must be correct at all times.
**Message:** *Catch broken orders, missing payments, inventory mismatches automatically.*

### 4. Moroccan SMBs / MENA Market
**Pain:** Custom ERP/CRM, Excel exports, dashboards — but zero observability.
**Message:** *Simple database monitoring and WhatsApp/email reports for business owners.*

---

## Best Selling Lines

- *Catch silent database problems. Explain them with AI. Send reports clients understand.*
- *DataWatch monitors your databases like a data engineer, explains incidents like a senior analyst, and reports to clients like an account manager.*
- *Monte Carlo-style data reliability without enterprise pricing or enterprise setup.*
- *Database observability for teams that need trusted data but don't have enterprise budgets.*

---

## Feature Priority (Next Steps)

### Must build before selling
- [ ] Monitors page (dedicated monitor management UI)
- [ ] MongoDB Tier-1 deep view (field presence, type distribution in table detail)
- [ ] Table description/owner fields  
- [ ] Better incident detail with debug queries UI
- [ ] Deletion detection (row count drop + soft-delete column)
- [ ] Distribution drift visualization on table detail

### Strong launch additions
- [ ] Cassandra connector (safe, partition-aware)
- [ ] PDF report export
- [ ] Teams notifications (Microsoft Teams)
- [ ] WhatsApp alerts
- [ ] Client portal (read-only workspace view)
- [ ] Report scheduling UI
- [ ] Natural language rule builder UI

### After first paid users
- [ ] dbt integration
- [ ] Data contracts UI
- [ ] Report white-labeling
- [ ] Incident comments
- [ ] User assignment on incidents
- [ ] Cost-aware warehouse scan warnings
- [ ] SSH tunnel support
- [ ] Audit log

---

*Full research from session 2026-06-05. See also: docs/positioning.md, docs/marketing.md*
