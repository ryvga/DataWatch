"""
AlertService — Slack, Email (SendGrid), PagerDuty.

Routing: query alert_configs for org + table_id (and org-wide configs),
filter by min_severity, enqueue send_alert task per matching config.
"""
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

SEVERITY_ORDER = {"P1": 1, "P2": 2, "P3": 3}


def severity_meets_threshold(incident_severity: str, min_severity: str) -> bool:
    """P1 meets threshold P2 (P1 ≤ P2), P3 does NOT meet threshold P2."""
    return SEVERITY_ORDER.get(incident_severity, 99) <= SEVERITY_ORDER.get(min_severity.upper(), 99)


# ── Slack ─────────────────────────────────────────────────────────────────────

SEVERITY_COLORS = {"P1": "#dc2626", "P2": "#f97316", "P3": "#eab308"}


def send_slack_alert(webhook_url: str, incident, narration: dict | None) -> bool:
    severity = incident.severity.upper()
    color = SEVERITY_COLORS.get(severity, "#6b7280")
    summary = narration.get("summary", "No summary available.") if narration and "error" not in narration else "Narration pending."
    top_cause = ""
    if narration and "likely_causes" in narration and narration["likely_causes"]:
        top_cause = narration["likely_causes"][0].get("hypothesis", "")

    payload = {
        "text": f"🚨 [{severity}] {incident.title}",
        "attachments": [
            {
                "color": color,
                "blocks": [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*{incident.title}*"},
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*Severity:*\n{severity}"},
                            {"type": "mrkdwn", "text": f"*Detected:*\n{incident.created_at.strftime('%Y-%m-%d %H:%M UTC')}"},
                        ],
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*Summary:* {summary}"},
                    },
                ],
            }
        ],
    }

    if top_cause:
        payload["attachments"][0]["blocks"].append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Top cause:* {top_cause}"},
        })

    try:
        resp = httpx.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info("Slack alert sent for incident %s", incident.id)
        return True
    except Exception as e:
        logger.error("Slack alert failed for incident %s: %s", incident.id, e)
        return False


# ── Email (SendGrid) ──────────────────────────────────────────────────────────

def send_email_alert(to_addresses: list[str], incident, narration: dict | None) -> bool:
    severity = incident.severity.upper()
    summary = narration.get("summary", "Anomaly detected.") if narration and "error" not in narration else "Anomaly detected."

    if not to_addresses:
        logger.warning("Email alert skipped for incident %s: no recipients", incident.id)
        return False

    if not settings.SENDGRID_API_KEY:
        from app.services.email import _layout, _send_email

        body = f"""
            <p><strong>{incident.title}</strong></p>
            <p><strong>Severity:</strong> {severity}</p>
            <p><strong>Summary:</strong> {summary}</p>
            <p><strong>Detected at:</strong> {incident.created_at.strftime('%Y-%m-%d %H:%M UTC')}</p>
        """
        return all(
            _send_email(addr, f"[DataWatch] {severity} incident - {incident.title[:80]}", _layout("DataWatch incident alert", body))
            for addr in to_addresses
        )

    actions_html = ""
    if narration and "recommended_actions" in narration:
        items = "".join(f"<li>{a}</li>" for a in narration["recommended_actions"])
        actions_html = f"<h3>Recommended Actions</h3><ul>{items}</ul>"

    html_content = f"""
    <html><body style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
      <div style="background: {'#dc2626' if severity == 'P1' else '#f97316' if severity == 'P2' else '#eab308'};
                  color: white; padding: 16px; border-radius: 8px 8px 0 0;">
        <h2 style="margin:0">🚨 [{severity}] DataWatch Incident</h2>
      </div>
      <div style="padding: 24px; border: 1px solid #e5e7eb; border-radius: 0 0 8px 8px;">
        <h3 style="margin-top:0">{incident.title}</h3>
        <p><strong>Summary:</strong> {summary}</p>
        <p><strong>Detected at:</strong> {incident.created_at.strftime('%Y-%m-%d %H:%M UTC')}</p>
        {actions_html}
      </div>
    </body></html>
    """

    payload = {
        "personalizations": [{"to": [{"email": addr} for addr in to_addresses]}],
        "from": {"email": settings.FROM_EMAIL, "name": "DataWatch"},
        "subject": f"[DataWatch] {severity} incident — {incident.title[:80]}",
        "content": [{"type": "text/html", "value": html_content}],
    }

    try:
        resp = httpx.post(
            "https://api.sendgrid.com/v3/mail/send",
            json=payload,
            headers={"Authorization": f"Bearer {settings.SENDGRID_API_KEY}"},
            timeout=15,
        )
        resp.raise_for_status()
        logger.info("Email alert sent for incident %s to %s", incident.id, to_addresses)
        return True
    except Exception as e:
        logger.error("Email alert failed for incident %s: %s", incident.id, e)
        return False


# ── PagerDuty ─────────────────────────────────────────────────────────────────

def send_pagerduty_alert(routing_key: str, incident, event_action: str = "trigger") -> bool:
    payload = {
        "routing_key": routing_key,
        "event_action": event_action,
        "dedup_key": f"datawatch-{incident.id}",
        "payload": {
            "summary": incident.title,
            "severity": "critical" if incident.severity == "P1" else "warning",
            "source": "DataWatch",
            "custom_details": {
                "severity": incident.severity,
                "fired_checks": incident.fired_checks,
                "detected_at": incident.created_at.isoformat(),
            },
        },
    }

    try:
        resp = httpx.post(
            "https://events.pagerduty.com/v2/enqueue",
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        logger.info("PagerDuty alert sent (%s) for incident %s", event_action, incident.id)
        return True
    except Exception as e:
        logger.error("PagerDuty alert failed for incident %s: %s", incident.id, e)
        return False


# ── Webhook ───────────────────────────────────────────────────────────────────

def send_webhook_alert(url: str, incident, narration: dict | None, secret: str | None = None) -> bool:
    """Generic JSON webhook — sends full incident payload with optional HMAC signature."""
    import hashlib, hmac, time
    payload = {
        "event": "incident.created",
        "timestamp": int(time.time()),
        "incident": {
            "id": str(incident.id),
            "title": incident.title,
            "severity": incident.severity,
            "status": incident.status,
            "detected_at": incident.created_at.isoformat(),
            "table_id": str(incident.table_id),
        },
        "ai_summary": narration.get("summary") if narration else None,
    }
    headers = {"Content-Type": "application/json"}
    if secret:
        body = __import__("json").dumps(payload).encode()
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        headers["X-DataWatch-Signature"] = f"sha256={sig}"
    try:
        with httpx.Client(timeout=10) as client:
            r = client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            return True
    except Exception as e:
        logger.error("Webhook alert failed: %s", e)
        return False


# ── Microsoft Teams ───────────────────────────────────────────────────────────

TEAMS_COLORS = {"P1": "FF0000", "P2": "FFA500", "P3": "FFFF00"}

def send_teams_alert(webhook_url: str, incident, narration: dict | None) -> bool:
    """Microsoft Teams Incoming Webhook (Adaptive Card format)."""
    severity = incident.severity.upper()
    summary = narration.get("summary", "See incident for details.") if narration else "See incident for details."
    color = TEAMS_COLORS.get(severity, "6b7280")
    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": color,
        "summary": f"[{severity}] {incident.title}",
        "sections": [{
            "activityTitle": f"🚨 [{severity}] DataWatch Incident",
            "activitySubtitle": incident.title,
            "facts": [
                {"name": "Severity", "value": severity},
                {"name": "Status", "value": incident.status.title()},
                {"name": "Detected", "value": incident.created_at.strftime("%Y-%m-%d %H:%M UTC")},
            ],
            "text": summary,
        }],
    }
    try:
        with httpx.Client(timeout=10) as client:
            r = client.post(webhook_url, json=payload)
            r.raise_for_status()
            return True
    except Exception as e:
        logger.error("Teams alert failed: %s", e)
        return False


# ── Discord ───────────────────────────────────────────────────────────────────

DISCORD_COLORS = {"P1": 15548997, "P2": 15105570, "P3": 16776960}

def send_discord_alert(webhook_url: str, incident, narration: dict | None) -> bool:
    """Discord webhook alert with an embed payload."""
    severity = incident.severity.upper()
    summary = narration.get("summary", "Narration pending.") if narration and "error" not in narration else "Narration pending."
    color = DISCORD_COLORS.get(severity, 8421504)
    payload = {
        "embeds": [
            {
                "color": color,
                "title": incident.title,
                "description": summary,
                "fields": [
                    {"name": "Severity", "value": severity, "inline": True},
                    {"name": "Status", "value": str(incident.status), "inline": True},
                    {
                        "name": "Detected",
                        "value": incident.created_at.strftime("%Y-%m-%d %H:%M UTC"),
                        "inline": True,
                    },
                ],
            }
        ]
    }

    try:
        with httpx.Client(timeout=10) as client:
            r = client.post(webhook_url, json=payload)
            r.raise_for_status()
            return True
    except Exception as e:
        logger.error("Discord alert failed for incident %s: %s", incident.id, e)
        return False


# ── OpsGenie ──────────────────────────────────────────────────────────────────

OPSGENIE_PRIORITIES = {"P1": "P1", "P2": "P2", "P3": "P3"}

def send_opsgenie_alert(
    api_key: str,
    incident,
    narration: dict | None,
    base_url: str = "https://api.opsgenie.com/v2/alerts",
) -> bool:
    """OpsGenie create alert API."""
    severity = incident.severity.upper()
    summary = narration.get("summary", "Narration pending.") if narration and "error" not in narration else "Narration pending."
    payload = {
        "message": incident.title,
        "description": summary,
        "priority": OPSGENIE_PRIORITIES.get(severity, "P3"),
        "tags": ["datawatch"],
        "source": "DataWatch",
    }
    headers = {"Authorization": f"GenieKey {api_key}"}

    try:
        with httpx.Client(timeout=10) as client:
            r = client.post(base_url, json=payload, headers=headers)
            r.raise_for_status()
            return True
    except Exception as e:
        logger.error("OpsGenie alert failed for incident %s: %s", incident.id, e)
        return False


# ── Dispatcher ────────────────────────────────────────────────────────────────

def dispatch_alert(alert_config, incident, narration: dict | None) -> bool:
    channel = alert_config.channel
    cfg = alert_config.config or {}

    min_severity = cfg.get("min_severity", "P3")
    if not severity_meets_threshold(incident.severity, min_severity):
        logger.info(
            "Skipping %s alert — incident %s (%s) below threshold %s",
            channel, incident.id, incident.severity, min_severity,
        )
        return False

    if channel == "slack":
        return send_slack_alert(cfg["webhook_url"], incident, narration)
    elif channel == "email":
        return send_email_alert(cfg.get("to", []), incident, narration)
    elif channel == "pagerduty":
        return send_pagerduty_alert(cfg["routing_key"], incident)
    elif channel == "webhook":
        return send_webhook_alert(cfg["url"], incident, narration, cfg.get("secret"))
    elif channel == "teams":
        return send_teams_alert(cfg["webhook_url"], incident, narration)
    elif channel == "discord":
        return send_discord_alert(cfg["webhook_url"], incident, narration)
    elif channel == "opsgenie":
        return send_opsgenie_alert(cfg["api_key"], incident, narration)
    else:
        logger.warning("Unknown alert channel: %s", channel)
        return False
