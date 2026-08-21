# Realtime and alert delivery specification

This is the implementation contract for monitor activity, incident updates, and
alert routes. It is intentionally explicit about failure behavior: persistence
must remain correct even when the realtime broker or a destination is down.

## Normal flow

1. A monitor/profile task commits the authoritative database change.
2. The API or worker publishes a small org-scoped event to Redis.
3. Connected browser clients receive the event and refetch the affected record.
4. Alert dispatch evaluates route scope and minimum severity, sends each eligible
   destination, and records per-destination success/failure in the task result.

The event is an optimization and never the source of truth. A missed event is
safe because every affected screen retains its normal refresh path.

## Event contract

All events use `version: 1`, a unique `id`, an ISO-8601 `timestamp`, the owning
`orgId`, a stable `type`, and a JSON object `payload`. Payloads must contain
identifiers only (for example `tableId`, `monitorId`, `incidentId`) plus small
status fields. Do not put credentials, connector configuration, or full table
rows in an event.

Current types:

| Type | Producer | Browser response |
| --- | --- | --- |
| `profile.completed` | profiling task | refresh table/profile state |
| `monitor.run.completed` | DSL task | refresh monitor status and incidents |
| `incident.updated` | incident actions and anomaly task | refresh incident lists and notifications |
| `alert.dispatched` | alert task | refresh notification count |
| `alert.route.updated` | alert route CRUD | refresh route/configuration views |
| `alert.tested` | send-test endpoint | show the test result toast |
| `realtime.connected` | WebSocket handshake | mark live updates as connected |

## Authentication and tenancy

- The WebSocket accepts the same JWT as the SPA via `token` or `access_token`.
- The token must be a user token, unexpired, active, and match the requested
  organization. Invalid or cross-organization access closes with code `1008`.
- Redis fan-out filters by `orgId`; a socket must never receive another
  workspace's event.
- A reconnect must re-authenticate; no socket is resumed without a fresh token.

## Client state and recovery

The client exposes `idle`, `connecting`, `connected`, `reconnecting`,
`offline`, and `unsupported` states. It reconnects with bounded exponential
backoff (up to 30 seconds) and keeps the existing API polling refreshes active.
Malformed JSON, unknown event types, duplicate events, and stale events are
ignored or coalesced; subsequent fetches determine the current state. A server
restart, Redis outage, laptop sleep, tab suspension, or a temporary proxy that
drops `Upgrade` must therefore degrade to polling instead of blocking the UI.

## Webhook delivery

Generic webhook payloads are compact, deterministic UTF-8 JSON. If a secret is
configured, the HMAC-SHA256 signature is computed over the exact bytes sent in
the HTTP request and exposed as `X-Panopta-Signature: sha256=<hex>`. The sender
also includes `X-Panopta-Event`, `X-Panopta-Event-Id`, and
`User-Agent: Panopta-Webhook/1.0`.

Destination failures are isolated: a timeout, DNS failure, non-2xx response, or
malformed URL marks that destination unsuccessful but does not roll back the
incident or block other routes. A route test uses a synthetic
`test-00000000` incident and must never create a real incident.

## Edge cases and acceptance criteria

- No JWT, expired JWT, inactive user, and cross-org JWT are rejected at the
  WebSocket handshake.
- Two browser tabs in one org both receive a committed event; a tab in another
  org does not.
- Redis unavailable during a write leaves the write successful and the browser
  eventually correct through polling.
- A socket that disconnects while broadcasting is pruned without affecting
  other sockets.
- Reconnects do not create duplicate listeners or unbounded timers.
- Webhook signatures verify against the captured raw body; whitespace, key
  ordering, Unicode, and an absent secret remain deterministic.
- Webhook routes reject non-HTTP(S) URLs and invalid minimum severities before
  persistence.
- A webhook timeout/non-2xx response returns a failed delivery result without
  failing the alert task or changing incident status.
- Send-test and delete are idempotent from the user's perspective: test does
  not create an incident, and deleting a route removes it from future dispatch.
- Browser smoke tests confirm the monitor DSL preview, the actionable DSL guide
  anchor, the WebSocket handshake, and empty console/network diagnostics.
