"""Idempotent, ordered state machine for persisted typed-monitor executions."""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_source import DataSource
from app.models.monitor import Monitor, MonitorEvaluationState, MonitorRevision, MonitorRun
from app.models.monitored_table import MonitoredTable
from app.models.table_profile import TableProfile
from app.services.monitor_compiler import (
    PLANNER_VERSION,
    RelationalMonitorPlan,
    compile_relational_plan,
)
from app.services.monitor_dsl import (
    Policy,
    Predicate,
    definition_hash,
    load_persisted_definition,
)
from app.services.monitor_evaluator import PolicyState, evaluate_breach, evaluate_policy
from app.services.schema_binding import build_relation_binding

TERMINAL_STATUSES = {"passed", "failed", "error", "cancelled"}
SAFE_ERROR_MESSAGES = {
    "execution_timeout": "Compiled monitor exceeded its timeout",
    "connector_execution_not_supported": "Connector cannot execute compiled monitors",
    "query_concurrency_exceeded": "Another query is already running for this source",
    "query_lease_unavailable": "Shared query capacity control is unavailable",
    "scan_budget_exceeded": "Compiled monitor exceeds maxBytesScanned",
    "scan_budget_not_supported": "Connector cannot enforce maxBytesScanned",
    "execution_failed": "Compiled monitor execution failed",
    "evaluation_failed": "Compiled monitor evaluation failed",
    "plan_context_mismatch": "Compiled plan no longer matches the reserved run",
}


class MonitorRunError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RunRequest:
    org_id: uuid.UUID
    monitor_id: uuid.UUID
    revision_id: uuid.UUID
    trigger_type: Literal["on_profile", "manual"]
    profile_id: uuid.UUID | None
    client_idempotency_key: str | None = None


@dataclass(frozen=True)
class RunReservation:
    run_id: uuid.UUID
    status: str
    acquired: bool


@dataclass(frozen=True)
class RunClaim:
    run_id: uuid.UUID
    claim_token: uuid.UUID
    attempt: int
    lease_expires_at: datetime


def profile_idempotency_key(monitor_id, revision_id, profile_id) -> str:
    return hashlib.sha256(f"profile:{monitor_id}:{revision_id}:{profile_id}".encode()).hexdigest()


def manual_idempotency_key(monitor_id, revision_id, client_key: str) -> str:
    return hashlib.sha256(f"manual:{monitor_id}:{revision_id}:{client_key}".encode()).hexdigest()


def _validate_request(request: RunRequest, now: datetime) -> None:
    if now.tzinfo is None:
        raise MonitorRunError("sequence_time_invalid", "Run reservation time must be timezone-aware")
    if request.trigger_type not in {"on_profile", "manual"}:
        raise MonitorRunError("trigger_type_invalid", "Run trigger type is invalid")
    if request.trigger_type == "on_profile" and request.profile_id is None:
        raise MonitorRunError("profile_id_required", "Profile-triggered runs require a profile")
    if request.trigger_type == "manual" and request.profile_id is not None:
        raise MonitorRunError("profile_id_forbidden", "Manual runs cannot reference a profile")
    if request.trigger_type == "manual" and not request.client_idempotency_key:
        raise MonitorRunError("idempotency_key_invalid", "Manual runs require an idempotency key")
    if request.client_idempotency_key and len(request.client_idempotency_key) > 512:
        raise MonitorRunError("idempotency_key_invalid", "Client idempotency key is too long")


async def reserve_run(
    db: AsyncSession,
    request: RunRequest,
    *,
    now: datetime,
) -> RunReservation:
    """Atomically reserve one audit row; duplicates never acquire execution ownership."""
    _validate_request(request, now)
    monitor = await db.scalar(
        select(Monitor).where(Monitor.id == request.monitor_id, Monitor.org_id == request.org_id)
    )
    revision = await db.scalar(
        select(MonitorRevision).where(
            MonitorRevision.id == request.revision_id,
            MonitorRevision.monitor_id == request.monitor_id,
        )
    )
    if not monitor or not revision:
        raise MonitorRunError("run_context_invalid", "Run context does not match monitor ownership")
    if monitor.status != "active" or monitor.active_revision_id != revision.id:
        raise MonitorRunError("monitor_not_active", "Monitor revision is not active")
    row = (
        await db.execute(
            select(MonitoredTable, DataSource)
            .join(DataSource, DataSource.id == MonitoredTable.source_id)
            .where(
                MonitoredTable.id == monitor.table_id,
                DataSource.org_id == request.org_id,
            )
        )
    ).one_or_none()
    if row is None:
        raise MonitorRunError("run_context_invalid", "Monitor target is outside the tenant")
    table, source = row
    definition = load_persisted_definition(revision.definition)
    if (
        definition.spec.target.asset_id != table.id
        or definition_hash(definition) != revision.definition_hash
    ):
        raise MonitorRunError("definition_hash_mismatch", "Stored revision context is invalid")

    if request.trigger_type == "on_profile":
        profile = await db.scalar(
            select(TableProfile).where(
                TableProfile.id == request.profile_id,
                TableProfile.table_id == table.id,
                TableProfile.error.is_(None),
            )
        )
        if profile is None:
            raise MonitorRunError(
                "profile_context_invalid",
                "Profile does not belong to the monitor target",
            )
        sequence_at = profile.collected_at
        latest_fingerprint = profile.schema_fingerprint
        idempotency_key = profile_idempotency_key(monitor.id, revision.id, profile.id)
    else:
        sequence_at = now
        latest_fingerprint = None
        idempotency_key = manual_idempotency_key(
            monitor.id,
            revision.id,
            request.client_idempotency_key or "",
        )
    relation = build_relation_binding(
        asset_id=table.id,
        source_type=source.type,
        schema_name=table.schema_name,
        table_name=table.table_name,
        ddl=table.dbt_model_yaml,
        latest_schema_fingerprint=latest_fingerprint,
    )
    plan = compile_relational_plan(definition, relation=relation)
    plan_payload = plan.payload()

    run_id = uuid.uuid4()
    inserted = await db.scalar(
        insert(MonitorRun)
        .values(
            id=run_id,
            org_id=request.org_id,
            monitor_id=request.monitor_id,
            revision_id=request.revision_id,
            table_id=table.id,
            idempotency_key=idempotency_key,
            trigger_type=request.trigger_type,
            profile_id=request.profile_id,
            sequence_at=sequence_at,
            plan_hash=plan_payload["planHash"],
            planner_version=PLANNER_VERSION,
            definition_hash=revision.definition_hash,
            schema_fingerprint=relation.schema_fingerprint,
            status="queued",
            attempt=1,
        )
        .on_conflict_do_nothing(index_elements=["org_id", "idempotency_key"])
        .returning(MonitorRun.id)
    )
    if inserted is not None:
        return RunReservation(run_id=inserted, status="queued", acquired=True)
    existing = await db.scalar(
        select(MonitorRun).where(
            MonitorRun.org_id == request.org_id,
            MonitorRun.idempotency_key == idempotency_key,
        )
    )
    if existing is None:
        raise MonitorRunError("reservation_conflict", "Run reservation conflict was not readable")
    immutable = (
        existing.monitor_id,
        existing.revision_id,
        existing.table_id,
        existing.trigger_type,
        existing.profile_id,
        existing.sequence_at,
        existing.plan_hash,
        existing.planner_version,
        existing.definition_hash,
        existing.schema_fingerprint,
    )
    requested = (
        request.monitor_id,
        request.revision_id,
        table.id,
        request.trigger_type,
        request.profile_id,
        existing.sequence_at if request.trigger_type == "manual" else sequence_at,
        plan_payload["planHash"],
        PLANNER_VERSION,
        revision.definition_hash,
        relation.schema_fingerprint,
    )
    if immutable != requested:
        raise MonitorRunError("idempotency_collision", "Idempotency key belongs to another run context")
    return RunReservation(run_id=existing.id, status=existing.status, acquired=False)


def _cancel(run: MonitorRun, code: str, now: datetime) -> None:
    run.status = "cancelled"
    run.result = {"version": "monitor-run/v1", "reason": code}
    run.completed_at = now
    run.claim_token = None
    run.lease_expires_at = None


async def claim_next_run(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    run_id: uuid.UUID,
    now: datetime,
    lease_seconds: int = 180,
) -> RunClaim | None:
    """Claim only the earliest eligible run; expired leases may be reclaimed."""
    if now.tzinfo is None or not 1 <= lease_seconds <= 900:
        raise MonitorRunError("claim_contract_invalid", "Claim time or lease is invalid")
    run = await db.scalar(
        select(MonitorRun)
        .where(MonitorRun.id == run_id, MonitorRun.org_id == org_id)
        .with_for_update()
    )
    if run is None:
        raise MonitorRunError("run_not_found", "Run was not found")
    if run.status in TERMINAL_STATUSES:
        return None
    if run.status == "running":
        if run.lease_expires_at is not None and run.lease_expires_at > now:
            return None
        run.attempt += 1
    elif run.status != "queued":
        raise MonitorRunError("run_state_invalid", "Run cannot be claimed from its state")

    monitor = await db.scalar(
        select(Monitor)
        .where(Monitor.id == run.monitor_id, Monitor.org_id == org_id)
        .with_for_update()
    )
    if monitor is None or monitor.status != "active" or monitor.active_revision_id != run.revision_id:
        _cancel(run, "inactive_or_stale_revision", now)
        await db.flush()
        return None

    state = await db.scalar(
        select(MonitorEvaluationState)
        .where(
            MonitorEvaluationState.monitor_id == run.monitor_id,
            MonitorEvaluationState.org_id == org_id,
        )
        .with_for_update()
    )
    if state is None:
        state = MonitorEvaluationState(
            monitor_id=run.monitor_id,
            org_id=org_id,
            revision_id=run.revision_id,
        )
        db.add(state)
        await db.flush()
    elif state.revision_id != run.revision_id:
        state.revision_id = run.revision_id
        state.phase = "healthy"
        state.breach_streak = 0
        state.recovery_streak = 0
        state.cooldown_until = None
        state.last_run_id = None
        state.last_sequence_at = None
        state.last_idempotency_key = None
        state.version += 1
    if state.last_sequence_at is not None and (
        run.sequence_at < state.last_sequence_at
        or (
            run.sequence_at == state.last_sequence_at
            and state.last_idempotency_key is not None
            and run.idempotency_key <= state.last_idempotency_key
        )
    ):
        _cancel(run, "stale_trigger", now)
        await db.flush()
        return None

    earlier = await db.scalar(
        select(MonitorRun.id)
        .where(
            MonitorRun.monitor_id == run.monitor_id,
            MonitorRun.status == "queued",
            MonitorRun.id != run.id,
            or_(
                MonitorRun.sequence_at < run.sequence_at,
                and_(
                    MonitorRun.sequence_at == run.sequence_at,
                    MonitorRun.idempotency_key < run.idempotency_key,
                ),
            ),
        )
        .limit(1)
    )
    if earlier is not None:
        return None
    other_running = await db.scalar(
        select(MonitorRun.id)
        .where(
            MonitorRun.monitor_id == run.monitor_id,
            MonitorRun.status == "running",
            MonitorRun.id != run.id,
        )
        .limit(1)
    )
    if other_running is not None:
        return None

    token = uuid.uuid4()
    lease_expires_at = now + timedelta(seconds=lease_seconds)
    run.status = "running"
    run.claim_token = token
    run.started_at = now
    run.lease_expires_at = lease_expires_at
    await db.flush()
    return RunClaim(run.id, token, run.attempt, lease_expires_at)


async def _claimed_run(
    db: AsyncSession,
    org_id: uuid.UUID,
    claim: RunClaim,
    now: datetime,
) -> MonitorRun:
    if now.tzinfo is None:
        raise MonitorRunError("finalization_time_invalid", "Finalization time must be timezone-aware")
    run = await db.scalar(
        select(MonitorRun)
        .where(MonitorRun.id == claim.run_id, MonitorRun.org_id == org_id)
        .with_for_update()
    )
    if run is None:
        raise MonitorRunError("run_not_found", "Run was not found")
    if run.status in TERMINAL_STATUSES:
        return run
    if run.status != "running" or run.claim_token != claim.claim_token:
        raise MonitorRunError("claim_lost", "Run claim is no longer current")
    if run.lease_expires_at is None or run.lease_expires_at <= now:
        raise MonitorRunError("claim_expired", "Run claim lease has expired")
    monitor = await db.scalar(
        select(Monitor)
        .where(Monitor.id == run.monitor_id, Monitor.org_id == org_id)
        .with_for_update()
    )
    if monitor is None or monitor.status != "active" or monitor.active_revision_id != run.revision_id:
        _cancel(run, "inactive_or_stale_revision", now)
        await db.flush()
    return run


async def renew_claim(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    claim: RunClaim,
    now: datetime,
    lease_seconds: int = 180,
) -> RunClaim | None:
    """Extend a live execution lease; expired or replaced workers cannot renew it."""
    if not 1 <= lease_seconds <= 900:
        raise MonitorRunError("claim_contract_invalid", "Claim lease is invalid")
    run = await _claimed_run(db, org_id, claim, now)
    if run.status in TERMINAL_STATUSES:
        return None
    run.lease_expires_at = now + timedelta(seconds=lease_seconds)
    await db.flush()
    return RunClaim(run.id, claim.claim_token, run.attempt, run.lease_expires_at)


async def finalize_success(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    claim: RunClaim,
    plan: RelationalMonitorPlan,
    definition_hash: str,
    measurements: dict,
    now: datetime,
) -> MonitorRun:
    run = await _claimed_run(db, org_id, claim, now)
    if run.status in TERMINAL_STATUSES:
        return run
    payload = plan.payload()
    expected = (
        payload["planHash"],
        payload["plannerVersion"],
        definition_hash,
        payload["relation"]["schemaFingerprint"],
    )
    persisted = (run.plan_hash, run.planner_version, run.definition_hash, run.schema_fingerprint)
    if persisted != expected:
        raise MonitorRunError("plan_context_mismatch", SAFE_ERROR_MESSAGES["plan_context_mismatch"])
    state = await db.scalar(
        select(MonitorEvaluationState)
        .where(MonitorEvaluationState.monitor_id == run.monitor_id, MonitorEvaluationState.org_id == org_id)
        .with_for_update()
    )
    if state is None or state.revision_id != run.revision_id:
        raise MonitorRunError("policy_state_missing", "Policy state does not match the run revision")
    breached = evaluate_breach(Predicate.model_validate(plan.breach_when), measurements)
    decision = evaluate_policy(
        breached=breached,
        policy=Policy.model_validate(plan.policy),
        previous=PolicyState(
            phase=state.phase,
            breach_streak=state.breach_streak,
            recovery_streak=state.recovery_streak,
            cooldown_until=state.cooldown_until,
        ),
        evaluated_at=now,
    )
    run.status = decision.run_status
    run.measurements = measurements
    run.result = decision.payload()
    run.completed_at = now
    run.claim_token = None
    run.lease_expires_at = None
    state.phase = decision.phase
    state.breach_streak = decision.breach_streak
    state.recovery_streak = decision.recovery_streak
    state.cooldown_until = decision.cooldown_until
    state.last_run_id = run.id
    state.last_sequence_at = run.sequence_at
    state.last_idempotency_key = run.idempotency_key
    state.version += 1
    await db.flush()
    return run


async def finalize_error(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    claim: RunClaim,
    error_code: str,
    now: datetime,
) -> MonitorRun:
    if now.tzinfo is None:
        raise MonitorRunError("finalization_time_invalid", "Finalization time must be timezone-aware")
    if error_code not in SAFE_ERROR_MESSAGES:
        raise MonitorRunError("error_code_invalid", "Execution error code is not allowlisted")
    run = await _claimed_run(db, org_id, claim, now)
    if run.status in TERMINAL_STATUSES:
        return run
    state = await db.scalar(
        select(MonitorEvaluationState)
        .where(MonitorEvaluationState.monitor_id == run.monitor_id, MonitorEvaluationState.org_id == org_id)
        .with_for_update()
    )
    if state is None or state.revision_id != run.revision_id:
        raise MonitorRunError("policy_state_missing", "Policy state does not match the run revision")
    revision = await db.scalar(
        select(MonitorRevision).where(
            MonitorRevision.id == run.revision_id,
            MonitorRevision.monitor_id == run.monitor_id,
        )
    )
    if revision is None:
        raise MonitorRunError("run_context_invalid", "Run revision no longer exists")
    policy = load_persisted_definition(revision.definition).spec.policy
    run.status = "error"
    run.error_code = error_code
    run.error = SAFE_ERROR_MESSAGES[error_code]
    run.result = {
        "version": "monitor-evaluation/v1",
        "transition": "execution_error",
        "notificationEligible": policy.notify_on_execution_error,
    }
    run.completed_at = now
    run.claim_token = None
    run.lease_expires_at = None
    state.breach_streak = 0
    state.recovery_streak = 0
    state.last_run_id = run.id
    state.last_sequence_at = run.sequence_at
    state.last_idempotency_key = run.idempotency_key
    state.version += 1
    await db.flush()
    return run
