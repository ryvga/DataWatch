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
Keys are created at registration and prefixed `dw_`. Shown **once**. Only bcrypt hash stored.

### JWT Bearer (SPA session)
```
Authorization: Bearer <jwt>
```
Obtain via `POST /auth/login`. Expires in 15 minutes.

---

## Auth Endpoints

### `POST /auth/register`
Create org + admin user. Returns API key (shown once).

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
  "api_key": "dw_abc123..."   // save this — never shown again
}
```

Errors: `409` slug already taken.

---

### `POST /auth/login`
Exchange email + password for JWT.

```json
// Request
{ "email": "admin@acme.com", "password": "secret123" }

// Response 200
{ "access_token": "<jwt>", "token_type": "bearer" }
```

Errors: `401` invalid credentials.

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
Returns connector metadata for dynamic UI forms: required fields, optional defaults, provider labels, version choices, and field input hints.

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

Errors: `501` for Snowflake stub.

---

### `POST /api/v1/sources/{id}/discover`
Discover all schemas and tables. Caches result in Redis for 30 minutes.

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
Add a table to monitoring. Enqueues first profile run immediately, creates an APScheduler job, and stores a table schema snapshot when DDL is available.

```json
// Request
{
  "source_id": "uuid",
  "schema_name": "public",
  "table_name": "orders",
  "freshness_column": "created_at",     // optional — enables freshness checks
  "check_interval_minutes": 60,         // default: 60
  "sensitivity": 3.0,                   // z-score threshold, default: 3.0
  "dbt_model_yaml": null                // optional — enriches LLM context
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
  "latest_profile": null
}
```

Errors: `402` plan table limit exceeded.

---

### `GET /api/v1/tables`
List all monitored tables with latest profile summary.

---

### `GET /api/v1/tables/{id}`
Table details + latest profile.

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
| 501 | Not implemented (Snowflake stub) |
| 502 | Bad gateway (alert delivery failed) |
