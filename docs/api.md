# DataWatch — API Reference

Base URL: `http://localhost:8000` (dev) | `https://<railway-url>` (prod)
Docs UI: `GET /docs` (Swagger) | `GET /redoc`

---

## Authentication

Two methods, both work on all protected routes:

### API Key (programmatic / default for demo)
```
x-api-key: dw_<32-byte-hex>
```
Keys are staff/API-key managed and prefixed `dw_`. Only bcrypt hashes are stored.

### JWT Bearer (SPA session)
```
Authorization: Bearer <jwt>
```
Obtain via `POST /auth/login`. Expires in 8 hours.

---

## Auth Endpoints

### `POST /auth/register`
Create org + owner user.

```json
// Request
{
  "org_name": "Acme Corp",
  "org_slug": "acme",         // unique, URL-safe
  "email": "admin@acme.com",
  "password": "secret123"
}

// Response 201
{
  "org_id": "uuid",
  "org_slug": "acme",
  "message": "Workspace created. Sign in to continue."
}
```

Errors: `409` slug already taken.

---

### `POST /auth/login`
Exchange email + password for JWT.

```json
// Request
{ "org_slug": "acme", "email": "admin@acme.com", "password": "secret123" }

// Response 200
{ "access_token": "<jwt>", "token_type": "bearer", "org_slug": "acme", "org_name": "Acme Corp", "user_role": "owner" }
```

Errors: `401` invalid credentials.

### `GET /api/v1/realtime/ws`

Authenticated WebSocket transport for browser live updates. The browser passes
the same short-lived JWT used by the SPA as a query parameter because browser
WebSocket handshakes cannot set an `Authorization` header portably:

```
wss://<host>/api/v1/realtime/ws?token=<jwt>
```

The server verifies the token, active user, and workspace membership before
accepting the connection. Missing, expired, non-user, or cross-workspace tokens
close with WebSocket code `1008`. Clients may send `ping` or `heartbeat`; the
server replies with `realtime.pong`.

Every accepted connection starts with a versioned envelope:

```json
{
  "version": 1,
  "id": "org:event:timestamp",
  "type": "realtime.connected",
  "orgId": "uuid",
  "timestamp": "2026-08-21T02:00:00Z",
  "payload": {"transport": "websocket"}
}
```

Workers publish events through Redis (`datawatch:realtime:v1`); the API fans
them out only to sockets for the same `orgId`. Current event types include
`profile.completed`, `monitor.run.completed`, `incident.updated`,
`alert.dispatched`, `alert.route.updated`, `alert.tested`, and
`realtime.connected`. Events are hints to refetch authoritative API records,
not a replacement for persistence. The frontend automatically reconnects with
bounded exponential backoff and falls back to its existing polling refreshes
when WebSockets or Redis are unavailable.

### Webhook delivery contract

Generic webhook routes receive compact, deterministic JSON with
`Content-Type: application/json`, `User-Agent: Panopta-Webhook/1.0`,
`X-Panopta-Event`, and `X-Panopta-Event-Id`. When a signing secret is configured,
`X-Panopta-Signature` is `sha256=<hex HMAC-SHA256>` over the exact UTF-8 request
body bytes. Consumers should verify the body before parsing JSON and reject
replayed event IDs according to their own retention policy. The Settings →
Alerts form links to webhook.site for disposable receiver testing; remove the
route after verification.

---

## Infrastructure

### `GET /health`
No auth required. Returns DB + Redis + scheduler status.

```json
{
  "status": "ok",
  "db": "connected",
  "redis": "connected",
  "scheduler_jobs": 3
}
```

---

## Org

### `GET /orgs/me`
Returns current org. Auth: JWT.

```json
{ "id": "uuid", "name": "Acme Corp", "slug": "acme", "plan": "free" }
```

---

## Data Sources — `/api/v1/sources`

All endpoints: Auth JWT.
`connection_config` is **never** returned in any response.

### `POST /api/v1/sources`
Register a new warehouse connection. The connection must pass testing before the source is saved.

```json
// Request
{
  "name": "Production Postgres",
  "type": "postgres",               // postgres | bigquery | duckdb | snowflake
  "connection_config": {
    // postgres:
    "host": "db.example.com",
    "port": 5432,
    "database": "mydb",
    "username": "readonly_user",
    "password": "secret"

    // bigquery:
    // "credentials_json": { ...service_account_json... },
    // "project_id": "my-project"

    // duckdb:
    // "path": ":memory:" or "/data/my.duckdb"
  }
}

// Response 201
{
  "id": "uuid",
  "name": "Production Postgres",
  "type": "postgres",
  "status": "connected",            // connected | error | stub | pending
  "last_connected_at": "2026-06-04T10:00:00Z"
}
```

Errors: `400` invalid type, missing required connection fields, or failed connection test. `402` plan limit exceeded.

---

### `POST /api/v1/sources/test-connection`
Test an unsaved connection configuration before storing credentials. Auth: JWT.

```json
// Request
{
  "type": "postgres",
  "connection_config": {
    "host": "db.example.com",
    "port": 5432,
    "database": "mydb",
    "username": "readonly_user",
    "password": "secret"
  }
}

// Response 200
{ "connected": true, "latency_ms": 42, "error": null }
```

---

### `GET /api/v1/sources/connector-types`
Returns connector metadata for dynamic UI forms: required fields, optional defaults,
provider labels, version choices, field input hints, readiness, and capabilities.

`readiness` is one of `stable | beta | experimental | planned`. `capabilities`
separately reports `connection_test`, `discovery`, `schema`, `profiling`
(`none | core | full`), `custom_monitors` (`none | legacy_sql_scalar`), and
`sampling`. Only PostgreSQL, DuckDB, and SQLite currently expose the restricted legacy
SQL monitor path.

Oracle is returned as `experimental` with `profiling=core`. Its dynamic form includes
`host`, `port`, `service_name`, `username`, secret `password`, optional exact `schema`,
verified TLS mode, optional secret wallet password, and bounded connect/call timeouts.
The API never returns a saved connection configuration. In production, any Oracle wallet
directory must resolve under the deployment's `ORACLE_WALLET_ROOT`.

---

### `GET /api/v1/sources`
List all sources for current org.

---

### `GET /api/v1/sources/{id}`
Source details + connection status.

---

### `DELETE /api/v1/sources/{id}`
Sets `status = paused`. Does NOT delete — preserves all profile history.

---

### `POST /api/v1/sources/{id}/test`
Run live connection test.

```json
// Response 200
{ "connected": true, "latency_ms": 42, "error": null }
```

Managed warehouse connection failures return a secret-safe unsuccessful test result;
only an adapter that still raises `NotImplementedError` maps to `501`.

---

### `POST /api/v1/sources/{id}/discover`
Discover all schemas and tables. Caches the result in Redis for 30 minutes using a
tenant-scoped key. Ownership is checked before both fresh discovery and cached reads.

```json
// Response 200
{
  "schemas": [
    {
      "name": "public",
      "tables": [
        { "name": "orders", "estimated_rows": 482000 },
        { "name": "users", "estimated_rows": 5000 }
      ]
    }
  ]
}
```

---

### `GET /api/v1/sources/{id}/schemas`
Returns cached discovery result. Triggers fresh discover if cache is stale.

---

### `GET /api/v1/sources/{id}/table-schema`
Returns DDL-like schema text for a discovered table.

Query params: `schema_name`, `table_name`.

```json
{
  "source_id": "uuid",
  "schema_name": "public",
  "table_name": "orders",
  "ddl": "CREATE TABLE public.orders (...);"
}
```

---

## Monitored Tables — `/api/v1/tables`

### `POST /api/v1/tables`
Add a table to monitoring. Enqueues first profile run immediately, starts Table Autopilot for safe baseline + AI recommendations, creates an APScheduler job, and captures a server-owned schema snapshot directly from the connector. Creation fails with 422 before persistence or task dispatch when the snapshot cannot be captured/parsed or when `freshness_column` is absent from the snapshot.

```json
// Request
{
  "source_id": "uuid",
  "schema_name": "public",
  "table_name": "orders",
  "freshness_column": "created_at",     // optional — enables freshness checks
  "check_interval_minutes": 60,         // default: 60
  "sensitivity": 3.0                    // z-score threshold, default: 3.0
}

// Response 201 — includes latest_profile if available
{
  "id": "uuid",
  "source_id": "uuid",
  "schema_name": "public",
  "table_name": "orders",
  "freshness_column": "created_at",
  "check_interval_minutes": 60,
  "sensitivity": 3.0,
  "is_active": true,
  "last_profiled_at": null,
  "latest_profile": null,
  "autopilot": {
    "status": "queued",
    "recommended_next_action": "Profiling and AI monitor recommendations are queued.",
    "steps": {
      "profile": { "status": "queued" },
      "safe_baseline": { "status": "pending" },
      "recommendations": { "status": "queued", "staged_count": 0 },
      "alerts": { "status": "pending" }
    },
    "safe_monitors": [],
    "recommendations": []
  }
}
```

`schema_snapshot` is response-only. The deprecated request field `dbt_model_yaml` is
rejected with 422 instead of being trusted as connector metadata. Updating a freshness
column refreshes the live snapshot and validates the column before changing the table.

Existing tables created before Table Autopilot return `autopilot.status = "not_started"` so the UI can still show the workflow and next action.

Errors: `402` plan table limit exceeded.

---

### `GET /api/v1/tables`
List all monitored tables with latest profile summary.

---

### `GET /api/v1/tables/{id}`
Table details + latest profile.

Profile responses include `profile_provenance` when the connector uses sampling or an
estimated population. For MongoDB this records `profile_mode=sampled_native`,
`count_mode=estimated`, `population_estimate`, `sample_strategy`, `sample_size`,
`sample_limit`, `sampled_bytes`, `sample_byte_budget`, `document_byte_limit`,
`oversized_sampled_count`, truncation flags, and `schema_mode=sampled`. Consumers must
present the population as an estimate and the field metrics as sampled observations,
not exact SQL counts or deterministic full-population schemas.

---

### `PATCH /api/v1/tables/{id}`
Update table config. All fields optional. Rescheduling APScheduler job if `check_interval_minutes` changes.

```json
{
  "freshness_column": "updated_at",
  "check_interval_minutes": 30,
  "sensitivity": 2.5,
  "is_active": false
}
```

---

### `DELETE /api/v1/tables/{id}`
Sets `is_active = false`. Removes APScheduler job. Preserves history.

---

### `POST /api/v1/tables/{id}/run`
Trigger immediate profile run. Returns Celery task ID.

```json
// Response 200
{ "task_id": "celery-uuid", "queued_at": "2026-06-04T10:00:00Z" }
```

---

### Legacy custom SQL monitors

`GET|POST /api/v1/tables/{id}/custom-monitors`,
`PATCH|DELETE /api/v1/tables/{id}/custom-monitors/{monitor_id}`, and
`POST /api/v1/tables/{id}/custom-monitors/{monitor_id}/run` manage the transitional
SQL monitor path. Only connectors reporting `custom_monitors=legacy_sql_scalar` accept
definitions.

The SQL must parse as exactly one `SELECT`, reference only the monitored table (CTEs are
allowed when their base tables stay in scope), avoid blocked side-effect functions, and
return exactly one row containing exactly one non-negative integer column. Empty,
multi-row, multi-column, boolean, string, fractional, negative, NaN, infinite, and
overflow results are execution errors rather than passing checks. Execution errors do
not auto-resolve incidents.

`POST /api/v1/tables/{id}/custom-check` applies the same contract for an ad hoc preview.

---

## Safe Monitor DSL — `/api/v2/monitors`

### `POST /api/v2/monitors/validate`

Validates a strict `datawatch.io/v1alpha1` JSON definition and resolves its `assetId`
inside the authenticated organization. The response includes `canonicalDefinition`, a
stable `definitionHash`, predicate/measurement statistics, and `capabilityPlan`.

Validation does not persist or execute the definition. It returns separate
`valid`, `compilationSupported`, `compatible`, and `activationSupported` states. A valid
grammar can therefore report structured schema/compiler issues such as
`field_not_found`, `field_type_not_supported`, or `schema_snapshot_missing` without
being treated as malformed. Unknown grammar fields return 422, while an asset outside
the tenant returns 404.

### `POST /api/v2/monitors/preview`

Validates the same definition and, when compatible, returns `compiledPlan` plus a
short-lived HMAC attestation. The plan contains preview-only SQL, ordered typed parameter
metadata, logical-to-physical output bindings, and an exact-one-row result contract. It
is not a connector driver execution contract. The attestation expires after five minutes
and is bound to the tenant, asset, canonical definition hash, latest successful schema
fingerprint, and planner version. Any bound-context change makes activation reject it.
An incompatible validation-only preview contains structured issues but no attestation.

### `POST /api/v2/assets/{asset_id}/monitors`

Creates a draft monitor and immutable revision 1. The definition target must match the
asset path. Monitor names are unique per tenant and asset; conflicts return 409.

### `GET /api/v2/assets/{asset_id}/monitors`

Lists the tenant's monitors for the asset with each current canonical revision.

### `GET /api/v2/monitors/{monitor_id}`

Returns stable monitor identity, lifecycle status, current edit revision, nullable active
revision ID, canonical definition, hashes, schema fingerprint, and timestamps.
Cross-tenant IDs return 404.

### `PUT /api/v2/monitors/{monitor_id}`

Creates a new immutable revision. The body is
`{"expectedRevision": 1, "definition": {...}}`; the expected revision provides
compare-and-swap concurrency control. The target asset cannot change. Stale or unchanged
definitions return 409.

### Revision and run history

- `GET /api/v2/monitors/{monitor_id}/revisions`
- `GET /api/v2/monitors/{monitor_id}/revisions/{revision}`
- `GET /api/v2/monitors/{monitor_id}/runs`

Revision history is newest first. Runs are capped at the latest 250 and include trigger,
ordering, plan/revision/schema audit context, attempt count, sanitized error code,
measurements, and versioned policy result. Profile-triggered runs and operator-triggered
manual runs use the same idempotent state machine and active-revision pinning.

### `POST /api/v2/monitors/{monitor_id}/run`

Queues one manual run for the active revision. The request body is
`{"clientIdempotencyKey": "..."}`; reusing the key returns the original run rather
than creating a duplicate. The endpoint returns `202` with the persisted run ID and
current state. Draft or unsupported monitors are rejected without creating a run.

### `POST /api/v2/monitors/{monitor_id}/activate`

Requires `expectedRevision` and the matching `previewAttestation`. It verifies the
current tenant, asset, definition, schema, and planner context, then binds the immutable
revision to the table's existing profile cadence for PostgreSQL, DuckDB, and SQLite
compiled runtimes. A supported activation returns the active revision pointer and
schedule metadata; incompatible or unsupported connector plans remain fail-closed.

---

### `GET /api/v1/tables/{id}/profiles`
Paginated profile history. Excludes `column_metrics` blob for list performance.

Query params: `limit` (default 50, max 250), `cursor` (ISO timestamp for pagination)

```json
[
  {
    "id": "uuid",
    "collected_at": "2026-06-04T09:00:00Z",
    "row_count": 482134,
    "freshness_seconds": 3541.2,
    "schema_fingerprint": "abc123def456",
    "profiling_duration_ms": 340,
    "error": null
  }
]
```

---

### `GET /api/v1/tables/{id}/profiles/{profile_id}`
Full profile including `column_metrics` JSONB.

---

### `GET /api/v1/tables/{id}/checks`
Paginated check results history.

Query params: `limit` (default 100, max 500), `cursor`

```json
[
  {
    "id": "uuid",
    "profile_id": "uuid",
    "check_type": "z_score",
    "check_name": "z_score_row_count",
    "column_name": null,
    "status": "failed",
    "observed_value": 0.0,
    "expected_range": { "low": 420.5, "high": 581.3 },
    "deviation_score": -15.2,
    "checked_at": "2026-06-04T09:01:00Z"
  }
]
```

---

## AI Governance Phase One — `/api/v1/ai`

All routes require a workspace JWT and return `404` for cross-tenant identities. Phase one
is observe-only: activation records an exact manifest context but never blocks an external
deployment.

| Method | Route | Contract |
|---|---|---|
| `GET/POST` | `/systems` | List or register stable AI-system identity, purpose, owners, lifecycle, and risk context |
| `GET/PATCH` | `/systems/{id}` | Inventory detail/evidence timeline or mutable identity update |
| `POST` | `/systems/{id}/versions` | Append one canonical system version; raw prompts/outputs are rejected |
| `POST` | `/system-versions/{id}/data-use-revisions` | Append a verified asset/field declaration labeled `customer_assertion` |
| `POST` | `/system-versions/{id}/release-manifests` | Create/replay an immutable canonical manifest and SHA-256 hash |
| `POST` | `/release-manifests/{id}/reviews` | Append a non-gating reviewer decision and evidence snapshot hash |
| `POST` | `/systems/{id}/deployments` | Register an environment/region/workload identity hash |
| `POST` | `/deployments/{id}/activate-manifest` | Compare-and-swap the exact manifest ID/hash and activation generation |
| `POST` | `/deployments/{id}/evaluate` | Run deterministic ownership, schema/freshness, role/grant, and vector controls |
| `GET` | `/systems/{id}/evidence` | Return up to 250 append-only terminal results with evidence class and replay hash |

Activation requires `manifest_id`, the same 64-character `manifest_hash`,
`expected_generation`, and the expected previous active hash. A stale writer receives
`409`. Evaluation requires a client idempotency key and accepts bounded timeout and scan
budget values. Results preserve six distinct states: `pass`, `fail`, `unknown`,
`unsupported`, `not_applicable`, and `error`.

For a PostgreSQL RAG declaration, `vector_contract` identifies only verified schema fields
and another monitored table on the same source. The connector runs one read-only aggregate,
returns counts and role metadata, and never returns rows or embeddings.

## Incidents — `/api/v1/incidents`

### `GET /api/v1/incidents`
List incidents. All query params optional.

Query params: `status` (open|acknowledged|resolved), `severity` (P1|P2|P3), `table_id`, `limit` (default 50)

```json
[
  {
    "id": "uuid",
    "table_id": "uuid",
    "severity": "P1",
    "status": "open",
    "title": "[P1] orders — row count dropped to 0",
    "fired_checks": [
      { "check_name": "row_count_zero", "observed_value": 0, "deviation_score": null }
    ],
    "llm_narration": {
      "summary": "The orders table stopped receiving data...",
      "likely_causes": [...],
      "impact_assessment": "...",
      "recommended_actions": [...],
      "data_pattern_notes": "...",
      "confidence": "high"
    },
    "created_at": "2026-06-04T09:01:00Z",
    "acknowledged_at": null,
    "resolved_at": null
  }
]
```

`llm_narration` is `null` while the Celery task is still running (NarrationPanel polls every 3s).

---

### `GET /api/v1/incidents/{id}`
Full incident detail.

---

### `PATCH /api/v1/incidents/{id}/acknowledge`
Sets `status = acknowledged`, `acknowledged_at = now`. Errors: `409` if not open.

---

### `PATCH /api/v1/incidents/{id}/resolve`
Sets `status = resolved`, `resolved_at = now`. Errors: `409` if already resolved.

---

## Alert Configs — `/api/v1/alerts`

### `POST /api/v1/alerts`
Create alert routing rule.

```json
// Slack
{
  "table_id": null,              // null = org-wide, UUID = table-specific
  "channel": "slack",
  "config": {
    "webhook_url": "https://hooks.slack.com/services/...",
    "min_severity": "P2"         // P1|P2|P3 — fire for this severity and above
  }
}

// Email
{
  "channel": "email",
  "config": {
    "to": ["oncall@company.com"],
    "min_severity": "P3"
  }
}

// PagerDuty
{
  "channel": "pagerduty",
  "config": {
    "routing_key": "YOUR_ROUTING_KEY",
    "min_severity": "P1"
  }
}
```

---

### `GET /api/v1/alerts`
List all alert configs for current org.

---

### `DELETE /api/v1/alerts/{id}`
Soft-delete (sets `is_active = false`).

---

### `POST /api/v1/alerts/{id}/test`
Send a test alert to verify the channel config.

```json
// Response 200
{ "sent": true, "channel": "slack" }
```

Errors: `502` if the alert delivery failed (check webhook URL / routing key).

---

## Error Response Format

All errors follow this structure:

```json
// Standard error
{ "detail": "Human readable message" }

// Plan limit error (402)
{
  "detail": {
    "error": "plan_limit_exceeded",
    "resource": "sources",
    "limit": 1,
    "current": 1,
    "plan": "free",
    "upgrade_url": "https://datawatch.io/pricing"
  }
}
```

---

## HTTP Status Codes

| Code | Meaning |
|---|---|
| 200 | OK |
| 201 | Created |
| 204 | No content (DELETE) |
| 400 | Bad request (invalid input) |
| 401 | Unauthorized (invalid/missing credentials) |
| 402 | Payment required (plan limit exceeded) |
| 404 | Not found (also used for access-denied — no info leak) |
| 409 | Conflict (duplicate slug, already acknowledged, etc.) |
| 501 | Connector path explicitly not implemented |
| 502 | Bad gateway (alert delivery failed) |
