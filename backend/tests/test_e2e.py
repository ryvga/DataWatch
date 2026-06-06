"""
End-to-end integration tests: connect → profile → detect → alert

Scenarios:
  1. Pipeline failure detection (P1, rule-based)
  2. Schema drift detection (P2)
  3. Incident deduplication
  4. Auto-resolve

LLM calls are mocked. httpx Slack/PD calls are mocked.
No OPENROUTER_API_KEY required.
"""
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from tests.conftest import MOCK_NARRATION, seed_profiles


# ── Helpers ────────────────────────────────────────────────────────────────────

def duckdb_source_config():
    """In-memory DuckDB — no external warehouse needed."""
    return {
        "name": "Test DuckDB",
        "type": "duckdb",
        "connection_config": {"path": ":memory:"},
    }


async def register_source(client, auth_headers, config=None):
    config = config or duckdb_source_config()
    resp = await client.post("/api/v1/sources", json=config, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def register_table(client, auth_headers, source_id: str, **kwargs):
    body = {
        "source_id": source_id,
        "schema_name": "main",
        "table_name": "orders",
        "freshness_column": "created_at",
        "check_interval_minutes": 60,
        "sensitivity": 3.0,
        **kwargs,
    }
    # Patch scheduler.add_table_job to no-op
    with patch("app.scheduler.add_table_job"), \
         patch("app.tasks.profile_table") as mock_task, \
         patch("app.tasks.bootstrap_table_autopilot") as mock_autopilot:
        mock_task.delay = MagicMock()
        mock_autopilot.delay = MagicMock()
        resp = await client.post("/api/v1/tables", json=body, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_delete_source_archives_source_and_deactivates_tables(client, auth_headers, db_session, test_org):
    from app.models.data_source import DataSource
    from app.models.monitored_table import MonitoredTable

    source = await register_source(client, auth_headers)
    table = await register_table(client, auth_headers, source["id"])

    resp = await client.delete(f"/api/v1/sources/{source['id']}", headers=auth_headers)
    assert resp.status_code == 204

    resp = await client.get("/api/v1/sources", headers=auth_headers)
    assert resp.status_code == 200
    assert all(item["id"] != source["id"] for item in resp.json())

    archived_source = await db_session.get(DataSource, uuid.UUID(source["id"]))
    archived_table = await db_session.get(MonitoredTable, uuid.UUID(table["id"]))
    assert archived_source.status == "paused"
    assert archived_table.is_active is False


async def run_anomaly_checks_directly(db_session, table_id: str, profile_id: str):
    """Call the async anomaly function directly (bypassing Celery)."""
    from app.tasks import _run_anomaly_checks_async
    with patch("app.services.llm.generate_narration", return_value=MOCK_NARRATION), \
         patch("app.tasks.generate_llm_narration") as mock_llm, \
         patch("app.tasks.send_alerts") as mock_alerts:
        mock_llm.delay = MagicMock()
        mock_alerts.delay = MagicMock()
        # Patch AsyncSessionLocal to reuse test session
        with patch("app.database.AsyncSessionLocal") as mock_session_factory:
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock(return_value=db_session)
            mock_cm.__aexit__ = AsyncMock(return_value=False)
            mock_session_factory.return_value = mock_cm
            result = await _run_anomaly_checks_async(table_id, profile_id)
    return result


# ── Scenario 1: Pipeline Failure ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_failure_detection(client, auth_headers, db_session, test_org):
    """row_count=0 → rule-based check → P1 incident created."""
    from app.models.table_profile import TableProfile

    # Setup
    source = await register_source(client, auth_headers)
    table = await register_table(client, auth_headers, source["id"])
    table_id = table["id"]

    # Seed 30-day baseline
    await seed_profiles(db_session, table_id, days=30, row_count=500)

    # Insert anomalous profile: row_count=0
    bad_profile = TableProfile(
        id=uuid.uuid4(),
        table_id=table_id,
        collected_at=datetime.now(UTC),
        row_count=0,
        freshness_seconds=259200.0,  # 3 days stale
        schema_fingerprint="fp_abc123",
        column_metrics={"amount": {"null_rate": 0.0, "mean": None}},
        profiling_duration_ms=150,
    )
    db_session.add(bad_profile)
    await db_session.flush()

    # Run anomaly checks
    result = await run_anomaly_checks_directly(db_session, table_id, str(bad_profile.id))

    assert result["failed"] >= 1, f"Expected failures, got: {result}"

    # Assert incident created
    resp = await client.get("/api/v1/incidents?status=open", headers=auth_headers)
    assert resp.status_code == 200
    incidents = resp.json()
    assert len(incidents) == 1, f"Expected 1 open incident, got {len(incidents)}"
    incident = incidents[0]
    assert incident["severity"] == "P1"
    check_names = [c["check_name"] for c in incident["fired_checks"]]
    assert "row_count_zero" in check_names, f"Expected row_count_zero in {check_names}"


# ── Scenario 2: Schema Drift ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_schema_drift_detection(client, auth_headers, db_session, test_org):
    """Schema fingerprint change → schema_drift rule check → P2 incident."""
    from app.models.table_profile import TableProfile

    source = await register_source(client, auth_headers)
    table = await register_table(client, auth_headers, source["id"])
    table_id = table["id"]

    # Seed baseline with fingerprint A
    await seed_profiles(db_session, table_id, days=10, fingerprint="fp_original")

    # Insert profile with different fingerprint (column dropped)
    drifted_profile = TableProfile(
        id=uuid.uuid4(),
        table_id=table_id,
        collected_at=datetime.now(UTC),
        row_count=498,
        freshness_seconds=3600.0,
        schema_fingerprint="fp_after_schema_change",
        column_metrics={"amount": {"null_rate": 0.01}},
        profiling_duration_ms=200,
    )
    db_session.add(drifted_profile)
    await db_session.flush()

    result = await run_anomaly_checks_directly(db_session, table_id, str(drifted_profile.id))

    resp = await client.get("/api/v1/incidents?status=open", headers=auth_headers)
    incidents = resp.json()
    assert len(incidents) >= 1
    check_names = [c["check_name"] for c in incidents[0]["fired_checks"]]
    assert "schema_drift" in check_names, f"Expected schema_drift in {check_names}"
    assert incidents[0]["severity"] in ("P1", "P2")


# ── Scenario 3: Deduplication ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_incident_deduplication(client, auth_headers, db_session, test_org):
    """Two anomalous profiles → still only ONE open incident."""
    from app.models.table_profile import TableProfile

    source = await register_source(client, auth_headers)
    table = await register_table(client, auth_headers, source["id"])
    table_id = table["id"]

    await seed_profiles(db_session, table_id, days=30, row_count=500)

    # First anomalous profile
    p1 = TableProfile(
        id=uuid.uuid4(), table_id=table_id, collected_at=datetime.now(UTC) - timedelta(hours=2),
        row_count=0, freshness_seconds=10000.0, schema_fingerprint="fp_abc123",
        column_metrics={}, profiling_duration_ms=100,
    )
    db_session.add(p1)
    await db_session.flush()
    await run_anomaly_checks_directly(db_session, table_id, str(p1.id))

    # Second anomalous profile — same issue
    p2 = TableProfile(
        id=uuid.uuid4(), table_id=table_id, collected_at=datetime.now(UTC),
        row_count=0, freshness_seconds=17200.0, schema_fingerprint="fp_abc123",
        column_metrics={}, profiling_duration_ms=100,
    )
    db_session.add(p2)
    await db_session.flush()
    await run_anomaly_checks_directly(db_session, table_id, str(p2.id))

    resp = await client.get("/api/v1/incidents?status=open", headers=auth_headers)
    incidents = resp.json()
    assert len(incidents) == 1, f"Deduplication failed — got {len(incidents)} incidents instead of 1"


# ── Scenario 4: Auto-Resolve ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_auto_resolve(client, auth_headers, db_session, test_org):
    """Incident auto-resolves when anomalous checks pass on next profile run."""
    from app.models.table_profile import TableProfile

    source = await register_source(client, auth_headers)
    table = await register_table(client, auth_headers, source["id"])
    table_id = table["id"]

    await seed_profiles(db_session, table_id, days=30, row_count=500)

    # Create incident
    bad = TableProfile(
        id=uuid.uuid4(), table_id=table_id, collected_at=datetime.now(UTC) - timedelta(hours=1),
        row_count=0, freshness_seconds=5000.0, schema_fingerprint="fp_abc123",
        column_metrics={}, profiling_duration_ms=100,
    )
    db_session.add(bad)
    await db_session.flush()
    await run_anomaly_checks_directly(db_session, table_id, str(bad.id))

    resp = await client.get("/api/v1/incidents?status=open", headers=auth_headers)
    assert len(resp.json()) == 1, "Expected 1 open incident after bad profile"

    # Recovery profile — row_count back to normal
    good = TableProfile(
        id=uuid.uuid4(), table_id=table_id, collected_at=datetime.now(UTC),
        row_count=503, freshness_seconds=3500.0, schema_fingerprint="fp_abc123",
        column_metrics={"amount": {"null_rate": 0.01}}, profiling_duration_ms=180,
    )
    db_session.add(good)
    await db_session.flush()
    await run_anomaly_checks_directly(db_session, table_id, str(good.id))

    resp = await client.get("/api/v1/incidents?status=resolved", headers=auth_headers)
    resolved = resp.json()
    assert len(resolved) >= 1, "Expected at least 1 resolved incident after recovery profile"
    assert resolved[0]["resolved_at"] is not None
