# Panopta — PFE Recording Runbook

## Prepare the recording

```bash
docker compose up -d --wait
docker compose --profile seed run --rm --entrypoint python seed /scripts/quickstart.py --reset
curl -fsS http://localhost:8000/ready
```

The seed waits for the Acme `orders` AI narration and configures a local P1/P2 email route to MailHog. Do not start recording until it prints `Acme orders narration is ready for recording`.

| Workspace | URL | Login |
| --- | --- | --- |
| Primary demo | http://acme-corp.localhost:5173 | `mounir@acme.io` / `demo1234` |
| Secondary workspace | http://startup-io.localhost:5173 | `dev@startup.io` / `demo1234` |
| Staff portal | http://admin.localhost:5173 | `admin@datawatch.io` / `admin1234` |
| Email preview | http://localhost:8025 | MailHog |

## Seven-minute recording flow

1. Sign in to the Acme workspace. Pause on **Operations**: the incident queue, four monitored tables, connected source count, and health score explain the current operating state immediately.
2. Open the critical `orders` incident from the red review strip. Explain that the title identifies the actionable signal: a `payment_status` null-rate spike, with freshness also breached.
3. In **Incident detail**, show the timeline, AI analysis, likely causes, recommended actions, and copied debug query. Emphasize that the explanation assists investigation; it does not make the decision for the operator.
4. Open **View table detail**. Show the latest profile history and the `payment_status` metric change. Explain that profiling uses aggregate queries, then evaluates rule-based, statistical, and ML signals over profile history.
5. Return to **Incidents** and acknowledge the issue. Show ownership in **Teams → Data Engineering** and the on-call context. Do not resolve the incident during the recording.
6. Open **Settings → Alerts** and show the configured email route. Open MailHog in a second tab to show the delivered P1/P2 incident email.
7. Open **AI Governance**. Show the system inventory, declared data-use map, evidence provenance, control reasons, and the explicit observe-only boundary. State that it records evidence and flags gaps; it is not legal certification or runtime blocking.

## Recording rules

- Use Acme only for the core story. Startup.io is secondary evidence of tenant isolation.
- Do not open Billing, Reports, or the empty Monitors index during the main recording.
- Do not promise universal connector support: PostgreSQL is stable; DuckDB/SQLite are beta; other connectors remain experimental or credential-gated.
- Do not call governance controls compliant, certified, or runtime-blocking.
- If the narration does not load, stop and re-run the seed command; do not record the loading state.

## Fast recovery

```bash
docker compose --profile seed run --rm --entrypoint python seed /scripts/quickstart.py --reset
docker compose logs --tail=100 worker
```

Use `docker compose --profile seed run --rm --entrypoint python seed /scripts/quickstart.py --reset` immediately before each recording take. It resets the intended incident, alert route, AI-governance fixtures, and presentation state.
