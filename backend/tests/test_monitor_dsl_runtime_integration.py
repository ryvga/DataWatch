import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.data_source import DataSource
from app.models.incident import Incident
from app.models.monitor import Monitor, MonitorRevision, MonitorRun
from app.models.monitored_table import MonitoredTable
from app.models.organization import Organization
from app.models.table_profile import TableProfile
from app.services.crypto import encrypt_config
from app.services.monitor_dsl import MonitorDefinition, definition_hash, persisted_definition_payload


def _row_count_definition(table_id: uuid.UUID) -> MonitorDefinition:
    return MonitorDefinition.model_validate(
        {
            "apiVersion": "datawatch.io/v1alpha1",
            "kind": "Monitor",
            "metadata": {"name": "row-count-zero", "labels": {"team": "data"}},
            "spec": {
                "target": {"assetId": str(table_id)},
                "trigger": {"type": "on_profile"},
                "measurements": [{"id": "rows", "type": "metric", "metric": "row_count"}],
                "breachWhen": {
                    "op": "lte",
                    "left": {"ref": "rows"},
                    "right": {"literal": 0},
                },
                "policy": {
                    "severity": "P1",
                    "consecutiveBreaches": 1,
                    "recoveryPasses": 1,
                    "cooldownMinutes": 60,
                    "notifyOnExecutionError": True,
                },
                "execution": {
                    "timeoutSeconds": 30,
                    "maxBytesScanned": 1_000_000,
                    "maxDocumentsScanned": 1_000_000,
                    "sampling": {"mode": "auto"},
                },
            },
        }
    )


@pytest.mark.asyncio
async def test_profile_run_incident_recovery_vertical_slice(db_session, test_engine, tmp_path: Path):
    """Exercise the real task boundary against DuckDB and the real Postgres audit DB."""
    from app import database
    from app.tasks import _run_one_dsl_monitor

    duck_path = tmp_path / "safe-monitor.duckdb"
    duck = duckdb.connect(str(duck_path))
    duck.execute("CREATE TABLE main.orders (id INTEGER NOT NULL)")
    duck.close()

    org = Organization(name="DSL Runtime Org", slug=f"dsl-runtime-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    await db_session.flush()
    source = DataSource(
        org_id=org.id,
        name="DSL DuckDB",
        type="duckdb",
        connection_config={"encrypted": encrypt_config({"path": str(duck_path)}, str(org.id))},
    )
    db_session.add(source)
    await db_session.flush()
    table = MonitoredTable(
        source_id=source.id,
        schema_name="main",
        table_name="orders",
        dbt_model_yaml="CREATE TABLE main.orders (id integer NOT NULL);",
    )
    db_session.add(table)
    await db_session.flush()
    definition = _row_count_definition(table.id)
    revision = MonitorRevision(
        revision=1,
        definition_version=definition.api_version,
        definition_hash=definition_hash(definition),
        definition=persisted_definition_payload(definition),
        validation_status="valid",
        schema_fingerprint=None,
    )
    monitor = Monitor(
        org_id=org.id,
        table_id=table.id,
        name=definition.metadata.name,
        mode="dsl",
        status="draft",
        current_revision=1,
    )
    db_session.add(monitor)
    await db_session.flush()
    revision.monitor_id = monitor.id
    db_session.add(revision)
    await db_session.flush()
    monitor.active_revision_id = revision.id
    monitor.status = "active"
    profile_one = TableProfile(
        table_id=table.id,
        row_count=0,
        schema_fingerprint=None,
        collected_at=datetime(2026, 8, 21, 1, 0, tzinfo=UTC),
    )
    db_session.add(profile_one)
    await db_session.commit()

    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    with patch.object(database, "AsyncSessionLocal", session_factory), patch(
        "app.tasks.generate_llm_narration"
    ) as narration:
        narration.delay = MagicMock()
        first = await _run_one_dsl_monitor(str(monitor.id), profile_id=str(profile_one.id))

    assert first["status"] == "failed"
    assert first["result"]["incidentAction"] == "open"
    async with session_factory() as session:
        incident = await session.scalar(select(Incident).where(Incident.table_id == table.id))
        first_run = await session.scalar(select(MonitorRun).where(MonitorRun.id == first["run_id"]))
        assert incident is not None
        assert incident.status == "open"
        assert incident.fired_checks[0]["check_type"] == "monitor_dsl"
        assert first_run.status == "failed"

    duck = duckdb.connect(str(duck_path))
    duck.execute("INSERT INTO main.orders VALUES (1)")
    duck.close()
    async with session_factory() as session:
        profile_two = TableProfile(
            table_id=table.id,
            row_count=1,
            schema_fingerprint=None,
            collected_at=datetime(2026, 8, 21, 1, 1, tzinfo=UTC),
        )
        session.add(profile_two)
        await session.commit()
        profile_two_id = profile_two.id

    with patch.object(database, "AsyncSessionLocal", session_factory):
        second = await _run_one_dsl_monitor(str(monitor.id), profile_id=str(profile_two_id))

    assert second["status"] == "passed"
    assert second["result"]["incidentAction"] == "resolve"
    async with session_factory() as session:
        incident = await session.scalar(select(Incident).where(Incident.table_id == table.id))
        assert incident.status == "resolved"
        runs = (await session.scalars(select(MonitorRun).where(MonitorRun.monitor_id == monitor.id))).all()
        assert [run.status for run in runs] == ["failed", "passed"]
