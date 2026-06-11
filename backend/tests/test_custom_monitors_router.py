import uuid
from unittest.mock import MagicMock, patch

import pytest


async def _auth_headers(client, slug: str, email: str, password: str) -> dict[str, str]:
    resp = await client.post(
        "/auth/login",
        json={"email": email, "password": password, "org_slug": slug},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _register_table(client, headers):
    source = await client.post(
        "/api/v1/sources",
        headers=headers,
        json={
            "name": "Monitor source",
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
                "table_name": f"events_{uuid.uuid4().hex[:8]}",
                "check_interval_minutes": 60,
                "sensitivity": 3.0,
                "dbt_model_yaml": "CREATE TABLE main.events (event_name varchar NULL);",
            },
        )
    assert table.status_code == 201, table.text
    return table.json()


@pytest.mark.asyncio
async def test_duplicate_custom_monitor_sql_is_rejected(client, db_session):
    slug = f"monitors-{uuid.uuid4().hex[:8]}"
    email = f"owner@{slug}.example.com"
    password = "testpassword123"
    register = await client.post(
        "/auth/register",
        json={
            "org_name": "Monitor Test Org",
            "org_slug": slug,
            "email": email,
            "password": password,
        },
    )
    assert register.status_code == 201, register.text
    headers = await _auth_headers(client, slug, email, password)
    table = await _register_table(client, headers)

    first = await client.post(
        f"/api/v1/tables/{table['id']}/custom-monitors",
        headers=headers,
        json={
            "name": "Event name required",
            "sql_query": "SELECT COUNT(*) FROM main.events WHERE event_name IS NULL",
            "severity": "P2",
        },
    )
    assert first.status_code == 201, first.text

    duplicate = await client.post(
        f"/api/v1/tables/{table['id']}/custom-monitors",
        headers=headers,
        json={
            "name": "AI duplicate event name required",
            "sql_query": " select   count(*)   from main.events where event_name is null ",
            "severity": "P2",
        },
    )
    assert duplicate.status_code == 409
    assert "already exists" in duplicate.json()["detail"]

    listed = await client.get(f"/api/v1/tables/{table['id']}/custom-monitors", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1
