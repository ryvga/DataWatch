"""Versioned, validation-only API for the safe monitor DSL."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.factory import ConnectorFactory
from app.database import get_db
from app.models.data_source import DataSource
from app.models.monitor import Monitor, MonitorRevision, MonitorRun
from app.models.monitored_table import MonitoredTable
from app.models.organization import Organization
from app.models.table_profile import TableProfile
from app.routers.auth import get_current_org_from_jwt
from app.services.monitor_attestation import (
    AttestationError,
    create_preview_attestation,
    verify_preview_attestation,
)
from app.services.monitor_compiler import PLANNER_VERSION
from app.services.monitor_dsl import (
    MonitorDefinition,
    definition_hash,
    load_persisted_definition,
    persisted_definition_payload,
    predicate_stats,
)
from app.services.monitor_run_service import MonitorRunError, RunRequest, reserve_run
from app.services.monitor_planning import analyze_monitor_support
from app.services.schema_binding import SchemaBindingError, build_relation_binding

router = APIRouter(prefix="/api/v2/monitors", tags=["monitor_dsl"])
asset_router = APIRouter(prefix="/api/v2/assets", tags=["monitor_dsl"])


class RevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(alias="expectedRevision", ge=1)
    definition: MonitorDefinition


class ActivationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(alias="expectedRevision", ge=1)
    preview_attestation: str = Field(alias="previewAttestation", min_length=20, max_length=4096)


class ManualRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_idempotency_key: str = Field(alias="clientIdempotencyKey", min_length=1, max_length=512)


async def _resolve_target(asset_id: UUID, org_id, db: AsyncSession) -> tuple[MonitoredTable, DataSource]:
    row = (
        await db.execute(
            select(MonitoredTable, DataSource)
            .join(DataSource, DataSource.id == MonitoredTable.source_id)
            .where(MonitoredTable.id == asset_id, DataSource.org_id == org_id)
        )
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Target asset not found")
    return row[0], row[1]


async def _latest_schema_fingerprint(table_id, db: AsyncSession) -> str | None:
    return await db.scalar(
        select(TableProfile.schema_fingerprint)
        .where(TableProfile.table_id == table_id, TableProfile.error.is_(None))
        .order_by(TableProfile.collected_at.desc())
        .limit(1)
    )


def _planning_result(
    definition: MonitorDefinition,
    source: DataSource,
    table: MonitoredTable,
    schema_fingerprint: str | None,
) -> tuple[dict, dict | None, str | None]:
    capabilities = ConnectorFactory.capabilities_for(source.type)
    requirements = sorted({measurement.type for measurement in definition.spec.measurements})
    issues = []
    plan = None
    binding_fingerprint = schema_fingerprint
    try:
        relation = build_relation_binding(
            asset_id=table.id,
            source_type=source.type,
            schema_name=table.schema_name,
            table_name=table.table_name,
            ddl=table.dbt_model_yaml,
            latest_schema_fingerprint=schema_fingerprint,
        )
    except SchemaBindingError as exc:
        compilation = {
            "compilationSupported": False,
            "plannerVersion": PLANNER_VERSION,
            "issues": [{"code": exc.code, "path": "schema", "message": str(exc)}],
        }
    else:
        binding_fingerprint = relation.schema_fingerprint
        compilation, compiled = analyze_monitor_support(definition, relation=relation)
        plan = compiled.payload() if compiled else None

    issues.extend(compilation["issues"])
    if capabilities["profiling"] == "none":
        issues.append(
            {
                "code": "connector_has_no_profile_runtime",
                "path": "source.type",
                "message": f"{source.type} has no scheduled profile runtime",
            }
        )
    unsupported = [issue["code"] for issue in issues]
    compiled_runtime_supported = compilation["compilationSupported"] and capabilities.get("compiled_monitors") in {
        "internal_read_only",
        "internal_document_read_only",
    }
    activation_issues = list(issues)
    if definition.spec.trigger.type == "interval":
        activation_issues.append(
            {
                "code": "interval_trigger_not_supported",
                "path": "spec.trigger",
                "message": "Interval triggers require a scheduler-backed monitor cadence",
            }
        )
    if compilation["compilationSupported"] and not compiled_runtime_supported:
        activation_issues.append(
            {
                "code": "connector_compiled_runtime_not_supported",
                "path": "source.type",
                "message": f"{source.type} has no safe compiled monitor runtime",
            }
        )
    payload = {
        "sourceType": source.type,
        "requirements": requirements,
        "compilationSupported": compilation["compilationSupported"],
        "plannerVersion": compilation["plannerVersion"],
        "compatible": compilation["compilationSupported"] and not unsupported,
        "unsupported": unsupported,
        "issues": issues,
        "activationSupported": compiled_runtime_supported and not activation_issues,
        "activationBlockers": [issue["code"] for issue in activation_issues],
    }
    return payload, plan, binding_fingerprint


def _binding_fingerprint(
    table: MonitoredTable,
    source: DataSource,
    latest_schema_fingerprint: str | None,
) -> str | None:
    try:
        relation = build_relation_binding(
            asset_id=table.id,
            source_type=source.type,
            schema_name=table.schema_name,
            table_name=table.table_name,
            ddl=table.dbt_model_yaml,
            latest_schema_fingerprint=latest_schema_fingerprint,
        )
    except SchemaBindingError:
        return latest_schema_fingerprint
    return relation.schema_fingerprint


def _validation_payload(
    definition: MonitorDefinition,
    source: DataSource,
    table: MonitoredTable,
    schema_fingerprint: str | None,
    *,
    include_plan: bool = False,
) -> tuple[dict, str | None]:
    capability_plan, compiled_plan, binding_fingerprint = _planning_result(
        definition,
        source,
        table,
        schema_fingerprint,
    )
    payload = {
        "valid": True,
        "apiVersion": definition.api_version,
        "definitionHash": definition_hash(definition),
        "canonicalDefinition": persisted_definition_payload(definition),
        "stats": {
            "measurements": len(definition.spec.measurements),
            **predicate_stats(definition),
        },
        "capabilityPlan": capability_plan,
    }
    if include_plan and compiled_plan:
        payload["compiledPlan"] = compiled_plan
    return payload, binding_fingerprint


def _monitor_payload(monitor: Monitor, revision: MonitorRevision) -> dict:
    return {
        "id": str(monitor.id),
        "assetId": str(monitor.table_id),
        "name": monitor.name,
        "mode": monitor.mode,
        "status": monitor.status,
        "currentRevision": monitor.current_revision,
        "activeRevisionId": (str(monitor.active_revision_id) if monitor.active_revision_id else None),
        "definitionVersion": revision.definition_version,
        "definitionHash": revision.definition_hash,
        "definition": revision.definition,
        "schemaFingerprint": revision.schema_fingerprint,
        "createdAt": monitor.created_at,
        "updatedAt": monitor.updated_at,
        "activatedAt": monitor.activated_at,
    }


def _revision_payload(revision: MonitorRevision) -> dict:
    return {
        "id": str(revision.id),
        "monitorId": str(revision.monitor_id),
        "revision": revision.revision,
        "definitionVersion": revision.definition_version,
        "definitionHash": revision.definition_hash,
        "definition": revision.definition,
        "validationStatus": revision.validation_status,
        "schemaFingerprint": revision.schema_fingerprint,
        "createdAt": revision.created_at,
    }


def _run_payload(run: MonitorRun) -> dict:
    return {
        "id": str(run.id),
        "monitorId": str(run.monitor_id),
        "revisionId": str(run.revision_id),
        "assetId": str(run.table_id),
        "idempotencyKey": run.idempotency_key,
        "triggerType": run.trigger_type,
        "profileId": str(run.profile_id) if run.profile_id else None,
        "sequenceAt": run.sequence_at,
        "queuedAt": run.queued_at,
        "planHash": run.plan_hash,
        "plannerVersion": run.planner_version,
        "definitionHash": run.definition_hash,
        "schemaFingerprint": run.schema_fingerprint,
        "status": run.status,
        "attempt": run.attempt,
        "measurements": run.measurements,
        "result": run.result,
        "error": run.error,
        "errorCode": run.error_code,
        "startedAt": run.started_at,
        "completedAt": run.completed_at,
    }


async def _get_monitor(monitor_id: UUID, org_id, db: AsyncSession) -> Monitor:
    monitor = await db.scalar(select(Monitor).where(Monitor.id == monitor_id, Monitor.org_id == org_id))
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")
    return monitor


async def _current_revision(monitor: Monitor, db: AsyncSession) -> MonitorRevision:
    revision = await db.scalar(
        select(MonitorRevision).where(
            MonitorRevision.monitor_id == monitor.id,
            MonitorRevision.revision == monitor.current_revision,
        )
    )
    if not revision:
        raise HTTPException(status_code=500, detail="Monitor revision state is inconsistent")
    return revision


@router.post("/validate")
async def validate_monitor_definition(
    definition: MonitorDefinition,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    table, source = await _resolve_target(definition.spec.target.asset_id, org.id, db)
    schema_fingerprint = await _latest_schema_fingerprint(table.id, db)
    payload, _ = _validation_payload(definition, source, table, schema_fingerprint)
    return payload


@router.post("/preview")
async def preview_monitor_definition(
    definition: MonitorDefinition,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    table, source = await _resolve_target(definition.spec.target.asset_id, org.id, db)
    schema_fingerprint = await _latest_schema_fingerprint(table.id, db)
    validation, binding_fingerprint = _validation_payload(
        definition,
        source,
        table,
        schema_fingerprint,
        include_plan=True,
    )
    preview = {
        "status": "validation_only",
        "plannerVersion": validation["capabilityPlan"]["plannerVersion"],
        "schemaFingerprint": binding_fingerprint,
    }
    if "compiledPlan" in validation:
        digest = definition_hash(definition)
        token, claims = create_preview_attestation(
            org_id=str(org.id),
            asset_id=str(table.id),
            definition_hash=digest,
            schema_fingerprint=binding_fingerprint,
            planner_version=validation["capabilityPlan"]["plannerVersion"],
        )
        preview.update(
            {
                "status": "compiled_validation_only",
                "attestation": token,
                "issuedAt": claims.issued_at,
                "expiresAt": claims.expires_at,
                "plannerVersion": claims.planner_version,
            }
        )
    return {**validation, "preview": preview}


@asset_router.post("/{asset_id}/monitors", status_code=201)
async def create_monitor_draft(
    asset_id: UUID,
    definition: MonitorDefinition,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    if definition.spec.target.asset_id != asset_id:
        raise HTTPException(status_code=422, detail="Definition target does not match asset path")
    table, source = await _resolve_target(asset_id, org.id, db)
    duplicate = await db.scalar(
        select(Monitor.id).where(
            Monitor.org_id == org.id,
            Monitor.table_id == table.id,
            Monitor.name == definition.metadata.name,
        )
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="A monitor with this name already exists")

    latest_schema_fingerprint = await _latest_schema_fingerprint(table.id, db)
    schema_fingerprint = _binding_fingerprint(
        table,
        source,
        latest_schema_fingerprint,
    )
    digest = definition_hash(definition)
    monitor = Monitor(
        org_id=org.id,
        table_id=table.id,
        name=definition.metadata.name,
        mode="dsl",
        status="draft",
        current_revision=1,
    )
    db.add(monitor)
    await db.flush()
    revision = MonitorRevision(
        monitor_id=monitor.id,
        revision=1,
        definition_version=definition.api_version,
        definition_hash=digest,
        definition=persisted_definition_payload(definition),
        validation_status="valid",
        schema_fingerprint=schema_fingerprint,
    )
    db.add(revision)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Monitor draft conflicts with existing state") from exc
    await db.refresh(monitor)
    await db.refresh(revision)
    return _monitor_payload(monitor, revision)


@asset_router.get("/{asset_id}/monitors")
async def list_monitor_drafts(
    asset_id: UUID,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    await _resolve_target(asset_id, org.id, db)
    rows = (
        await db.execute(
            select(Monitor, MonitorRevision)
            .join(
                MonitorRevision,
                (MonitorRevision.monitor_id == Monitor.id) & (MonitorRevision.revision == Monitor.current_revision),
            )
            .where(Monitor.org_id == org.id, Monitor.table_id == asset_id)
            .order_by(Monitor.created_at.desc())
        )
    ).all()
    return [_monitor_payload(monitor, revision) for monitor, revision in rows]


@router.get("/{monitor_id}")
async def get_monitor_draft(
    monitor_id: UUID,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    monitor = await _get_monitor(monitor_id, org.id, db)
    return _monitor_payload(monitor, await _current_revision(monitor, db))


@router.get("/{monitor_id}/revisions")
async def list_monitor_revisions(
    monitor_id: UUID,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    monitor = await _get_monitor(monitor_id, org.id, db)
    revisions = (
        await db.scalars(
            select(MonitorRevision)
            .where(MonitorRevision.monitor_id == monitor.id)
            .order_by(MonitorRevision.revision.desc())
        )
    ).all()
    return [_revision_payload(revision) for revision in revisions]


@router.get("/{monitor_id}/revisions/{revision_number}")
async def get_monitor_revision(
    monitor_id: UUID,
    revision_number: int,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    monitor = await _get_monitor(monitor_id, org.id, db)
    revision = await db.scalar(
        select(MonitorRevision).where(
            MonitorRevision.monitor_id == monitor.id,
            MonitorRevision.revision == revision_number,
        )
    )
    if not revision:
        raise HTTPException(status_code=404, detail="Monitor revision not found")
    return _revision_payload(revision)


@router.get("/{monitor_id}/runs")
async def list_monitor_runs(
    monitor_id: UUID,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    monitor = await _get_monitor(monitor_id, org.id, db)
    runs = (
        await db.scalars(
            select(MonitorRun)
            .where(MonitorRun.monitor_id == monitor.id, MonitorRun.org_id == org.id)
            .order_by(MonitorRun.started_at.desc())
            .limit(250)
        )
    ).all()
    return [_run_payload(run) for run in runs]


@router.post("/{monitor_id}/run", status_code=202)
async def run_monitor_now(
    monitor_id: UUID,
    body: ManualRunRequest,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    """Queue one idempotent manual run of the active revision."""
    monitor = await _get_monitor(monitor_id, org.id, db)
    if monitor.status != "active" or monitor.active_revision_id is None:
        raise HTTPException(status_code=409, detail="Monitor is not active")
    revision = await db.get(MonitorRevision, monitor.active_revision_id)
    if revision is None:
        raise HTTPException(status_code=500, detail="Monitor active revision is inconsistent")
    try:
        reservation = await reserve_run(
            db,
            RunRequest(
                org_id=org.id,
                monitor_id=monitor.id,
                revision_id=revision.id,
                trigger_type="manual",
                profile_id=None,
                client_idempotency_key=body.client_idempotency_key,
            ),
            now=datetime.now(UTC),
        )
    except MonitorRunError as exc:
        status = 422 if exc.code in {"idempotency_key_invalid", "run_context_invalid"} else 409
        raise HTTPException(status_code=status, detail={"error": exc.code, "message": str(exc)}) from exc
    await db.commit()
    from app.tasks import run_dsl_monitor

    task = run_dsl_monitor.delay(str(monitor.id), body.client_idempotency_key)
    run = await db.get(MonitorRun, reservation.run_id)
    return {
        "queued": reservation.status in {"queued", "running"},
        "acquired": reservation.acquired,
        "taskId": task.id,
        "run": _run_payload(run),
    }


@router.put("/{monitor_id}")
async def create_monitor_revision(
    monitor_id: UUID,
    body: RevisionRequest,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    monitor = await _get_monitor(monitor_id, org.id, db)
    table, source = await _resolve_target(monitor.table_id, org.id, db)
    if body.definition.spec.target.asset_id != monitor.table_id:
        raise HTTPException(status_code=422, detail="Monitor target is immutable")
    if body.expected_revision != monitor.current_revision:
        raise HTTPException(
            status_code=409,
            detail={"error": "revision_conflict", "currentRevision": monitor.current_revision},
        )
    current = await _current_revision(monitor, db)
    digest = definition_hash(body.definition)
    if digest == current.definition_hash:
        raise HTTPException(status_code=409, detail="Definition is unchanged")

    latest_schema_fingerprint = await _latest_schema_fingerprint(monitor.table_id, db)
    schema_fingerprint = _binding_fingerprint(
        table,
        source,
        latest_schema_fingerprint,
    )
    next_revision = monitor.current_revision + 1
    result = await db.execute(
        update(Monitor)
        .where(
            Monitor.id == monitor.id,
            Monitor.org_id == org.id,
            Monitor.current_revision == body.expected_revision,
        )
        .values(
            name=body.definition.metadata.name,
            current_revision=next_revision,
            updated_at=datetime.now(UTC),
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Monitor was revised concurrently")
    revision = MonitorRevision(
        monitor_id=monitor.id,
        revision=next_revision,
        definition_version=body.definition.api_version,
        definition_hash=digest,
        definition=persisted_definition_payload(body.definition),
        validation_status="valid",
        schema_fingerprint=schema_fingerprint,
    )
    db.add(revision)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Monitor revision conflicts with existing state") from exc
    await db.refresh(monitor)
    await db.refresh(revision)
    return _monitor_payload(monitor, revision)


@router.post("/{monitor_id}/activate")
async def activate_monitor(
    monitor_id: UUID,
    body: ActivationRequest,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    monitor = await _get_monitor(monitor_id, org.id, db)
    if body.expected_revision != monitor.current_revision:
        raise HTTPException(status_code=409, detail="Monitor revision changed after preview")
    revision = await _current_revision(monitor, db)
    table, source = await _resolve_target(monitor.table_id, org.id, db)
    latest_schema_fingerprint = await _latest_schema_fingerprint(monitor.table_id, db)
    schema_fingerprint = _binding_fingerprint(
        table,
        source,
        latest_schema_fingerprint,
    )
    definition = load_persisted_definition(revision.definition)
    capability_plan, compiled_plan, _ = _planning_result(definition, source, table, latest_schema_fingerprint)
    try:
        verify_preview_attestation(
            body.preview_attestation,
            org_id=str(org.id),
            asset_id=str(monitor.table_id),
            definition_hash=revision.definition_hash,
            schema_fingerprint=schema_fingerprint,
            planner_version=capability_plan["plannerVersion"],
        )
    except AttestationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not capability_plan["activationSupported"] or compiled_plan is None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "activation_not_supported",
                "reasons": capability_plan["activationBlockers"],
            },
        )

    now = datetime.now(UTC)
    monitor.active_revision_id = revision.id
    monitor.status = "active"
    monitor.activated_at = now
    monitor.updated_at = now
    await db.commit()
    await db.refresh(monitor)
    return {
        **_monitor_payload(monitor, revision),
        "activation": {
            "status": "active",
            "trigger": "on_profile",
            "schedule": "existing_table_profile_cadence",
            "plannerVersion": capability_plan["plannerVersion"],
        },
    }
