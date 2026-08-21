import uuid
import os
import socket
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import duckdb
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.data_source import DataSource
from app.models.alert_config import AlertConfig
from app.models.incident import Incident
from app.models.monitor import Monitor, MonitorRevision, MonitorRun
from app.models.monitored_table import MonitoredTable
from app.models.organization import Organization
from app.models.table_profile import TableProfile
from app.services.crypto import encrypt_config
from app.services.monitor_dsl import MonitorDefinition, definition_hash, persisted_definition_payload
from app.services.schema_binding import build_relation_binding


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


def _mongo_row_count_definition(table_id: uuid.UUID) -> MonitorDefinition:
    payload = _row_count_definition(table_id).model_dump(
        mode="json",
        by_alias=True,
        exclude_unset=True,
    )
    payload["spec"]["execution"].pop("maxBytesScanned", None)
    payload["spec"]["execution"]["maxDocumentsScanned"] = 10
    payload["spec"]["execution"]["sampling"] = {"mode": "off"}
    return MonitorDefinition.model_validate(payload)


def _cassandra_row_count_definition(table_id: uuid.UUID) -> MonitorDefinition:
    payload = _row_count_definition(table_id).model_dump(
        mode="json",
        by_alias=True,
        exclude_unset=True,
    )
    payload["spec"]["trigger"] = {"type": "manual"}
    payload["spec"]["execution"].pop("maxBytesScanned", None)
    payload["spec"]["execution"].pop("maxDocumentsScanned", None)
    payload["spec"]["execution"]["maxRowsScanned"] = 10
    payload["spec"]["execution"]["partitionBindings"] = {"tenant_id": "tenant-a"}
    payload["spec"]["execution"]["sampling"] = {"mode": "off"}
    return MonitorDefinition.model_validate(payload)


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
    alert_config = AlertConfig(
        org_id=org.id,
        table_id=table.id,
        channel="webhook",
        config={"url": "https://alerts.example.test/datawatch", "secret": "test-secret"},
    )
    db_session.add(alert_config)
    profile_one = TableProfile(
        table_id=table.id,
        row_count=0,
        schema_fingerprint=None,
        collected_at=datetime(2026, 8, 21, 1, 0, tzinfo=UTC),
    )
    db_session.add(profile_one)
    await db_session.commit()

    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    with (
        patch.object(database, "AsyncSessionLocal", session_factory),
        patch("app.tasks.generate_llm_narration") as narration,
    ):
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

    # Continue through the real narration persistence and alert-routing task
    # boundaries with deterministic provider/transport fixtures.
    narration_payload = {
        "summary": "The orders table is empty.",
        "likely_causes": [{"hypothesis": "Upstream load failed", "probability": "high"}],
        "impact_assessment": "Downstream order analytics are incomplete.",
        "recommended_actions": ["Inspect the upstream load"],
        "data_pattern_notes": "The active row-count monitor observed zero rows.",
        "confidence": "high",
    }
    from app.tasks import _generate_llm_narration_async, _send_alerts_async

    with (
        patch.object(database, "AsyncSessionLocal", session_factory),
        patch("app.services.llm.get_cached_narration", return_value=None),
        patch("app.services.llm.build_context", new=AsyncMock(return_value="deterministic context")),
        patch("app.services.llm.generate_narration", return_value=narration_payload),
        patch("app.services.llm.cache_narration"),
        patch("app.tasks.send_alerts") as queued_alerts,
    ):
        narration_result = await _generate_llm_narration_async(str(incident.id))
        queued_alerts.delay.assert_called_once_with(str(incident.id))

    assert narration_result["status"] == "ok"

    with (
        patch.object(database, "AsyncSessionLocal", session_factory),
        patch("app.services.llm.get_cached_narration", return_value=narration_payload),
        patch("app.services.alert.dispatch_alert", return_value=True) as dispatch,
        patch("app.services.realtime.publish_event", new=AsyncMock()),
    ):
        alert_result = await _send_alerts_async(str(incident.id))

    assert alert_result["alerts_dispatched"] == 1
    assert alert_result["results"][0]["sent"] is True
    dispatch.assert_called_once()
    async with session_factory() as session:
        narrated = await session.get(Incident, incident.id)
        assert narrated.llm_narration == narration_payload

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


@pytest.mark.asyncio
async def test_mongodb_document_monitor_opens_and_resolves_incident(
    db_session,
    test_engine,
):
    """Prove the native Mongo plan through persisted run and incident transitions."""
    try:
        probe = socket.create_connection(("127.0.0.1", 27018), timeout=0.2)
        probe.close()
    except OSError:
        if os.environ.get("REQUIRE_TEST_SERVICES", "").lower() in {"1", "true", "yes"}:
            pytest.fail("MongoDB test service unavailable while REQUIRE_TEST_SERVICES=1")
        pytest.skip("MongoDB test service unavailable")

    from pymongo import AsyncMongoClient

    from app import database
    from app.tasks import _run_one_dsl_monitor

    uri = "mongodb://datawatch-root:datawatch-root@127.0.0.1:27018/?authSource=admin"
    collection_name = f"runtime_monitor_{uuid.uuid4().hex}"
    client = AsyncMongoClient(uri)
    collection = client["datawatch_nosql"][collection_name]
    await collection.insert_one({"bootstrap": True})
    await collection.delete_many({})

    org = Organization(
        name="Mongo Runtime Org",
        slug=f"mongo-runtime-{uuid.uuid4().hex[:8]}",
    )
    db_session.add(org)
    await db_session.flush()
    source = DataSource(
        org_id=org.id,
        name="Mongo Runtime",
        type="mongodb",
        connection_config={
            "encrypted": encrypt_config(
                {
                    "uri": uri,
                    "database": "datawatch_nosql",
                    "tls_mode": "disabled",
                },
                str(org.id),
            )
        },
    )
    db_session.add(source)
    await db_session.flush()
    ddl = f'CREATE COLLECTION "datawatch_nosql"."{collection_name}" ("bootstrap" boolean NULL);'
    table = MonitoredTable(
        source_id=source.id,
        schema_name="datawatch_nosql",
        table_name=collection_name,
        dbt_model_yaml=ddl,
    )
    db_session.add(table)
    await db_session.flush()
    schema_fingerprint = build_relation_binding(
        asset_id=table.id,
        source_type="mongodb",
        schema_name=table.schema_name,
        table_name=table.table_name,
        ddl=ddl,
        latest_schema_fingerprint=None,
    ).schema_fingerprint
    definition = _mongo_row_count_definition(table.id)
    revision = MonitorRevision(
        revision=1,
        definition_version=definition.api_version,
        definition_hash=definition_hash(definition),
        definition=persisted_definition_payload(definition),
        validation_status="valid",
        schema_fingerprint=schema_fingerprint,
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
    first_profile = TableProfile(
        table_id=table.id,
        row_count=0,
        schema_fingerprint=schema_fingerprint,
        collected_at=datetime(2026, 8, 21, 2, 0, tzinfo=UTC),
    )
    db_session.add(first_profile)
    await db_session.commit()

    session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    try:
        with (
            patch.object(database, "AsyncSessionLocal", session_factory),
            patch("app.tasks.generate_llm_narration") as narration,
        ):
            narration.delay = MagicMock()
            first = await _run_one_dsl_monitor(
                str(monitor.id),
                profile_id=str(first_profile.id),
            )
        assert first["status"] == "failed"
        assert first["result"]["incidentAction"] == "open"

        await collection.insert_one({"bootstrap": True})
        async with session_factory() as session:
            second_profile = TableProfile(
                table_id=table.id,
                row_count=1,
                schema_fingerprint=schema_fingerprint,
                collected_at=datetime(2026, 8, 21, 2, 1, tzinfo=UTC),
            )
            session.add(second_profile)
            await session.commit()
            second_profile_id = second_profile.id
        with patch.object(database, "AsyncSessionLocal", session_factory):
            second = await _run_one_dsl_monitor(
                str(monitor.id),
                profile_id=str(second_profile_id),
            )
        assert second["status"] == "passed"
        assert second["result"]["incidentAction"] == "resolve"

        async with session_factory() as session:
            incident = await session.scalar(select(Incident).where(Incident.table_id == table.id))
            runs = (await session.scalars(select(MonitorRun).where(MonitorRun.monitor_id == monitor.id))).all()
            assert incident.status == "resolved"
            assert [run.status for run in runs] == ["failed", "passed"]
            assert all(run.planner_version == "datawatch-v1alpha1-mongodb-1" for run in runs)
    finally:
        await collection.drop()
        await client.close()


@pytest.mark.asyncio
async def test_cassandra_partition_monitor_opens_and_resolves_incident(
    db_session,
    test_engine,
):
    """Prove prepared partition execution through persisted incident transitions."""
    try:
        probe = socket.create_connection(("127.0.0.1", 9043), timeout=0.2)
        probe.close()
    except OSError:
        if os.environ.get("REQUIRE_TEST_SERVICES", "").lower() in {"1", "true", "yes"}:
            pytest.fail("Cassandra test service unavailable while REQUIRE_TEST_SERVICES=1")
        pytest.skip("Cassandra test service unavailable")

    from cassandra.cluster import Cluster

    from app import database
    from app.connectors.cassandra import CassandraConnector
    from app.tasks import _run_one_dsl_monitor

    keyspace = f"runtime_monitor_{uuid.uuid4().hex}"
    cluster = Cluster(["127.0.0.1"], port=9043)
    session = cluster.connect()
    session.execute(
        f"CREATE KEYSPACE \"{keyspace}\" WITH replication = {{'class': 'SimpleStrategy', 'replication_factor': 1}}"
    )
    session.execute(
        f'CREATE TABLE "{keyspace}"."events" (tenant_id text, event_id int, PRIMARY KEY (tenant_id, event_id))'
    )
    connector = CassandraConnector(
        {
            "hosts": "127.0.0.1",
            "port": 9043,
            "keyspace": keyspace,
            "tls_mode": "disabled",
        }
    )
    ddl = await connector.get_table_ddl(keyspace, "events")

    org = Organization(
        name="Cassandra Runtime Org",
        slug=f"cassandra-runtime-{uuid.uuid4().hex[:8]}",
    )
    db_session.add(org)
    await db_session.flush()
    source = DataSource(
        org_id=org.id,
        name="Cassandra Runtime",
        type="cassandra",
        connection_config={
            "encrypted": encrypt_config(
                {
                    "hosts": "127.0.0.1",
                    "port": 9043,
                    "keyspace": keyspace,
                    "tls_mode": "disabled",
                },
                str(org.id),
            )
        },
    )
    db_session.add(source)
    await db_session.flush()
    table = MonitoredTable(
        source_id=source.id,
        schema_name=keyspace,
        table_name="events",
        dbt_model_yaml=ddl,
    )
    db_session.add(table)
    await db_session.flush()
    schema_fingerprint = build_relation_binding(
        asset_id=table.id,
        source_type="cassandra",
        schema_name=table.schema_name,
        table_name=table.table_name,
        ddl=ddl,
        latest_schema_fingerprint=None,
    ).schema_fingerprint
    definition = _cassandra_row_count_definition(table.id)
    revision = MonitorRevision(
        revision=1,
        definition_version=definition.api_version,
        definition_hash=definition_hash(definition),
        definition=persisted_definition_payload(definition),
        validation_status="valid",
        schema_fingerprint=schema_fingerprint,
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
    await db_session.commit()

    session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    try:
        with (
            patch.object(database, "AsyncSessionLocal", session_factory),
            patch("app.tasks.generate_llm_narration") as narration,
        ):
            narration.delay = MagicMock()
            first = await _run_one_dsl_monitor(
                str(monitor.id),
                client_idempotency_key="cassandra-empty",
            )
        assert first["status"] == "failed"
        assert first["result"]["incidentAction"] == "open"

        session.execute(
            f'INSERT INTO "{keyspace}"."events" (tenant_id, event_id) VALUES (%s, %s)',
            ("tenant-a", 1),
        )
        with patch.object(database, "AsyncSessionLocal", session_factory):
            second = await _run_one_dsl_monitor(
                str(monitor.id),
                client_idempotency_key="cassandra-recovered",
            )
        assert second["status"] == "passed"
        assert second["result"]["incidentAction"] == "resolve"

        async with session_factory() as audit_session:
            incident = await audit_session.scalar(select(Incident).where(Incident.table_id == table.id))
            runs = (await audit_session.scalars(select(MonitorRun).where(MonitorRun.monitor_id == monitor.id))).all()
            assert incident.status == "resolved"
            assert [run.status for run in runs] == ["failed", "passed"]
            assert all(run.planner_version == "datawatch-v1alpha1-cassandra-1" for run in runs)
    finally:
        await connector.close()
        session.execute(f'DROP KEYSPACE IF EXISTS "{keyspace}"')
        cluster.shutdown()
