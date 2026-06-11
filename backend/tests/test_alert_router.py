import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from app.models.organization import Organization
from app.services.alert_policy import channels_for_org, validate_alert_config


async def _auth_headers(client, slug: str, email: str, password: str) -> dict[str, str]:
    resp = await client.post(
        "/auth/login",
        json={"email": email, "password": password, "org_slug": slug},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _create_source_and_table(client, headers):
    source = await client.post(
        "/api/v1/sources",
        headers=headers,
        json={
            "name": "Alert route source",
            "type": "duckdb",
            "connection_config": {"path": ":memory:"},
        },
    )
    assert source.status_code == 201, source.text

    with patch("app.scheduler.add_table_job"), \
         patch("app.tasks.profile_table") as profile_task, \
         patch("app.tasks.bootstrap_table_autopilot") as autopilot_task:
        profile_task.delay = MagicMock()
        autopilot_task.delay = MagicMock()
        table = await client.post(
            "/api/v1/tables",
            headers=headers,
            json={
                "source_id": source.json()["id"],
                "schema_name": "main",
                "table_name": f"orders_{uuid.uuid4().hex[:8]}",
                "check_interval_minutes": 60,
                "sensitivity": 3.0,
                "dbt_model_yaml": "CREATE TABLE main.orders (id integer NOT NULL);",
            },
        )
    assert table.status_code == 201, table.text
    return source.json(), table.json()


@pytest.mark.asyncio
async def test_create_alert_commits_and_lists_immediately(client, db_session):
    slug = f"alerts-{uuid.uuid4().hex[:8]}"
    email = f"owner@{slug}.example.com"
    password = "testpassword123"
    register = await client.post(
        "/auth/register",
        json={
            "org_name": "Alert Test Org",
            "org_slug": slug,
            "email": email,
            "password": password,
        },
    )
    assert register.status_code == 201, register.text
    headers = await _auth_headers(client, slug, email, password)

    created = await client.post(
        "/api/v1/alerts",
        headers=headers,
        json={
            "channel": "email",
            "config": {"to": ["ops@example.com"], "min_severity": "P2"},
        },
    )
    assert created.status_code == 201, created.text

    listed = await client.get("/api/v1/alerts", headers=headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [created.json()["id"]]

    deleted = await client.delete(f"/api/v1/alerts/{created.json()['id']}", headers=headers)
    assert deleted.status_code == 204
    listed_after_delete = await client.get("/api/v1/alerts", headers=headers)
    assert listed_after_delete.status_code == 200
    assert listed_after_delete.json() == []


@pytest.mark.asyncio
async def test_create_table_scoped_alert_updates_autopilot_without_false_failure(client, db_session):
    slug = f"alerts-{uuid.uuid4().hex[:8]}"
    email = f"owner@{slug}.example.com"
    password = "testpassword123"
    register = await client.post(
        "/auth/register",
        json={
            "org_name": "Alert Table Org",
            "org_slug": slug,
            "email": email,
            "password": password,
        },
    )
    assert register.status_code == 201, register.text
    headers = await _auth_headers(client, slug, email, password)
    _, table = await _create_source_and_table(client, headers)
    assert table["autopilot"]["steps"]["alerts"]["status"] == "pending"

    created = await client.post(
        "/api/v1/alerts",
        headers=headers,
        json={
            "table_id": table["id"],
            "channel": "email",
            "config": {"to": ["table-ops@example.com"], "min_severity": "P2"},
        },
    )
    assert created.status_code == 201, created.text

    refreshed_table = await client.get(f"/api/v1/tables/{table['id']}", headers=headers)
    assert refreshed_table.status_code == 200
    assert refreshed_table.json()["autopilot"]["steps"]["alerts"]["status"] == "complete"


@pytest.mark.asyncio
async def test_locked_alert_channel_returns_upgrade_context(client, db_session):
    slug = f"alerts-{uuid.uuid4().hex[:8]}"
    email = f"owner@{slug}.example.com"
    password = "testpassword123"
    register = await client.post(
        "/auth/register",
        json={
            "org_name": "Alert Free Org",
            "org_slug": slug,
            "email": email,
            "password": password,
        },
    )
    assert register.status_code == 201, register.text
    headers = await _auth_headers(client, slug, email, password)

    blocked = await client.post(
        "/api/v1/alerts",
        headers=headers,
        json={
            "channel": "pagerduty",
            "config": {"routing_key": "pd-key", "min_severity": "P1"},
        },
    )
    assert blocked.status_code == 402
    detail = blocked.json()["detail"]
    assert detail["error"] == "feature_not_in_plan"
    assert detail["feature"] == "pagerduty"
    assert detail["required_plan"] == "growth"
    assert detail["current_plan"] == "free"
    assert "PagerDuty requires Growth" in detail["message"]


@pytest.mark.asyncio
async def test_starter_allows_webhook_but_locks_pagerduty(client, db_session):
    slug = f"alerts-{uuid.uuid4().hex[:8]}"
    email = f"owner@{slug}.example.com"
    password = "testpassword123"
    register = await client.post(
        "/auth/register",
        json={
            "org_name": "Alert Starter Org",
            "org_slug": slug,
            "email": email,
            "password": password,
        },
    )
    assert register.status_code == 201, register.text
    org = await db_session.scalar(select(Organization).where(Organization.slug == slug))
    org.plan = "starter"
    org.subscription_status = "active"
    await db_session.flush()
    headers = await _auth_headers(client, slug, email, password)

    webhook = await client.post(
        "/api/v1/alerts",
        headers=headers,
        json={
            "channel": "webhook",
            "config": {"url": "https://example.com/datawatch", "min_severity": "P3"},
        },
    )
    assert webhook.status_code == 201, webhook.text

    pagerduty = await client.post(
        "/api/v1/alerts",
        headers=headers,
        json={
            "channel": "pagerduty",
            "config": {"routing_key": "pd-key", "min_severity": "P1"},
        },
    )
    assert pagerduty.status_code == 402
    assert pagerduty.json()["detail"]["required_plan"] == "growth"


def test_alert_policy_validates_channel_specific_config():
    assert [channel["id"] for channel in channels_for_org("free", "trialing") if channel["available"]] == ["email"]
    assert validate_alert_config("email", {"to": ["ops@example.com"], "min_severity": "P1"}) == {
        "to": ["ops@example.com"],
        "min_severity": "P1",
    }

    with pytest.raises(ValueError, match="Email alerts need at least one recipient"):
        validate_alert_config("email", {"to": []})

    with pytest.raises(ValueError, match="Minimum severity must be P1, P2, or P3"):
        validate_alert_config("slack", {"webhook_url": "https://hooks.slack.com/test", "min_severity": "P4"})
