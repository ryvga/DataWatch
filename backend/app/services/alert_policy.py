from __future__ import annotations

import re
from copy import deepcopy
from urllib.parse import urlparse

from app.services.plans import UPGRADE_URL


PLAN_ORDER = {"free": 0, "starter": 1, "growth": 2, "agency": 3, "enterprise": 4}
ACTIVE_STATUSES = {"active", "trialing", "approval_pending", "ACTIVE", "TRIALING", "APPROVAL_PENDING"}
SEVERITIES = {"P1", "P2", "P3"}

CHANNELS = {
    "email": {
        "label": "Email",
        "required_plan": "free",
        "description": "Send incidents to one or more email recipients.",
        "scope": "Org-wide or table-specific",
        "fields": [
            {"name": "to", "label": "Recipients", "type": "email_list", "required": True, "secret": False},
            {"name": "min_severity", "label": "Minimum severity", "type": "severity", "required": False, "secret": False},
        ],
    },
    "slack": {
        "label": "Slack",
        "required_plan": "starter",
        "description": "Post incident cards into a Slack channel using an incoming webhook.",
        "scope": "Org-wide or table-specific",
        "fields": [
            {"name": "webhook_url", "label": "Webhook URL", "type": "url", "required": True, "secret": True},
            {"name": "min_severity", "label": "Minimum severity", "type": "severity", "required": False, "secret": False},
        ],
    },
    "webhook": {
        "label": "Generic webhook",
        "required_plan": "starter",
        "description": "POST a signed JSON payload to your incident automation endpoint.",
        "scope": "Org-wide or table-specific",
        "fields": [
            {"name": "url", "label": "Endpoint URL", "type": "url", "required": True, "secret": False},
            {"name": "secret", "label": "Signing secret", "type": "text", "required": False, "secret": True},
            {"name": "min_severity", "label": "Minimum severity", "type": "severity", "required": False, "secret": False},
        ],
    },
    "pagerduty": {
        "label": "PagerDuty",
        "required_plan": "growth",
        "description": "Trigger PagerDuty Events API incidents for urgent Panopta incidents.",
        "scope": "Best for P1/P2 table-specific routes",
        "fields": [
            {"name": "routing_key", "label": "Routing key", "type": "password", "required": True, "secret": True},
            {"name": "min_severity", "label": "Minimum severity", "type": "severity", "required": False, "secret": False},
        ],
    },
    "teams": {
        "label": "Microsoft Teams",
        "required_plan": "growth",
        "description": "Post incident cards to a Teams incoming webhook.",
        "scope": "Org-wide or table-specific",
        "fields": [
            {"name": "webhook_url", "label": "Webhook URL", "type": "url", "required": True, "secret": True},
            {"name": "min_severity", "label": "Minimum severity", "type": "severity", "required": False, "secret": False},
        ],
    },
    "discord": {
        "label": "Discord",
        "required_plan": "growth",
        "description": "Post incident embeds to a Discord webhook.",
        "scope": "Org-wide or table-specific",
        "fields": [
            {"name": "webhook_url", "label": "Webhook URL", "type": "url", "required": True, "secret": True},
            {"name": "min_severity", "label": "Minimum severity", "type": "severity", "required": False, "secret": False},
        ],
    },
    "opsgenie": {
        "label": "OpsGenie",
        "required_plan": "growth",
        "description": "Create OpsGenie alerts for incident response teams.",
        "scope": "Best for P1/P2 table-specific routes",
        "fields": [
            {"name": "api_key", "label": "API key", "type": "password", "required": True, "secret": True},
            {"name": "min_severity", "label": "Minimum severity", "type": "severity", "required": False, "secret": False},
        ],
    },
}


def effective_alert_plan(plan: str, subscription_status: str) -> str:
    normalized_plan = (plan or "free").lower()
    normalized_status = (subscription_status or "").lower()
    if normalized_plan == "free":
        return "free"
    if normalized_status in ACTIVE_STATUSES:
        return normalized_plan
    return "free"


def channel_available(plan: str, subscription_status: str, channel: str) -> bool:
    meta = CHANNELS[channel]
    effective = effective_alert_plan(plan, subscription_status)
    return PLAN_ORDER.get(effective, 0) >= PLAN_ORDER[meta["required_plan"]]


def channel_upgrade_detail(plan: str, subscription_status: str, channel: str) -> dict:
    meta = CHANNELS[channel]
    effective = effective_alert_plan(plan, subscription_status)
    return {
        "error": "feature_not_in_plan",
        "feature": channel,
        "feature_label": meta["label"],
        "current_plan": effective,
        "configured_plan": (plan or "free").lower(),
        "subscription_status": subscription_status or "unknown",
        "required_plan": meta["required_plan"],
        "upgrade_url": UPGRADE_URL,
        "message": f"{meta['label']} requires {meta['required_plan'].title()} or higher. Your current alert entitlement is {effective.title()}.",
    }


def channels_for_org(plan: str, subscription_status: str) -> list[dict]:
    return [
        {
            "id": channel,
            **deepcopy(meta),
            "available": channel_available(plan, subscription_status, channel),
            "locked_reason": None
            if channel_available(plan, subscription_status, channel)
            else channel_upgrade_detail(plan, subscription_status, channel)["message"],
        }
        for channel, meta in CHANNELS.items()
    ]


def mask_alert_config(channel: str, config: dict | None) -> dict:
    cfg = dict(config or {})
    meta = CHANNELS.get(channel)
    if not meta:
        return cfg
    secret_fields = {field["name"] for field in meta["fields"] if field.get("secret")}
    for field in secret_fields:
        if cfg.get(field):
            cfg[field] = "********"
    return cfg


def validate_alert_config(channel: str, config: dict | None) -> dict:
    if channel not in CHANNELS:
        valid = ", ".join(CHANNELS)
        raise ValueError(f"Unknown alert channel '{channel}'. Choose one of: {valid}.")
    cfg = dict(config or {})
    min_severity = str(cfg.get("min_severity", "P3")).upper()
    if min_severity not in SEVERITIES:
        raise ValueError("Minimum severity must be P1, P2, or P3.")
    cfg["min_severity"] = min_severity

    if channel == "email":
        recipients = cfg.get("to")
        if isinstance(recipients, str):
            recipients = [item.strip() for item in recipients.split(",") if item.strip()]
        if not isinstance(recipients, list) or not recipients:
            raise ValueError("Email alerts need at least one recipient in config.to.")
        invalid = [item for item in recipients if not isinstance(item, str) or not _looks_like_email(item)]
        if invalid:
            raise ValueError(f"Email recipients must be valid addresses: {', '.join(map(str, invalid))}.")
        cfg["to"] = recipients
    elif channel in {"slack", "teams", "discord"}:
        _require_url(cfg, "webhook_url", CHANNELS[channel]["label"])
    elif channel == "webhook":
        _require_url(cfg, "url", "Generic webhook")
    elif channel == "pagerduty":
        _require_non_empty(cfg, "routing_key", "PagerDuty routing key")
    elif channel == "opsgenie":
        _require_non_empty(cfg, "api_key", "OpsGenie API key")

    return cfg


def _require_non_empty(config: dict, key: str, label: str) -> None:
    if not str(config.get(key) or "").strip():
        raise ValueError(f"{label} is required.")


def _require_url(config: dict, key: str, label: str) -> None:
    value = str(config.get(key) or "").strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{label} needs a valid http or https URL in config.{key}.")


def _looks_like_email(value: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value))
