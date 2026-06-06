import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


async def _register_source(client, auth_headers):
    resp = await client.post(
        "/api/v1/sources",
        json={
            "name": "Autopilot DuckDB",
            "type": "duckdb",
            "connection_config": {"path": ":memory:"},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_create_table_initializes_autopilot_and_queues_bootstrap(client, auth_headers):
    source = await _register_source(client, auth_headers)

    with patch("app.scheduler.add_table_job"), \
         patch("app.tasks.profile_table") as profile_task, \
         patch("app.tasks.bootstrap_table_autopilot") as autopilot_task:
        profile_task.delay = MagicMock()
        autopilot_task.delay = MagicMock()

        resp = await client.post(
            "/api/v1/tables",
            json={
                "source_id": source["id"],
                "schema_name": "main",
                "table_name": "orders",
                "check_interval_minutes": 60,
                "sensitivity": 3.0,
                "dbt_model_yaml": (
                    "CREATE TABLE main.orders (\n"
                    "  id integer NOT NULL,\n"
                    "  created_at timestamp NULL,\n"
                    "  status varchar NULL\n"
                    ");"
                ),
            },
            headers=auth_headers,
        )

    assert resp.status_code == 201, resp.text
    payload = resp.json()
    assert payload["autopilot"]["status"] == "queued"
    assert payload["autopilot"]["steps"]["profile"]["status"] == "queued"
    assert payload["autopilot"]["steps"]["recommendations"]["status"] == "queued"
    assert payload["autopilot"]["recommended_next_action"] == "Profiling and AI monitor recommendations are queued."
    profile_task.delay.assert_called_once_with(payload["id"])
    autopilot_task.delay.assert_called_once_with(payload["id"])


@pytest.mark.asyncio
async def test_bootstrap_autopilot_infers_freshness_and_stages_risky_monitors(
    client,
    auth_headers,
    db_session,
):
    from app.models.custom_monitor import CustomMonitor
    from app.models.monitored_table import MonitoredTable
    from app.tasks import _bootstrap_table_autopilot_async

    source = await _register_source(client, auth_headers)
    with patch("app.scheduler.add_table_job"), \
         patch("app.tasks.profile_table") as profile_task, \
         patch("app.tasks.bootstrap_table_autopilot") as autopilot_task:
        profile_task.delay = MagicMock()
        autopilot_task.delay = MagicMock()
        resp = await client.post(
            "/api/v1/tables",
            json={
                "source_id": source["id"],
                "schema_name": "main",
                "table_name": "orders",
                "check_interval_minutes": 60,
                "sensitivity": 3.0,
                "dbt_model_yaml": (
                    "CREATE TABLE main.orders (\n"
                    "  order_id integer NOT NULL,\n"
                    "  created_at timestamp NULL,\n"
                    "  email varchar NULL\n"
                    ");"
                ),
            },
            headers=auth_headers,
        )
    assert resp.status_code == 201, resp.text
    table_id = resp.json()["id"]

    recommendations = [
        {
            "monitor_type": "freshness",
            "column_name": "created_at",
            "name": "orders freshness",
            "rationale": "Detect delayed loads.",
            "severity": "P1",
            "config": {"max_age_hours": 24},
        },
        {
            "monitor_type": "custom_sql",
            "column_name": None,
            "name": "paid orders have email",
            "rationale": "Business-critical communication path.",
            "severity": "P2",
            "config": {"sql": "SELECT COUNT(*) FROM main.orders WHERE status = 'paid' AND email IS NULL"},
        },
    ]

    with patch("app.services.table_autopilot.recommend_monitors", return_value=recommendations):
        result = await _bootstrap_table_autopilot_async(table_id)

    assert result["status"] == "ok"
    table = await db_session.get(MonitoredTable, uuid.UUID(table_id))
    assert table.freshness_column == "created_at"
    assert table.autopilot["status"] == "ready"
    assert table.autopilot["steps"]["safe_baseline"]["status"] == "enabled"
    assert table.autopilot["steps"]["recommendations"]["staged_count"] == 1
    assert table.autopilot["recommendations"][0]["status"] == "staged"
    assert table.autopilot["recommendations"][0]["requires_review"] is True

    monitors = (await db_session.execute(
        CustomMonitor.__table__.select().where(CustomMonitor.table_id == uuid.UUID(table_id))
    )).all()
    assert monitors == []


@pytest.mark.asyncio
async def test_muted_incident_suppresses_identical_future_incidents(db_session, test_org):
    from app.models.data_source import DataSource
    from app.models.incident import Incident
    from app.models.monitored_table import MonitoredTable
    from app.services.anomaly import AnomalyResult
    from app.services.incident import IncidentService

    source = DataSource(
        id=uuid.uuid4(),
        org_id=uuid.UUID(test_org["org_id"]),
        name="Source",
        type="duckdb",
        connection_config={"encrypted": "x"},
        status="connected",
    )
    table = MonitoredTable(id=uuid.uuid4(), source_id=source.id, schema_name="main", table_name="orders")
    db_session.add_all([source, table])
    await db_session.flush()

    check = AnomalyResult("rule", "row_count_zero", None, "failed", 0, None, None)
    svc = IncidentService()
    incident = await svc.create_or_update(db_session, source.org_id, table, [check], uuid.uuid4())
    incident.status = "muted"
    incident.llm_narration = {"muted_until": (datetime.now(UTC) + timedelta(hours=2)).isoformat()}
    await db_session.flush()

    repeated = await svc.create_or_update(db_session, source.org_id, table, [check], uuid.uuid4())

    assert repeated is None
    rows = (await db_session.execute(Incident.__table__.select())).all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_false_positive_suppresses_identical_future_incidents(db_session, test_org):
    from app.models.data_source import DataSource
    from app.models.incident import Incident
    from app.models.monitored_table import MonitoredTable
    from app.services.anomaly import AnomalyResult
    from app.services.incident import IncidentService

    source = DataSource(
        id=uuid.uuid4(),
        org_id=uuid.UUID(test_org["org_id"]),
        name="Source",
        type="duckdb",
        connection_config={"encrypted": "x"},
        status="connected",
    )
    table = MonitoredTable(id=uuid.uuid4(), source_id=source.id, schema_name="main", table_name="orders")
    db_session.add_all([source, table])
    await db_session.flush()

    check = AnomalyResult("z_score", "z_score_row_count", None, "failed", 750, {"low": 490, "high": 510}, 4.2)
    svc = IncidentService()
    incident = await svc.create_or_update(db_session, source.org_id, table, [check], uuid.uuid4())
    incident.status = "ignored"
    incident.llm_narration = {"false_positive_until": (datetime.now(UTC) + timedelta(days=7)).isoformat()}
    await db_session.flush()

    repeated = await svc.create_or_update(db_session, source.org_id, table, [check], uuid.uuid4())

    assert repeated is None
    rows = (await db_session.execute(Incident.__table__.select())).all()
    assert len(rows) == 1
