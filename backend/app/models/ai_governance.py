"""Phase-one AI governance inventory and immutable audit records."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AISystem(Base):
    __tablename__ = "ai_systems"
    __table_args__ = (
        UniqueConstraint("org_id", "slug", name="uq_ai_systems_org_slug"),
        UniqueConstraint("id", "org_id", name="uq_ai_systems_id_org"),
        UniqueConstraint("id", "org_id", "current_version_id", name="uq_ai_systems_current_pointer"),
        ForeignKeyConstraint(
            ["business_owner_id", "org_id"], ["users.id", "users.org_id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["technical_owner_id", "org_id"], ["users.id", "users.org_id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["risk_owner_id", "org_id"], ["users.id", "users.org_id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(["team_id", "org_id"], ["teams.id", "teams.org_id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["current_version_id", "org_id", "id"],
            ["ai_system_versions.id", "ai_system_versions.org_id", "ai_system_versions.system_id"],
            name="fk_ai_systems_current_version_owner",
            use_alter=True,
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "lifecycle_status IN ('draft', 'development', 'production', 'paused', 'retired')",
            name="ck_ai_systems_lifecycle",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    intended_purpose: Mapped[str] = mapped_column(Text, nullable=False)
    prohibited_uses: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    affected_population: Mapped[str | None] = mapped_column(Text, nullable=True)
    autonomy_level: Mapped[str] = mapped_column(String(32), nullable=False, default="assistive")
    human_oversight: Mapped[str] = mapped_column(Text, nullable=False)
    business_owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    technical_owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    risk_owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    team_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    risk_context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AISystemVersion(Base):
    __tablename__ = "ai_system_versions"
    __table_args__ = (
        UniqueConstraint("system_id", "version_number", name="uq_ai_system_versions_number"),
        UniqueConstraint("id", "org_id", "system_id", name="uq_ai_system_versions_owner"),
        ForeignKeyConstraint(
            ["system_id", "org_id"], ["ai_systems.id", "ai_systems.org_id"], ondelete="CASCADE"
        ),
        CheckConstraint("version_number > 0", name="ck_ai_system_versions_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    system_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    definition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    artifact_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_config_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    evaluation_suite_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    change_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AIDataUseRevision(Base):
    __tablename__ = "ai_data_use_revisions"
    __table_args__ = (
        UniqueConstraint("version_id", "ordinal", name="uq_ai_data_use_revision_ordinal"),
        UniqueConstraint("id", "org_id", "system_id", name="uq_ai_data_use_revision_owner"),
        ForeignKeyConstraint(
            ["version_id", "org_id", "system_id"],
            ["ai_system_versions.id", "ai_system_versions.org_id", "ai_system_versions.system_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_id", "org_id"], ["data_sources.id", "data_sources.org_id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["table_id", "source_id"],
            ["monitored_tables.id", "monitored_tables.source_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "use_kind IN ('training', 'fine_tuning', 'validation', 'rag', 'inference', 'feedback', 'telemetry')",
            name="ck_ai_data_use_kind",
        ),
        CheckConstraint("ordinal > 0", name="ck_ai_data_use_revision_positive"),
        CheckConstraint("evidence_class = 'customer_assertion'", name="ck_ai_data_use_assertion_class"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    system_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    table_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    use_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    fields: Mapped[list] = mapped_column(JSONB, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    necessity: Mapped[str] = mapped_column(Text, nullable=False)
    steward: Mapped[str] = mapped_column(String(255), nullable=False)
    sensitivity_ceiling: Mapped[str] = mapped_column(String(32), nullable=False)
    retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    residency: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    allowed_transformations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    expected_db_roles: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    vector_contract: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    schema_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_definition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    definition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_class: Mapped[str] = mapped_column(String(32), nullable=False, default="customer_assertion")
    change_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AIReleaseManifest(Base):
    __tablename__ = "ai_release_manifests"
    __table_args__ = (
        UniqueConstraint("org_id", "system_id", "manifest_hash", name="uq_ai_release_manifest_hash"),
        UniqueConstraint("id", "org_id", "system_id", name="uq_ai_release_manifest_owner"),
        ForeignKeyConstraint(
            ["version_id", "org_id", "system_id"],
            ["ai_system_versions.id", "ai_system_versions.org_id", "ai_system_versions.system_id"],
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    system_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False, default="aigov-manifest/v1")
    canonical_manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AIDeployment(Base):
    __tablename__ = "ai_deployments"
    __table_args__ = (
        UniqueConstraint("org_id", "system_id", "environment", "region", name="uq_ai_deployment_scope"),
        UniqueConstraint("id", "org_id", "system_id", name="uq_ai_deployment_owner"),
        ForeignKeyConstraint(
            ["system_id", "org_id"], ["ai_systems.id", "ai_systems.org_id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["active_manifest_id", "org_id", "system_id"],
            ["ai_release_manifests.id", "ai_release_manifests.org_id", "ai_release_manifests.system_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("activation_generation >= 0", name="ck_ai_deployment_generation"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    system_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    region: Mapped[str] = mapped_column(String(64), nullable=False, default="global")
    workload_identity_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="registered")
    active_manifest_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    active_manifest_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    activation_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AIApproval(Base):
    """Append-only reviewer attestation; phase one does not enforce it as a gate."""

    __tablename__ = "ai_approvals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["manifest_id", "org_id", "system_id"],
            ["ai_release_manifests.id", "ai_release_manifests.org_id", "ai_release_manifests.system_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["reviewer_id", "org_id"], ["users.id", "users.org_id"], ondelete="RESTRICT"
        ),
        UniqueConstraint("id", "org_id", "system_id", name="uq_ai_approvals_owner"),
        CheckConstraint(
            "decision IN ('noted', 'approved', 'rejected', 'changes_requested')",
            name="ck_ai_approvals_decision",
        ),
        CheckConstraint("evidence_class = 'reviewer_decision'", name="ck_ai_approvals_evidence_class"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    system_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    manifest_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reviewer_role: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_class: Mapped[str] = mapped_column(String(32), nullable=False, default="reviewer_decision")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AIControlEvaluation(Base):
    __tablename__ = "ai_control_evaluations"
    __table_args__ = (
        UniqueConstraint("org_id", "idempotency_key", name="uq_ai_control_evaluation_idempotency"),
        UniqueConstraint("id", "org_id", "system_id", name="uq_ai_control_evaluation_owner"),
        ForeignKeyConstraint(
            ["deployment_id", "org_id", "system_id"],
            ["ai_deployments.id", "ai_deployments.org_id", "ai_deployments.system_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["manifest_id", "org_id", "system_id"],
            ["ai_release_manifests.id", "ai_release_manifests.org_id", "ai_release_manifests.system_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["data_use_revision_id", "org_id", "system_id"],
            ["ai_data_use_revisions.id", "ai_data_use_revisions.org_id", "ai_data_use_revisions.system_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('pass', 'fail', 'unknown', 'unsupported', 'not_applicable', 'error')",
            name="ck_ai_control_evaluation_status",
        ),
        CheckConstraint(
            "evidence_class IN ('customer_assertion', 'connector_observation')",
            name="ck_ai_control_evaluation_evidence_class",
        ),
        Index("ix_ai_control_evaluations_system_created", "system_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    system_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    deployment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    manifest_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    data_use_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    control_id: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    evidence_class: Mapped[str] = mapped_column(String(32), nullable=False)
    observed: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    expected: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    evaluator_version: Mapped[str] = mapped_column(String(64), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AIGovernanceIncident(Base):
    __tablename__ = "ai_governance_incidents"
    __table_args__ = (
        Index(
            "uq_ai_governance_incident_active_dedupe",
            "org_id",
            "dedupe_key",
            unique=True,
            postgresql_where=text("status IN ('open', 'acknowledged')"),
        ),
        ForeignKeyConstraint(
            ["deployment_id", "org_id", "system_id"],
            ["ai_deployments.id", "ai_deployments.org_id", "ai_deployments.system_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["evaluation_id", "org_id", "system_id"],
            ["ai_control_evaluations.id", "ai_control_evaluations.org_id", "ai_control_evaluations.system_id"],
            ondelete="RESTRICT",
        ),
        Index("ix_ai_governance_incidents_system_status", "system_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    system_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    deployment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    control_id: Mapped[str] = mapped_column(String(80), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(8), nullable=False, default="P2")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


_IMMUTABLE = (AISystemVersion, AIDataUseRevision, AIReleaseManifest, AIApproval, AIControlEvaluation)


def _reject_immutable_mutation(_mapper, _connection, target) -> None:
    raise ValueError(f"{target.__class__.__name__} records are append-only")


for _model in _IMMUTABLE:
    event.listen(_model, "before_update", _reject_immutable_mutation)
    event.listen(_model, "before_delete", _reject_immutable_mutation)
