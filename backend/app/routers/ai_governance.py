"""Tenant-scoped observe-only AI governance API."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import desc, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.factory import ConnectorFactory
from app.database import get_db
from app.models.ai_governance import (
    AIControlEvaluation,
    AIApproval,
    AIDataUseRevision,
    AIDeployment,
    AIGovernanceIncident,
    AIReleaseManifest,
    AISystem,
    AISystemVersion,
)
from app.models.data_source import DataSource
from app.models.monitored_table import MonitoredTable
from app.models.table_profile import TableProfile
from app.models.team import Team
from app.models.user import User
from app.routers.auth import get_current_user_from_jwt
from app.services.ai_governance import (
    EVALUATOR_VERSION,
    build_data_use_definition,
    build_release_manifest,
    build_version_definition,
    canonical_hash,
    evaluate_ownership,
    evaluate_privileges,
    evaluate_schema_freshness,
    evaluate_vector_consistency,
    reject_sensitive_payload,
)
from app.services.crypto import decrypt_config
from app.services.schema_binding import parse_ddl_columns, schema_fingerprint

router = APIRouter(prefix="/api/v1/ai", tags=["ai-governance"])
CurrentUser = tuple[User, object]


def _reject_payload(value: dict) -> None:
    try:
        reject_sensitive_payload(value)
    except Exception as exc:
        code = getattr(exc, "code", "invalid_governance_payload")
        raise HTTPException(status_code=422, detail={"code": code, "message": str(exc)}) from exc


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not normalized or len(normalized) > 100:
        raise ValueError("Slug must contain 1-100 lowercase letters, numbers, or hyphens")
    return normalized


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SystemCreate(StrictModel):
    name: str = Field(min_length=2, max_length=255)
    slug: str = Field(min_length=1, max_length=100)
    lifecycle_status: Literal["draft", "development", "production", "paused", "retired"] = "draft"
    intended_purpose: str = Field(min_length=8, max_length=5000)
    prohibited_uses: list[str] = Field(default_factory=list, max_length=50)
    affected_population: str | None = Field(default=None, max_length=5000)
    autonomy_level: Literal["assistive", "human_reviewed", "semi_autonomous", "autonomous"] = "assistive"
    human_oversight: str = Field(min_length=8, max_length=5000)
    business_owner_id: UUID | None = None
    technical_owner_id: UUID | None = None
    risk_owner_id: UUID | None = None
    team_id: UUID | None = None
    risk_context: dict = Field(default_factory=dict)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        if value != _slug(value):
            raise ValueError("Slug must already be normalized")
        return value


class SystemPatch(StrictModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    lifecycle_status: Literal["draft", "development", "production", "paused", "retired"] | None = None
    intended_purpose: str | None = Field(default=None, min_length=8, max_length=5000)
    prohibited_uses: list[str] | None = Field(default=None, max_length=50)
    affected_population: str | None = Field(default=None, max_length=5000)
    autonomy_level: Literal["assistive", "human_reviewed", "semi_autonomous", "autonomous"] | None = None
    human_oversight: str | None = Field(default=None, min_length=8, max_length=5000)
    business_owner_id: UUID | None = None
    technical_owner_id: UUID | None = None
    risk_owner_id: UUID | None = None
    team_id: UUID | None = None
    risk_context: dict | None = None


class VersionCreate(StrictModel):
    provider: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=200)
    artifact_hash: str | None = Field(default=None, max_length=128)
    prompt_config_hash: str | None = Field(default=None, max_length=128)
    evaluation_suite_hash: str | None = Field(default=None, max_length=128)
    capabilities: list[str] = Field(default_factory=list, max_length=100)
    limitations: list[str] = Field(default_factory=list, max_length=100)
    fallback: str | None = Field(default=None, max_length=5000)
    human_oversight_procedure: str | None = Field(default=None, max_length=5000)
    risk_snapshot: dict = Field(default_factory=dict)
    change_rationale: str = Field(min_length=4, max_length=5000)


class VectorContract(StrictModel):
    vector_table_id: UUID
    embedding_field: str = Field(min_length=1, max_length=255)
    source_key: str = Field(min_length=1, max_length=255)
    vector_source_key: str = Field(min_length=1, max_length=255)
    source_updated_at: str | None = Field(default=None, max_length=255)
    vector_updated_at: str | None = Field(default=None, max_length=255)
    source_deleted_at: str | None = Field(default=None, max_length=255)
    maximum_freshness_seconds: int = Field(default=86400, ge=60, le=31_536_000)


class DataUseCreate(StrictModel):
    table_id: UUID
    use_kind: Literal["training", "fine_tuning", "validation", "rag", "inference", "feedback", "telemetry"]
    fields: list[str] = Field(min_length=1, max_length=250)
    purpose: str = Field(min_length=4, max_length=5000)
    necessity: str = Field(min_length=4, max_length=5000)
    steward: str = Field(min_length=2, max_length=255)
    sensitivity_ceiling: Literal["public", "internal", "confidential", "restricted"]
    retention_days: int | None = Field(default=None, ge=1, le=36500)
    residency: list[str] = Field(default_factory=list, max_length=50)
    allowed_transformations: list[str] = Field(default_factory=list, max_length=100)
    expected_db_roles: list[str] = Field(default_factory=list, max_length=100)
    vector_contract: VectorContract | None = None
    change_rationale: str = Field(min_length=4, max_length=5000)


class ManifestCreate(StrictModel):
    data_use_revision_ids: list[UUID] = Field(min_length=1, max_length=250)
    evidence_cutoff: datetime | None = None


class DeploymentCreate(StrictModel):
    environment: Literal["development", "staging", "production"]
    region: str = Field(default="global", min_length=1, max_length=64)
    workload_identity_hash: str | None = Field(default=None, max_length=128)


class ActivateManifest(StrictModel):
    manifest_id: UUID
    manifest_hash: str = Field(min_length=64, max_length=64)
    expected_generation: int = Field(ge=0)
    expected_active_manifest_hash: str | None = Field(default=None, max_length=64)


class EvaluationRequest(StrictModel):
    client_idempotency_key: str = Field(min_length=8, max_length=80)
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    max_bytes_scanned: int = Field(default=100_000_000, ge=1_000_000, le=10_000_000_000)


class ReviewCreate(StrictModel):
    reviewer_role: str = Field(min_length=2, max_length=64)
    decision: Literal["noted", "approved", "rejected", "changes_requested"]
    rationale: str = Field(min_length=8, max_length=5000)


def _system_payload(system: AISystem, *, open_failures: int = 0) -> dict:
    return {
        "id": str(system.id),
        "slug": system.slug,
        "name": system.name,
        "lifecycleStatus": system.lifecycle_status,
        "intendedPurpose": system.intended_purpose,
        "prohibitedUses": system.prohibited_uses,
        "affectedPopulation": system.affected_population,
        "autonomyLevel": system.autonomy_level,
        "humanOversight": system.human_oversight,
        "businessOwnerId": str(system.business_owner_id) if system.business_owner_id else None,
        "technicalOwnerId": str(system.technical_owner_id) if system.technical_owner_id else None,
        "riskOwnerId": str(system.risk_owner_id) if system.risk_owner_id else None,
        "teamId": str(system.team_id) if system.team_id else None,
        "riskContext": system.risk_context,
        "currentVersionId": str(system.current_version_id) if system.current_version_id else None,
        "openFailures": open_failures,
        "governanceMode": "observe",
        "createdAt": system.created_at,
        "updatedAt": system.updated_at,
    }


async def _system_or_404(system_id: UUID, org_id: UUID, db: AsyncSession, *, lock: bool = False) -> AISystem:
    query = select(AISystem).where(AISystem.id == system_id, AISystem.org_id == org_id)
    if lock:
        query = query.with_for_update()
    system = await db.scalar(query)
    if not system:
        raise HTTPException(status_code=404, detail="AI system not found")
    return system


async def _validate_owner_ids(body, org_id: UUID, db: AsyncSession) -> None:
    for field in ("business_owner_id", "technical_owner_id", "risk_owner_id"):
        owner_id = getattr(body, field, None)
        if owner_id and not await db.scalar(select(User.id).where(User.id == owner_id, User.org_id == org_id)):
            raise HTTPException(status_code=422, detail=f"{field} must reference a workspace member")
    team_id = getattr(body, "team_id", None)
    if team_id and not await db.scalar(select(Team.id).where(Team.id == team_id, Team.org_id == org_id)):
        raise HTTPException(status_code=422, detail="team_id must reference a workspace team")


@router.get("/systems")
async def list_systems(
    current: CurrentUser = Depends(get_current_user_from_jwt), db: AsyncSession = Depends(get_db)
):
    _user, org = current
    systems = (await db.scalars(select(AISystem).where(AISystem.org_id == org.id).order_by(AISystem.name))).all()
    payload = []
    for item in systems:
        failures = await db.scalar(select(func.count()).select_from(AIGovernanceIncident).where(AIGovernanceIncident.system_id == item.id, AIGovernanceIncident.status.in_(["open", "acknowledged"])))
        payload.append(_system_payload(item, open_failures=int(failures or 0)))
    return payload


@router.post("/systems", status_code=201)
async def create_system(
    body: SystemCreate,
    current: CurrentUser = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    user, org = current
    _reject_payload(body.model_dump(mode="json"))
    await _validate_owner_ids(body, org.id, db)
    system = AISystem(org_id=org.id, created_by=user.id, **body.model_dump())
    db.add(system)
    await db.commit()
    await db.refresh(system)
    return _system_payload(system)


@router.get("/systems/{system_id}")
async def get_system(
    system_id: UUID,
    current: CurrentUser = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    _user, org = current
    system = await _system_or_404(system_id, org.id, db)
    versions = (await db.scalars(select(AISystemVersion).where(AISystemVersion.system_id == system.id).order_by(desc(AISystemVersion.version_number)))).all()
    deployments = (await db.scalars(select(AIDeployment).where(AIDeployment.system_id == system.id).order_by(AIDeployment.environment))).all()
    data_uses = (await db.scalars(select(AIDataUseRevision).where(AIDataUseRevision.system_id == system.id).order_by(AIDataUseRevision.created_at))).all()
    evaluations = (await db.scalars(select(AIControlEvaluation).where(AIControlEvaluation.system_id == system.id).order_by(desc(AIControlEvaluation.created_at)).limit(100))).all()
    approvals = (await db.scalars(select(AIApproval).where(AIApproval.system_id == system.id).order_by(desc(AIApproval.created_at)).limit(100))).all()
    incidents = (await db.scalars(select(AIGovernanceIncident).where(AIGovernanceIncident.system_id == system.id).order_by(desc(AIGovernanceIncident.created_at)))).all()
    payload = _system_payload(system, open_failures=sum(item.status != "resolved" for item in incidents))
    timeline = [
        {"id": str(e.id), "kind": "control_evaluation", "controlId": e.control_id, "status": e.status, "evidenceClass": e.evidence_class, "reasonCode": e.reason_code, "observed": e.observed, "expected": e.expected, "inputHash": e.input_hash, "createdAt": e.created_at}
        for e in evaluations
    ] + [
        {"id": str(a.id), "kind": "review", "controlId": "release-review", "status": a.decision, "evidenceClass": a.evidence_class, "reasonCode": "reviewer_attestation_recorded", "observed": {"reviewerRole": a.reviewer_role, "rationale": a.rationale}, "expected": {}, "inputHash": a.evidence_snapshot_hash, "createdAt": a.created_at}
        for a in approvals
    ]
    timeline.sort(key=lambda item: item["createdAt"], reverse=True)
    payload.update({
        "versions": [{"id": str(v.id), "versionNumber": v.version_number, "definitionHash": v.definition_hash, "definition": v.definition, "changeRationale": v.change_rationale, "createdAt": v.created_at} for v in versions],
        "deployments": [{"id": str(d.id), "environment": d.environment, "region": d.region, "status": d.status, "activeManifestId": str(d.active_manifest_id) if d.active_manifest_id else None, "activeManifestHash": d.active_manifest_hash, "activationGeneration": d.activation_generation} for d in deployments],
        "dataUses": [{"id": str(item.id), "versionId": str(item.version_id), "ordinal": item.ordinal, "definition": item.canonical_definition, "definitionHash": item.definition_hash, "evidenceClass": item.evidence_class, "createdAt": item.created_at} for item in data_uses],
        "evidenceTimeline": timeline,
        "incidents": [{"id": str(i.id), "controlId": i.control_id, "severity": i.severity, "status": i.status, "title": i.title, "createdAt": i.created_at} for i in incidents],
    })
    return payload


@router.patch("/systems/{system_id}")
async def patch_system(
    system_id: UUID,
    body: SystemPatch,
    current: CurrentUser = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    _user, org = current
    _reject_payload(body.model_dump(mode="json", exclude_unset=True))
    await _validate_owner_ids(body, org.id, db)
    system = await _system_or_404(system_id, org.id, db, lock=True)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(system, key, value)
    await db.commit()
    await db.refresh(system)
    return _system_payload(system)


@router.post("/systems/{system_id}/versions", status_code=201)
async def create_version(
    system_id: UUID,
    body: VersionCreate,
    current: CurrentUser = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    user, org = current
    system = await _system_or_404(system_id, org.id, db, lock=True)
    _reject_payload(body.model_dump(mode="json"))
    definition, definition_hash = build_version_definition(body.model_dump())
    latest = await db.scalar(select(AISystemVersion.version_number).where(AISystemVersion.system_id == system.id).order_by(desc(AISystemVersion.version_number)).limit(1))
    version = AISystemVersion(
        org_id=org.id, system_id=system.id, version_number=(latest or 0) + 1,
        definition=definition, definition_hash=definition_hash, provider=body.provider,
        model=body.model, artifact_hash=body.artifact_hash, prompt_config_hash=body.prompt_config_hash,
        evaluation_suite_hash=body.evaluation_suite_hash, change_rationale=body.change_rationale,
        created_by=user.id,
    )
    db.add(version)
    await db.flush()
    system.current_version_id = version.id
    await db.commit()
    return {"id": str(version.id), "versionNumber": version.version_number, "definition": definition, "definitionHash": definition_hash, "evidenceClass": "customer_assertion"}


async def _asset_or_404(table_id: UUID, org_id: UUID, db: AsyncSession) -> tuple[MonitoredTable, DataSource]:
    row = (await db.execute(select(MonitoredTable, DataSource).join(DataSource, DataSource.id == MonitoredTable.source_id).where(MonitoredTable.id == table_id, DataSource.org_id == org_id))).first()
    if not row:
        raise HTTPException(status_code=422, detail="Data-use asset must be a monitored table in this workspace")
    return row[0], row[1]


@router.post("/system-versions/{version_id}/data-use-revisions", status_code=201)
async def create_data_use(
    version_id: UUID,
    body: DataUseCreate,
    current: CurrentUser = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    user, org = current
    version = await db.scalar(select(AISystemVersion).where(AISystemVersion.id == version_id, AISystemVersion.org_id == org.id))
    if not version:
        raise HTTPException(status_code=404, detail="AI system version not found")
    table, source = await _asset_or_404(body.table_id, org.id, db)
    columns = parse_ddl_columns(table.dbt_model_yaml)
    column_names = {column.name for column in columns}
    if not columns:
        raise HTTPException(status_code=422, detail="Verified schema snapshot required before declaring data use")
    unknown = sorted(set(body.fields) - column_names)
    if unknown:
        raise HTTPException(status_code=422, detail={"code": "undeclared_schema_field", "fields": unknown})
    vector_payload = body.vector_contract.model_dump(mode="json") if body.vector_contract else None
    if body.use_kind == "rag" and not vector_payload:
        raise HTTPException(status_code=422, detail="RAG data use requires a vector contract")
    if vector_payload:
        vector_table, vector_source = await _asset_or_404(body.vector_contract.vector_table_id, org.id, db)
        if vector_source.id != source.id:
            raise HTTPException(status_code=422, detail="Phase-one vector table must use the same PostgreSQL source")
        parsed_vector_columns = parse_ddl_columns(vector_table.dbt_model_yaml)
        vector_columns = {column.name for column in parsed_vector_columns}
        required_source = {body.vector_contract.source_key} | {value for value in (body.vector_contract.source_updated_at, body.vector_contract.source_deleted_at) if value}
        required_vector = {body.vector_contract.vector_source_key, body.vector_contract.embedding_field} | {value for value in (body.vector_contract.vector_updated_at,) if value}
        if not required_source <= column_names or not required_vector <= vector_columns:
            raise HTTPException(status_code=422, detail="Vector contract fields must exist in verified schema snapshots")
        embedding_column = next(column for column in parsed_vector_columns if column.name == body.vector_contract.embedding_field)
        if not embedding_column.data_type.lower().startswith("vector"):
            raise HTTPException(status_code=422, detail="embedding_field must use a pgvector vector type")
    fingerprint = schema_fingerprint(columns)
    ordinal = (await db.scalar(select(AIDataUseRevision.ordinal).where(AIDataUseRevision.version_id == version.id).order_by(desc(AIDataUseRevision.ordinal)).limit(1)) or 0) + 1
    raw = body.model_dump(mode="json")
    raw["source_id"] = str(source.id)
    raw["table_id"] = str(table.id)
    raw["vector_contract"] = vector_payload
    _reject_payload(raw)
    definition, definition_hash = build_data_use_definition(raw, schema_fingerprint=fingerprint)
    item = AIDataUseRevision(
        org_id=org.id, system_id=version.system_id, version_id=version.id, source_id=source.id,
        table_id=table.id, ordinal=ordinal, use_kind=body.use_kind, fields=definition["fields"],
        purpose=body.purpose, necessity=body.necessity, steward=body.steward,
        sensitivity_ceiling=body.sensitivity_ceiling, retention_days=body.retention_days,
        residency=body.residency, allowed_transformations=body.allowed_transformations,
        expected_db_roles=body.expected_db_roles, vector_contract=vector_payload,
        schema_fingerprint=fingerprint, canonical_definition=definition, definition_hash=definition_hash,
        evidence_class="customer_assertion", change_rationale=body.change_rationale, created_by=user.id,
    )
    db.add(item)
    await db.commit()
    return {"id": str(item.id), "ordinal": ordinal, "definition": definition, "definitionHash": definition_hash, "evidenceClass": "customer_assertion"}


@router.post("/system-versions/{version_id}/release-manifests", status_code=201)
async def create_manifest(
    version_id: UUID,
    body: ManifestCreate,
    current: CurrentUser = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    user, org = current
    version = await db.scalar(select(AISystemVersion).where(AISystemVersion.id == version_id, AISystemVersion.org_id == org.id))
    if not version:
        raise HTTPException(status_code=404, detail="AI system version not found")
    items = (await db.scalars(select(AIDataUseRevision).where(AIDataUseRevision.id.in_(body.data_use_revision_ids), AIDataUseRevision.version_id == version.id, AIDataUseRevision.org_id == org.id))).all()
    if len(items) != len(set(body.data_use_revision_ids)):
        raise HTTPException(status_code=422, detail="Every manifest data-use revision must belong to this version and workspace")
    cutoff = body.evidence_cutoff or datetime.now(UTC)
    manifest, manifest_hash = build_release_manifest(system_id=str(version.system_id), version_id=str(version.id), version_hash=version.definition_hash, data_uses=[(str(item.id), item.definition_hash) for item in items], evidence_cutoff=cutoff)
    existing = await db.scalar(select(AIReleaseManifest).where(AIReleaseManifest.org_id == org.id, AIReleaseManifest.system_id == version.system_id, AIReleaseManifest.manifest_hash == manifest_hash))
    if existing:
        return {"id": str(existing.id), "manifestHash": existing.manifest_hash, "canonicalManifest": existing.canonical_manifest, "replayed": True}
    record = AIReleaseManifest(org_id=org.id, system_id=version.system_id, version_id=version.id, schema_version=manifest["schemaVersion"], canonical_manifest=manifest, manifest_hash=manifest_hash, evidence_cutoff=cutoff, created_by=user.id)
    db.add(record)
    await db.commit()
    return {"id": str(record.id), "manifestHash": manifest_hash, "canonicalManifest": manifest, "replayed": False}


@router.post("/release-manifests/{manifest_id}/reviews", status_code=201)
async def review_manifest(
    manifest_id: UUID,
    body: ReviewCreate,
    current: CurrentUser = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    user, org = current
    manifest = await db.scalar(select(AIReleaseManifest).where(AIReleaseManifest.id == manifest_id, AIReleaseManifest.org_id == org.id))
    if not manifest:
        raise HTTPException(status_code=404, detail="AI release manifest not found")
    evaluation_hashes = (await db.scalars(select(AIControlEvaluation.input_hash).where(AIControlEvaluation.manifest_id == manifest.id, AIControlEvaluation.org_id == org.id).order_by(AIControlEvaluation.input_hash))).all()
    snapshot_hash = canonical_hash({"manifestHash": manifest.manifest_hash, "evaluationHashes": list(evaluation_hashes), "reviewerRole": body.reviewer_role, "decision": body.decision})
    approval = AIApproval(org_id=org.id, system_id=manifest.system_id, manifest_id=manifest.id, reviewer_id=user.id, reviewer_role=body.reviewer_role, decision=body.decision, rationale=body.rationale, evidence_snapshot_hash=snapshot_hash, evidence_class="reviewer_decision")
    db.add(approval)
    await db.commit()
    return {"id": str(approval.id), "manifestId": str(manifest.id), "decision": approval.decision, "reviewerRole": approval.reviewer_role, "evidenceSnapshotHash": snapshot_hash, "evidenceClass": "reviewer_decision", "gating": False}


@router.post("/systems/{system_id}/deployments", status_code=201)
async def create_deployment(
    system_id: UUID,
    body: DeploymentCreate,
    current: CurrentUser = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    _user, org = current
    await _system_or_404(system_id, org.id, db)
    deployment = AIDeployment(org_id=org.id, system_id=system_id, **body.model_dump())
    db.add(deployment)
    await db.commit()
    return {"id": str(deployment.id), "environment": deployment.environment, "region": deployment.region, "activationGeneration": 0, "governanceMode": "observe"}


@router.post("/deployments/{deployment_id}/activate-manifest")
async def activate_manifest(
    deployment_id: UUID,
    body: ActivateManifest,
    current: CurrentUser = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    _user, org = current
    deployment = await db.scalar(select(AIDeployment).where(AIDeployment.id == deployment_id, AIDeployment.org_id == org.id))
    if not deployment:
        raise HTTPException(status_code=404, detail="AI deployment not found")
    manifest = await db.scalar(select(AIReleaseManifest).where(AIReleaseManifest.id == body.manifest_id, AIReleaseManifest.org_id == org.id, AIReleaseManifest.system_id == deployment.system_id, AIReleaseManifest.manifest_hash == body.manifest_hash))
    if not manifest:
        raise HTTPException(status_code=422, detail="Manifest identity/hash does not match this deployment")
    conditions = [AIDeployment.id == deployment.id, AIDeployment.org_id == org.id, AIDeployment.activation_generation == body.expected_generation]
    conditions.append(AIDeployment.active_manifest_hash.is_(None) if body.expected_active_manifest_hash is None else AIDeployment.active_manifest_hash == body.expected_active_manifest_hash)
    result = await db.execute(update(AIDeployment).where(*conditions).values(active_manifest_id=manifest.id, active_manifest_hash=manifest.manifest_hash, activation_generation=AIDeployment.activation_generation + 1, status="observing"))
    if result.rowcount != 1:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Deployment changed; refresh generation and active manifest hash")
    await db.commit()
    return {"deploymentId": str(deployment.id), "activeManifestId": str(manifest.id), "activeManifestHash": manifest.manifest_hash, "activationGeneration": body.expected_generation + 1, "mode": "observe"}


async def _connector_observation(data_use, source, db, org_id, body) -> dict | None:
    if source.type != "postgres" or data_use.use_kind != "rag" or not data_use.vector_contract:
        return None
    vector_table, _ = await _asset_or_404(UUID(data_use.vector_contract["vector_table_id"]), org_id, db)
    source_table = await db.get(MonitoredTable, data_use.table_id)
    config = decrypt_config(source.connection_config["encrypted"], str(org_id))
    connector = ConnectorFactory.create(source.type, config)
    try:
        contract = data_use.vector_contract
        return await connector.collect_rag_governance_observation(
            source_schema=source_table.schema_name, source_table=source_table.table_name,
            source_key=contract["source_key"], source_updated_at=contract.get("source_updated_at"),
            source_deleted_at=contract.get("source_deleted_at"), vector_schema=vector_table.schema_name,
            vector_table=vector_table.table_name, vector_source_key=contract["vector_source_key"],
            vector_updated_at=contract.get("vector_updated_at"), timeout_seconds=body.timeout_seconds,
            max_bytes_scanned=body.max_bytes_scanned,
        )
    finally:
        await connector.close()


@router.post("/deployments/{deployment_id}/evaluate")
async def evaluate_deployment(
    deployment_id: UUID,
    body: EvaluationRequest,
    current: CurrentUser = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    _user, org = current
    deployment = await db.scalar(select(AIDeployment).where(AIDeployment.id == deployment_id, AIDeployment.org_id == org.id))
    if not deployment or not deployment.active_manifest_id:
        raise HTTPException(status_code=409, detail="Deployment has no active manifest")
    system = await _system_or_404(deployment.system_id, org.id, db)
    manifest = await db.scalar(select(AIReleaseManifest).where(AIReleaseManifest.id == deployment.active_manifest_id, AIReleaseManifest.org_id == org.id))
    data_use_ids = [UUID(item["id"]) for item in manifest.canonical_manifest["dataUses"]]
    data_uses = (await db.scalars(select(AIDataUseRevision).where(AIDataUseRevision.id.in_(data_use_ids), AIDataUseRevision.org_id == org.id))).all()
    results = [evaluate_ownership(system)]
    for data_use in data_uses:
        source = await db.scalar(select(DataSource).where(DataSource.id == data_use.source_id, DataSource.org_id == org.id))
        profile = await db.scalar(select(TableProfile).where(TableProfile.table_id == data_use.table_id, TableProfile.collected_at <= manifest.evidence_cutoff).order_by(desc(TableProfile.collected_at)).limit(1))
        observation = None
        observation_error = None
        if source and source.type == "postgres" and data_use.use_kind == "rag":
            try:
                observation = await _connector_observation(data_use, source, db, org.id, body)
            except Exception as exc:
                observation_error = type(exc).__name__
        maximum_age = int((data_use.vector_contract or {}).get("maximum_freshness_seconds", 86400))
        results.append(evaluate_schema_freshness(data_use, profile, maximum_age_seconds=maximum_age))
        if observation_error:
            results.extend([
                type(evaluate_privileges(data_use, None, supported=True))(
                    "effective-db-role-drift", "error", "connector_observation", "connector_observation_error", {"errorType": observation_error}, {"allowedRoles": data_use.expected_db_roles}, str(data_use.id)
                ),
                type(evaluate_vector_consistency(data_use, None, supported=True))(
                    "vector-consistency", "error", "connector_observation", "connector_observation_error", {"errorType": observation_error}, {}, str(data_use.id)
                ),
            ])
        else:
            results.append(evaluate_privileges(data_use, observation, supported=bool(source and source.type == "postgres")))
            results.append(evaluate_vector_consistency(data_use, observation, supported=bool(source and source.type == "postgres")))
    persisted = []
    created_incident_ids = []
    for result in results:
        idem = canonical_hash({"client": body.client_idempotency_key, "manifest": manifest.manifest_hash, "control": result.control_id, "dataUse": result.data_use_revision_id})
        evaluation = await db.scalar(select(AIControlEvaluation).where(AIControlEvaluation.org_id == org.id, AIControlEvaluation.idempotency_key == idem))
        if not evaluation:
            evaluation = AIControlEvaluation(org_id=org.id, system_id=system.id, deployment_id=deployment.id, manifest_id=manifest.id, data_use_revision_id=UUID(result.data_use_revision_id) if result.data_use_revision_id else None, control_id=result.control_id, status=result.status, evidence_class=result.evidence_class, observed=result.observed, expected=result.expected, reason_code=result.reason_code, evaluator_version=EVALUATOR_VERSION, input_hash=result.input_hash, idempotency_key=idem)
            db.add(evaluation)
            await db.flush()
        dedupe = canonical_hash({"deployment": str(deployment.id), "control": result.control_id, "dataUse": result.data_use_revision_id})
        if result.status == "fail":
            statement = insert(AIGovernanceIncident).values(org_id=org.id, system_id=system.id, deployment_id=deployment.id, evaluation_id=evaluation.id, control_id=result.control_id, dedupe_key=dedupe, severity="P2", status="open", title=f"AI governance control failed: {result.control_id}").on_conflict_do_nothing(index_elements=[AIGovernanceIncident.org_id, AIGovernanceIncident.dedupe_key], index_where=AIGovernanceIncident.status.in_(["open", "acknowledged"])).returning(AIGovernanceIncident.id)
            incident_id = (await db.execute(statement)).scalar_one_or_none()
            if incident_id:
                created_incident_ids.append(str(incident_id))
        elif result.status == "pass":
            await db.execute(update(AIGovernanceIncident).where(AIGovernanceIncident.org_id == org.id, AIGovernanceIncident.dedupe_key == dedupe, AIGovernanceIncident.status.in_(["open", "acknowledged"])).values(status="resolved", resolved_at=datetime.now(UTC)))
        persisted.append({"id": str(evaluation.id), "controlId": result.control_id, "status": result.status, "evidenceClass": result.evidence_class, "reasonCode": result.reason_code, "observed": result.observed, "expected": result.expected, "inputHash": result.input_hash})
    await db.commit()
    from app.services.realtime import publish_event
    from app.tasks import send_governance_alerts
    await publish_event(str(org.id), "ai_governance.evaluated", {"systemId": str(system.id), "deploymentId": str(deployment.id), "manifestHash": manifest.manifest_hash})
    for incident_id in created_incident_ids:
        send_governance_alerts.delay(incident_id)
    return {"deploymentId": str(deployment.id), "manifestHash": manifest.manifest_hash, "mode": "observe", "evaluations": persisted}


@router.get("/systems/{system_id}/evidence")
async def evidence_timeline(
    system_id: UUID,
    current: CurrentUser = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    _user, org = current
    await _system_or_404(system_id, org.id, db)
    rows = (await db.scalars(select(AIControlEvaluation).where(AIControlEvaluation.system_id == system_id, AIControlEvaluation.org_id == org.id).order_by(desc(AIControlEvaluation.created_at)).limit(250))).all()
    return [{"id": str(row.id), "controlId": row.control_id, "status": row.status, "evidenceClass": row.evidence_class, "reasonCode": row.reason_code, "observed": row.observed, "expected": row.expected, "inputHash": row.input_hash, "evaluatorVersion": row.evaluator_version, "createdAt": row.created_at} for row in rows]
