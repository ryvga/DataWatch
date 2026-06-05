from datetime import UTC, datetime
from types import SimpleNamespace

from app.services import alert


class _Response:
    def raise_for_status(self):
        return None


class _Client:
    def __init__(self, calls, timeout):
        self.calls = calls
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, **kwargs):
        self.calls.append({"url": url, "timeout": self.timeout, **kwargs})
        return _Response()


def _patch_client(monkeypatch):
    calls = []

    def client_factory(*, timeout):
        return _Client(calls, timeout)

    monkeypatch.setattr(alert.httpx, "Client", client_factory)
    return calls


def _incident(severity="P2"):
    return SimpleNamespace(
        id="inc-123",
        title="Orders freshness breach",
        severity=severity,
        status="open",
        fired_checks=["freshness"],
        table_id="table-123",
        created_at=datetime(2026, 6, 5, 12, 30, tzinfo=UTC),
    )


def test_send_discord_alert_posts_embed_payload(monkeypatch):
    calls = _patch_client(monkeypatch)
    narration = {"summary": "Orders have not refreshed for two hours."}

    assert hasattr(alert, "send_discord_alert"), "send_discord_alert is missing"
    ok = alert.send_discord_alert("https://discord.test/webhook", _incident("P2"), narration)

    assert ok is True
    assert calls[0]["url"] == "https://discord.test/webhook"
    assert calls[0]["timeout"] == 10
    embed = calls[0]["json"]["embeds"][0]
    assert embed["color"] == 15105570
    assert embed["title"] == "Orders freshness breach"
    assert embed["description"] == "Orders have not refreshed for two hours."
    assert embed["fields"] == [
        {"name": "Severity", "value": "P2", "inline": True},
        {"name": "Status", "value": "open", "inline": True},
        {"name": "Detected", "value": "2026-06-05 12:30 UTC", "inline": True},
    ]


def test_send_opsgenie_alert_posts_create_alert_payload(monkeypatch):
    calls = _patch_client(monkeypatch)
    narration = {"summary": "Orders have not refreshed for two hours."}

    assert hasattr(alert, "send_opsgenie_alert"), "send_opsgenie_alert is missing"
    ok = alert.send_opsgenie_alert("api-key", _incident("P1"), narration)

    assert ok is True
    assert calls[0]["url"] == "https://api.opsgenie.com/v2/alerts"
    assert calls[0]["timeout"] == 10
    assert calls[0]["headers"] == {"Authorization": "GenieKey api-key"}
    assert calls[0]["json"] == {
        "message": "Orders freshness breach",
        "description": "Orders have not refreshed for two hours.",
        "priority": "P1",
        "tags": ["datawatch"],
        "source": "DataWatch",
    }


def test_dispatch_alert_routes_discord_and_opsgenie(monkeypatch):
    dispatched = []

    monkeypatch.setattr(
        alert,
        "send_discord_alert",
        lambda webhook_url, incident, narration: dispatched.append(("discord", webhook_url)) or True,
        raising=False,
    )
    monkeypatch.setattr(
        alert,
        "send_opsgenie_alert",
        lambda api_key, incident, narration: dispatched.append(("opsgenie", api_key)) or True,
        raising=False,
    )

    assert alert.dispatch_alert(
        SimpleNamespace(channel="discord", config={"webhook_url": "discord-url"}),
        _incident(),
        {"summary": "summary"},
    )
    assert alert.dispatch_alert(
        SimpleNamespace(channel="opsgenie", config={"api_key": "opsgenie-key"}),
        _incident(),
        {"summary": "summary"},
    )

    assert dispatched == [("discord", "discord-url"), ("opsgenie", "opsgenie-key")]
