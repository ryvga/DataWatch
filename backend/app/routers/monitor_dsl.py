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
from app.services.monitor_dsl import MonitorDefinition, definition_hash, predicate_stats

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


async def _resolve_target(
    asset_id: UUID, org_id, db: AsyncSession
) -> tuple[MonitoredTable, DataSource]:
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


def _capability_plan(definition: MonitorDefinition, source: DataSource) -> dict:
    capabilities = ConnectorFactory.capabilities_for(source.type)
    requirements = sorted({measurement.type for measurement in definition.spec.measurements})
    unsupported = []
    if capabilities["profiling"] == "none":
        unsupported.append("connector_has_no_profile_runtime")
    unsupported.append("dsl_compiler_not_integrated")
    return {
        "sourceType": source.type,
        "requirements": requirements,
        "compatible": not unsupported,
        "unsupported": unsupported,
        "activationSupported": False,
    }


def _validation_payload(definition: MonitorDefinition, source: DataSource) -> dict:
    return {
        "valid": True,
        "apiVersion": definition.api_version,
        "definitionHash": definition_hash(definition),
        "canonicalDefinition": definition.model_dump(mode="json", by_alias=True),
        "stats": {
            "measurements": len(definition.spec.measurements),
            **predicate_stats(definition),
        },
        "capabilityPlan": _capability_plan(definition, source),
    }


def _monitor_payload(monitor: Monitor, revision: MonitorRevision) -> dict:
    return {
        "id": str(monitor.id),
        "assetId": str(monitor.table_id),
        "name": monitor.name,
        "mode": monitor.mode,
        "status": monitor.status,
        "currentRevision": monitor.current_revision,
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
        "status": run.status,
        "measurements": run.measurements,
        "result": run.result,
        "error": run.error,
        "startedAt": run.started_at,
        "completedAt": run.completed_at,
    }


async def _get_monitor(monitor_id: UUID, org_id, db: AsyncSession) -> Monitor:
    monitor = await db.scalar(
        select(Monitor).where(Monitor.id == monitor_id, Monitor.org_id == org_id)
    )
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
    _, source = await _resolve_target(definition.spec.target.asset_id, org.id, db)
    return _validation_payload(definition, source)


@router.post("/preview")
async def preview_monitor_definition(
    definition: MonitorDefinition,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    table, source = await _resolve_target(definition.spec.target.asset_id, org.id, db)
    schema_fingerprint = await _latest_schema_fingerprint(table.id, db)
    digest = definition_hash(definition)
    token, claims = create_preview_attestation(
        org_id=str(org.id),
        asset_id=str(table.id),
        definition_hash=digest,
        schema_fingerprint=schema_fingerprint,
    )
    return {
        **_validation_payload(definition, source),
        "preview": {
            "status": "validation_only",
            "attestation": token,
            "issuedAt": claims.issued_at,
            "expiresAt": claims.expires_at,
            "plannerVersion": claims.planner_version,
            "schemaFingerprint": schema_fingerprint,
        },
    }


@asset_router.post("/{asset_id}/monitors", status_code=201)
async def create_monitor_draft(
    asset_id: UUID,
    definition: MonitorDefinition,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    if definition.spec.target.asset_id != asset_id:
        raise HTTPException(status_code=422, detail="Definition target does not match asset path")
    table, _ = await _resolve_target(asset_id, org.id, db)
    duplicate = await db.scalar(
        select(Monitor.id).where(
            Monitor.org_id == org.id,
            Monitor.table_id == table.id,
            Monitor.name == definition.metadata.name,
        )
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="A monitor with this name already exists")

    schema_fingerprint = await _latest_schema_fingerprint(table.id, db)
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
        definition=definition.model_dump(mode="json", by_alias=True),
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
                (MonitorRevision.monitor_id == Monitor.id)
                & (MonitorRevision.revision == Monitor.current_revision),
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


@router.put("/{monitor_id}")
async def create_monitor_revision(
    monitor_id: UUID,
    body: RevisionRequest,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    monitor = await _get_monitor(monitor_id, org.id, db)
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

    schema_fingerprint = await _latest_schema_fingerprint(monitor.table_id, db)
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
        definition=body.definition.model_dump(mode="json", by_alias=True),
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
    schema_fingerprint = await _latest_schema_fingerprint(monitor.table_id, db)
    try:
        verify_preview_attestation(
            body.preview_attestation,
            org_id=str(org.id),
            asset_id=str(monitor.table_id),
            definition_hash=revision.definition_hash,
            schema_fingerprint=schema_fingerprint,
        )
    except AttestationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise HTTPException(
        status_code=409,
        detail={
            "error": "activation_not_supported",
            "reason": "dsl_execution_runtime_not_implemented",
        },
    )
