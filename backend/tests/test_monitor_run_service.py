import asyncio
import importlib.util
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.data_source import DataSource
from app.models.monitor import Monitor, MonitorEvaluationState, MonitorRevision, MonitorRun
from app.models.monitored_table import MonitoredTable
from app.models.organization import Organization
from app.models.table_profile import TableProfile
from app.services.monitor_compiler import compile_relational_plan
from app.services.monitor_dsl import MonitorDefinition, definition_hash
from app.services.monitor_run_service import (
    MonitorRunError,
    RunRequest,
    claim_next_run,
    finalize_error,
    finalize_success,
    manual_idempotency_key,
    profile_idempotency_key,
    renew_claim,
    reserve_run,
)
from app.services.schema_binding import build_relation_binding
from tests.test_monitor_dsl import valid_definition


def test_idempotency_keys_are_fixed_length_and_context_scoped():
    monitor_id, revision_id, profile_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    profile_key = profile_idempotency_key(monitor_id, revision_id, profile_id)
    manual_key = manual_idempotency_key(monitor_id, revision_id, "client-request-1")

    assert len(profile_key) == 64
    assert len(manual_key) == 64
    assert profile_key != manual_key
    assert manual_key != manual_idempotency_key(monitor_id, revision_id, "client-request-2")


@pytest.mark.asyncio
async def test_run_request_rejects_trigger_and_time_contract_before_database_access():
    class DatabaseMustNotRun:
        async def scalar(self, _statement):
            raise AssertionError("database should not be called")

    request = RunRequest(
        org_id=uuid.uuid4(),
        monitor_id=uuid.uuid4(),
        revision_id=uuid.uuid4(),
        trigger_type="on_profile",
        profile_id=None,
    )
    with pytest.raises(MonitorRunError) as exc:
        await reserve_run(
            DatabaseMustNotRun(),
            request,
            now=datetime(2026, 7, 19, 20, 0),
        )
    assert exc.value.code == "sequence_time_invalid"


async def _runtime_fixture(db_session):
    org = Organization(name="Run Org", slug=f"run-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    await db_session.flush()
    source = DataSource(
        org_id=org.id,
        name="Run DB",
        type="sqlite",
        connection_config={"encrypted": "unused"},
    )
    db_session.add(source)
    await db_session.flush()
    table = MonitoredTable(
        source_id=source.id,
        schema_name="main",
        table_name="orders",
        dbt_model_yaml=(
            "CREATE TABLE main.orders ("
            "status text NULL, payment_reference text NULL"
            ");"
        ),
    )
    db_session.add(table)
    await db_session.flush()
    body = valid_definition()
    body["spec"]["target"]["assetId"] = str(table.id)
    definition = MonitorDefinition.model_validate(body)
    monitor = Monitor(
        org_id=org.id,
        table_id=table.id,
        name=definition.metadata.name,
        status="draft",
    )
    db_session.add(monitor)
    await db_session.flush()
    revision = MonitorRevision(
        monitor_id=monitor.id,
        revision=1,
        definition_version=definition.api_version,
        definition_hash=definition_hash(definition),
        definition=definition.model_dump(mode="json", by_alias=True),
        schema_fingerprint=None,
    )
    db_session.add(revision)
    await db_session.flush()
    monitor.active_revision_id = revision.id
    monitor.status = "active"
    profile = TableProfile(
        table_id=table.id,
        row_count=3,
        schema_fingerprint=None,
        collected_at=datetime(2026, 7, 19, 20, 0, tzinfo=UTC),
    )
    db_session.add(profile)
    await db_session.flush()
    relation = build_relation_binding(
        asset_id=table.id,
        source_type="sqlite",
        schema_name="main",
        table_name="orders",
        ddl=table.dbt_model_yaml,
        latest_schema_fingerprint=None,
    )
    plan = compile_relational_plan(definition, relation=relation)
    return org, table, monitor, revision, profile, definition, plan


@pytest.mark.asyncio
async def test_persisted_run_reservation_claim_success_and_duplicate_delivery(db_session):
    org, table, monitor, revision, profile, definition, plan = await _runtime_fixture(db_session)
    now = datetime(2026, 7, 19, 20, 0, tzinfo=UTC)
    request = RunRequest(
        org_id=org.id,
        monitor_id=monitor.id,
        revision_id=revision.id,
        trigger_type="on_profile",
        profile_id=profile.id,
    )

    first = await reserve_run(db_session, request, now=now)
    duplicate = await reserve_run(db_session, request, now=now)
    assert first.acquired is True
    assert duplicate.acquired is False
    assert duplicate.run_id == first.run_id

    claim = await claim_next_run(
        db_session,
        org_id=org.id,
        run_id=first.run_id,
        now=now,
    )
    assert claim is not None
    run = await finalize_success(
        db_session,
        org_id=org.id,
        claim=claim,
        plan=plan,
        definition_hash=definition_hash(definition),
        measurements={"invalid_orders.count": 1, "invalid_orders.rate": 1 / 3},
        now=now + timedelta(seconds=1),
    )
    assert run.status == "failed"
    assert run.result["transition"] == "breach_pending"
    assert await claim_next_run(
        db_session,
        org_id=org.id,
        run_id=run.id,
        now=now + timedelta(minutes=5),
    ) is None
    state = await db_session.scalar(
        select(MonitorEvaluationState).where(MonitorEvaluationState.monitor_id == monitor.id)
    )
    assert state.phase == "healthy"
    assert state.breach_streak == 1
    assert state.last_run_id == run.id
    assert state.last_idempotency_key == run.idempotency_key
    assert run.claim_token is None


@pytest.mark.asyncio
async def test_expired_claim_replaces_token_and_old_worker_cannot_finalize(db_session):
    org, table, monitor, revision, profile, definition, plan = await _runtime_fixture(db_session)
    now = datetime(2026, 7, 19, 20, 0, tzinfo=UTC)
    request = RunRequest(
        org_id=org.id,
        monitor_id=monitor.id,
        revision_id=revision.id,
        trigger_type="on_profile",
        profile_id=profile.id,
    )
    reservation = await reserve_run(db_session, request, now=now)
    old = await claim_next_run(
        db_session, org_id=org.id, run_id=reservation.run_id, now=now, lease_seconds=10
    )
    reclaimed = await claim_next_run(
        db_session,
        org_id=org.id,
        run_id=reservation.run_id,
        now=now + timedelta(seconds=11),
        lease_seconds=10,
    )
    assert reclaimed is not None and old is not None
    assert reclaimed.claim_token != old.claim_token
    assert reclaimed.attempt == 2

    with pytest.raises(MonitorRunError) as exc:
        await finalize_error(
            db_session,
            org_id=org.id,
            claim=old,
            error_code="execution_timeout",
            now=now + timedelta(seconds=12),
        )
    assert exc.value.code == "claim_lost"


@pytest.mark.asyncio
async def test_run_error_is_allowlisted_and_cannot_persist_connector_details(db_session):
    org, table, monitor, revision, profile, _, plan = await _runtime_fixture(db_session)
    now = datetime(2026, 7, 19, 20, 0, tzinfo=UTC)
    request = RunRequest(
        org_id=org.id,
        monitor_id=monitor.id,
        revision_id=revision.id,
        trigger_type="on_profile",
        profile_id=profile.id,
    )
    reservation = await reserve_run(db_session, request, now=now)
    claim = await claim_next_run(db_session, org_id=org.id, run_id=reservation.run_id, now=now)
    assert claim is not None

    with pytest.raises(MonitorRunError):
        await finalize_error(
            db_session,
            org_id=org.id,
            claim=claim,
            error_code="password=secret host=internal",
            now=now,
        )
    run = await finalize_error(
        db_session,
        org_id=org.id,
        claim=claim,
        error_code="execution_failed",
        now=now,
    )
    assert run.status == "error"
    assert run.error == "Compiled monitor execution failed"
    assert "secret" not in run.error
    assert run.result["notificationEligible"] is True
    assert run.claim_token is None


@pytest.mark.asyncio
async def test_expired_claim_cannot_finalize_but_a_live_claim_can_be_renewed(db_session):
    org, _, monitor, revision, profile, _, _ = await _runtime_fixture(db_session)
    now = datetime(2026, 7, 19, 20, 0, tzinfo=UTC)
    reservation = await reserve_run(
        db_session,
        RunRequest(
            org_id=org.id,
            monitor_id=monitor.id,
            revision_id=revision.id,
            trigger_type="on_profile",
            profile_id=profile.id,
        ),
        now=now,
    )
    claim = await claim_next_run(
        db_session,
        org_id=org.id,
        run_id=reservation.run_id,
        now=now,
        lease_seconds=10,
    )
    assert claim is not None
    renewed = await renew_claim(
        db_session,
        org_id=org.id,
        claim=claim,
        now=now + timedelta(seconds=5),
        lease_seconds=30,
    )
    assert renewed is not None
    assert renewed.lease_expires_at == now + timedelta(seconds=35)

    with pytest.raises(MonitorRunError) as exc:
        await finalize_error(
            db_session,
            org_id=org.id,
            claim=renewed,
            error_code="execution_timeout",
            now=now + timedelta(seconds=36),
        )
    assert exc.value.code == "claim_expired"


@pytest.mark.asyncio
async def test_manual_run_retry_reuses_the_original_reservation(db_session):
    org, _, monitor, revision, _, _, _ = await _runtime_fixture(db_session)
    first_at = datetime(2026, 7, 19, 20, 0, tzinfo=UTC)
    request = RunRequest(
        org_id=org.id,
        monitor_id=monitor.id,
        revision_id=revision.id,
        trigger_type="manual",
        profile_id=None,
        client_idempotency_key="operator-request-1",
    )
    first = await reserve_run(db_session, request, now=first_at)
    retry = await reserve_run(db_session, request, now=first_at + timedelta(minutes=5))

    assert first.acquired is True
    assert retry.acquired is False
    assert retry.run_id == first.run_id
    run = await db_session.get(MonitorRun, first.run_id)
    assert run.sequence_at == first_at


@pytest.mark.asyncio
async def test_finalization_cancels_when_monitor_is_paused_after_claim(db_session):
    org, _, monitor, revision, profile, _, plan = await _runtime_fixture(db_session)
    now = datetime(2026, 7, 19, 20, 0, tzinfo=UTC)
    reservation = await reserve_run(
        db_session,
        RunRequest(
            org_id=org.id,
            monitor_id=monitor.id,
            revision_id=revision.id,
            trigger_type="on_profile",
            profile_id=profile.id,
        ),
        now=now,
    )
    claim = await claim_next_run(
        db_session, org_id=org.id, run_id=reservation.run_id, now=now
    )
    assert claim is not None
    monitor.status = "paused"
    await db_session.flush()

    run = await finalize_success(
        db_session,
        org_id=org.id,
        claim=claim,
        plan=plan,
        definition_hash=revision.definition_hash,
        measurements={"invalid_orders.count": 0, "invalid_orders.rate": 0},
        now=now + timedelta(seconds=1),
    )
    assert run.status == "cancelled"
    assert run.result["reason"] == "inactive_or_stale_revision"


@pytest.mark.asyncio
async def test_renewal_returns_cancelled_when_monitor_is_paused(db_session):
    org, _, monitor, revision, profile, _, _ = await _runtime_fixture(db_session)
    now = datetime(2026, 7, 19, 20, 0, tzinfo=UTC)
    reservation = await reserve_run(
        db_session,
        RunRequest(
            org_id=org.id,
            monitor_id=monitor.id,
            revision_id=revision.id,
            trigger_type="on_profile",
            profile_id=profile.id,
        ),
        now=now,
    )
    claim = await claim_next_run(
        db_session, org_id=org.id, run_id=reservation.run_id, now=now
    )
    assert claim is not None
    monitor.status = "paused"
    await db_session.flush()

    renewed = await renew_claim(
        db_session,
        org_id=org.id,
        claim=claim,
        now=now + timedelta(seconds=1),
    )
    assert renewed is None
    run = await db_session.get(MonitorRun, reservation.run_id)
    assert run.status == "cancelled"


@pytest.mark.asyncio
async def test_claims_are_sequence_ordered_and_only_one_run_is_in_flight(db_session):
    org, table, monitor, revision, first_profile, _, plan = await _runtime_fixture(db_session)
    now = datetime(2026, 7, 19, 20, 0, tzinfo=UTC)
    first_profile.collected_at = now
    second_profile = TableProfile(
        table_id=table.id,
        row_count=4,
        collected_at=now + timedelta(minutes=1),
    )
    db_session.add(second_profile)
    await db_session.flush()

    async def reserve(profile, received_at):
        return await reserve_run(
            db_session,
            RunRequest(
                org_id=org.id,
                monitor_id=monitor.id,
                revision_id=revision.id,
                trigger_type="on_profile",
                profile_id=profile.id,
            ),
            now=received_at,
        )

    earlier = await reserve(first_profile, now)
    later = await reserve(second_profile, now + timedelta(minutes=1))
    assert await claim_next_run(
        db_session,
        org_id=org.id,
        run_id=later.run_id,
        now=now + timedelta(minutes=2),
    ) is None
    first_claim = await claim_next_run(
        db_session,
        org_id=org.id,
        run_id=earlier.run_id,
        now=now + timedelta(minutes=2),
    )
    assert first_claim is not None
    assert await claim_next_run(
        db_session,
        org_id=org.id,
        run_id=later.run_id,
        now=now + timedelta(minutes=2),
    ) is None


@pytest.mark.asyncio
async def test_equal_timestamp_runs_use_idempotency_key_as_the_ordering_cursor(db_session):
    org, _, monitor, revision, _, _, _ = await _runtime_fixture(db_session)
    now = datetime(2026, 7, 19, 20, 0, tzinfo=UTC)

    async def reserve(client_key):
        return await reserve_run(
            db_session,
            RunRequest(
                org_id=org.id,
                monitor_id=monitor.id,
                revision_id=revision.id,
                trigger_type="manual",
                profile_id=None,
                client_idempotency_key=client_key,
            ),
            now=now,
        )

    reservations = [await reserve("same-time-a"), await reserve("same-time-b")]
    runs = [await db_session.get(MonitorRun, item.run_id) for item in reservations]
    ordered = sorted(runs, key=lambda run: run.idempotency_key)

    assert await claim_next_run(
        db_session,
        org_id=org.id,
        run_id=ordered[1].id,
        now=now,
    ) is None
    first_claim = await claim_next_run(
        db_session,
        org_id=org.id,
        run_id=ordered[0].id,
        now=now,
    )
    assert first_claim is not None
    await finalize_error(
        db_session,
        org_id=org.id,
        claim=first_claim,
        error_code="execution_failed",
        now=now + timedelta(seconds=1),
    )
    second_claim = await claim_next_run(
        db_session,
        org_id=org.id,
        run_id=ordered[1].id,
        now=now + timedelta(seconds=2),
    )
    assert second_claim is not None


@pytest.mark.asyncio
async def test_concurrent_workers_cannot_both_claim_the_same_run(db_session, test_engine):
    org, _, monitor, revision, profile, _, _ = await _runtime_fixture(db_session)
    now = datetime(2026, 7, 19, 20, 0, tzinfo=UTC)
    reservation = await reserve_run(
        db_session,
        RunRequest(
            org_id=org.id,
            monitor_id=monitor.id,
            revision_id=revision.id,
            trigger_type="on_profile",
            profile_id=profile.id,
        ),
        now=now,
    )
    org_id, run_id = org.id, reservation.run_id
    await db_session.commit()
    sessions = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def claim_in_transaction():
        async with sessions() as session:
            claim = await claim_next_run(
                session,
                org_id=org_id,
                run_id=run_id,
                now=now,
            )
            await session.commit()
            return claim

    claims = await asyncio.gather(claim_in_transaction(), claim_in_transaction())
    assert sum(claim is not None for claim in claims) == 1
    async with sessions() as session:
        run = await session.get(MonitorRun, run_id)
        assert run.status == "running"
        assert run.attempt == 1


@pytest.mark.asyncio
async def test_database_triggers_protect_audits_and_allow_parent_cascade(db_session):
    migration_path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "012_monitor_runtime_state.py"
    )
    spec = importlib.util.spec_from_file_location("monitor_runtime_guards", migration_path)
    migration = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(migration)

    async def drop_guard_functions():
        await db_session.execute(
            text("DROP FUNCTION IF EXISTS datawatch_reject_terminal_monitor_run_mutation() CASCADE")
        )
        await db_session.execute(
            text("DROP FUNCTION IF EXISTS datawatch_reject_monitor_revision_mutation() CASCADE")
        )

    await drop_guard_functions()
    await db_session.execute(text(migration.REVISION_TRIGGER_FUNCTION_SQL))
    await db_session.execute(text(migration.REVISION_TRIGGER_SQL))
    await db_session.execute(text(migration.RUN_TRIGGER_FUNCTION_SQL))
    await db_session.execute(text(migration.RUN_TRIGGER_SQL))
    await db_session.commit()

    try:
        org, table, monitor, revision, profile, _, _ = await _runtime_fixture(db_session)
        now = datetime(2026, 7, 19, 20, 0, tzinfo=UTC)
        reservation = await reserve_run(
            db_session,
            RunRequest(
                org_id=org.id,
                monitor_id=monitor.id,
                revision_id=revision.id,
                trigger_type="on_profile",
                profile_id=profile.id,
            ),
            now=now,
        )
        claim = await claim_next_run(
            db_session, org_id=org.id, run_id=reservation.run_id, now=now
        )
        assert claim is not None
        await finalize_error(
            db_session,
            org_id=org.id,
            claim=claim,
            error_code="execution_failed",
            now=now + timedelta(seconds=1),
        )
        monitor_id, revision_id, run_id, table_id = (
            monitor.id,
            revision.id,
            reservation.run_id,
            table.id,
        )
        await db_session.commit()

        with pytest.raises(DBAPIError):
            await db_session.execute(
                text("UPDATE monitor_runs SET error = 'rewritten' WHERE id = :id"),
                {"id": run_id},
            )
        await db_session.rollback()
        with pytest.raises(DBAPIError):
            await db_session.execute(
                text("UPDATE monitor_revisions SET definition_hash = :hash WHERE id = :id"),
                {"hash": "0" * 64, "id": revision_id},
            )
        await db_session.rollback()

        persisted_table = await db_session.get(MonitoredTable, table_id)
        await db_session.delete(persisted_table)
        await db_session.commit()
        assert await db_session.get(Monitor, monitor_id) is None
    finally:
        await db_session.rollback()
        await drop_guard_functions()
        await db_session.commit()
