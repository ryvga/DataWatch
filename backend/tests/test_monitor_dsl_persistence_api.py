import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


async def _login(client, slug, email, password):
    response = await client.post(
        "/auth/login",
        json={"org_slug": slug, "email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _create_asset(client, headers):
    source = await client.post(
        "/api/v1/sources",
        headers=headers,
        json={
            "name": "DSL source",
            "type": "duckdb",
            "connection_config": {"path": ":memory:"},
        },
    )
    assert source.status_code == 201, source.text
    with patch(
        "app.routers.tables._verified_schema_snapshot",
        new=AsyncMock(return_value=("CREATE TABLE main.orders (id integer NOT NULL);", {"id"})),
    ), patch("app.scheduler.add_table_job"), patch("app.tasks.profile_table") as profile, patch(
        "app.tasks.bootstrap_table_autopilot"
    ) as autopilot:
        profile.delay = MagicMock()
        autopilot.delay = MagicMock()
        table = await client.post(
            "/api/v1/tables",
            headers=headers,
            json={
                "source_id": source.json()["id"],
                "schema_name": "main",
                "table_name": f"orders_{uuid.uuid4().hex[:8]}",
            },
        )
    assert table.status_code == 201, table.text
    return table.json()["id"]


def _definition(asset_id, *, name="zero-orders", threshold=0):
    return {
        "apiVersion": "datawatch.io/v1alpha1",
        "kind": "Monitor",
        "metadata": {"name": name, "labels": {"team": "data"}},
        "spec": {
            "target": {"assetId": asset_id},
            "measurements": [
                {"id": "rows", "type": "metric", "metric": "row_count"}
            ],
            "breachWhen": {
                "op": "lte",
                "left": {"ref": "rows"},
                "right": {"literal": threshold},
            },
        },
    }


@pytest.mark.asyncio
async def test_dsl_draft_revision_preview_and_tenant_isolation(client, auth_headers, test_org):
    asset_id = await _create_asset(client, auth_headers)
    initial = _definition(asset_id)

    preview = await client.post(
        "/api/v2/monitors/preview", headers=auth_headers, json=initial
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["preview"]["status"] == "compiled_validation_only"
    assert preview.json()["capabilityPlan"]["compilationSupported"] is True
    assert preview.json()["compiledPlan"]["statementMode"] == "preview_only"
    assert preview.json()["compiledPlan"]["driverBindingRequired"] is True

    created = await client.post(
        f"/api/v2/assets/{asset_id}/monitors", headers=auth_headers, json=initial
    )
    assert created.status_code == 201, created.text
    monitor = created.json()
    monitor_id = monitor["id"]
    assert monitor["status"] == "draft"
    assert monitor["currentRevision"] == 1
    assert monitor["activeRevisionId"] is None

    duplicate = await client.post(
        f"/api/v2/assets/{asset_id}/monitors", headers=auth_headers, json=initial
    )
    assert duplicate.status_code == 409

    revised_definition = _definition(asset_id, name="zero-orders-v2", threshold=1)
    revised = await client.put(
        f"/api/v2/monitors/{monitor_id}",
        headers=auth_headers,
        json={"expectedRevision": 1, "definition": revised_definition},
    )
    assert revised.status_code == 200, revised.text
    assert revised.json()["currentRevision"] == 2
    assert revised.json()["definitionHash"] != monitor["definitionHash"]

    revisions = await client.get(
        f"/api/v2/monitors/{monitor_id}/revisions", headers=auth_headers
    )
    assert revisions.status_code == 200
    assert [item["revision"] for item in revisions.json()] == [2, 1]
    assert revisions.json()[1]["definitionHash"] == monitor["definitionHash"]

    runs = await client.get(f"/api/v2/monitors/{monitor_id}/runs", headers=auth_headers)
    assert runs.status_code == 200
    assert runs.json() == []

    stale = await client.put(
        f"/api/v2/monitors/{monitor_id}",
        headers=auth_headers,
        json={"expectedRevision": 1, "definition": initial},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["error"] == "revision_conflict"

    revised_preview = await client.post(
        "/api/v2/monitors/preview", headers=auth_headers, json=revised_definition
    )
    activation = await client.post(
        f"/api/v2/monitors/{monitor_id}/activate",
        headers=auth_headers,
        json={
            "expectedRevision": 2,
            "previewAttestation": revised_preview.json()["preview"]["attestation"],
        },
        )
    assert activation.status_code == 200, activation.text
    assert activation.json()["status"] == "active"
    assert activation.json()["activeRevisionId"]
    assert activation.json()["activation"]["schedule"] == "existing_table_profile_cadence"

    # Editing an active monitor creates a draft head; manual execution remains
    # pinned to the attested active revision until the new revision is activated.
    head_definition = _definition(asset_id, name="zero-orders-v3", threshold=2)
    head = await client.put(
        f"/api/v2/monitors/{monitor_id}",
        headers=auth_headers,
        json={"expectedRevision": 2, "definition": head_definition},
    )
    assert head.status_code == 200, head.text

    with patch("app.tasks.run_dsl_monitor") as run_dsl_monitor:
        run_dsl_monitor.delay = MagicMock(return_value=MagicMock(id="task-1"))
        manual = await client.post(
            f"/api/v2/monitors/{monitor_id}/run",
            headers=auth_headers,
            json={"clientIdempotencyKey": "manual-1"},
        )
    assert manual.status_code == 202, manual.text
    assert manual.json()["run"]["triggerType"] == "manual"
    assert manual.json()["run"]["status"] == "queued"
    assert manual.json()["run"]["revisionId"] == activation.json()["activeRevisionId"]

    listed = await client.get(f"/api/v2/assets/{asset_id}/monitors", headers=auth_headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [monitor_id]

    other_slug = f"other-{uuid.uuid4().hex[:8]}"
    other_email = f"owner@{other_slug}.example.com"
    password = "testpassword123"
    registered = await client.post(
        "/auth/register",
        json={
            "org_name": "Other Org",
            "org_slug": other_slug,
            "email": other_email,
            "password": password,
        },
    )
    assert registered.status_code == 201
    other_headers = await _login(client, other_slug, other_email, password)
    hidden = await client.get(f"/api/v2/monitors/{monitor_id}", headers=other_headers)
    assert hidden.status_code == 404
