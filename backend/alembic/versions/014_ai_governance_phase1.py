"""AI governance phase-one inventory and supply-chain contract.

Revision ID: 014
Revises: 013
Create Date: 2026-08-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def _identity() -> sa.Column:
    return sa.Column("id", UUID(as_uuid=True), primary_key=True)


def _org() -> sa.Column:
    return sa.Column("org_id", UUID(as_uuid=True), nullable=False)


def _created() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.create_unique_constraint("uq_users_id_org", "users", ["id", "org_id"])
    op.create_unique_constraint("uq_teams_id_org", "teams", ["id", "org_id"])
    op.create_unique_constraint("uq_data_sources_id_org", "data_sources", ["id", "org_id"])
    op.create_unique_constraint("uq_monitored_tables_id_source", "monitored_tables", ["id", "source_id"])

    op.create_table(
        "ai_systems",
        _identity(),
        _org(),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("lifecycle_status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("intended_purpose", sa.Text(), nullable=False),
        sa.Column("prohibited_uses", JSONB, nullable=False, server_default="[]"),
        sa.Column("affected_population", sa.Text(), nullable=True),
        sa.Column("autonomy_level", sa.String(32), nullable=False, server_default="assistive"),
        sa.Column("human_oversight", sa.Text(), nullable=False),
        sa.Column("business_owner_id", UUID(as_uuid=True), nullable=True),
        sa.Column("technical_owner_id", UUID(as_uuid=True), nullable=True),
        sa.Column("risk_owner_id", UUID(as_uuid=True), nullable=True),
        sa.Column("team_id", UUID(as_uuid=True), nullable=True),
        sa.Column("risk_context", JSONB, nullable=False, server_default="{}"),
        sa.Column("current_version_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        _created(),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["business_owner_id", "org_id"], ["users.id", "users.org_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["technical_owner_id", "org_id"], ["users.id", "users.org_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["risk_owner_id", "org_id"], ["users.id", "users.org_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["team_id", "org_id"], ["teams.id", "teams.org_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("org_id", "slug", name="uq_ai_systems_org_slug"),
        sa.UniqueConstraint("id", "org_id", name="uq_ai_systems_id_org"),
        sa.UniqueConstraint("id", "org_id", "current_version_id", name="uq_ai_systems_current_pointer"),
        sa.CheckConstraint("lifecycle_status IN ('draft','development','production','paused','retired')", name="ck_ai_systems_lifecycle"),
    )

    op.create_table(
        "ai_system_versions",
        _identity(),
        _org(),
        sa.Column("system_id", UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("definition", JSONB, nullable=False),
        sa.Column("definition_hash", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(120), nullable=True),
        sa.Column("model", sa.String(200), nullable=True),
        sa.Column("artifact_hash", sa.String(128), nullable=True),
        sa.Column("prompt_config_hash", sa.String(128), nullable=True),
        sa.Column("evaluation_suite_hash", sa.String(128), nullable=True),
        sa.Column("change_rationale", sa.Text(), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        _created(),
        sa.ForeignKeyConstraint(["system_id", "org_id"], ["ai_systems.id", "ai_systems.org_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("system_id", "version_number", name="uq_ai_system_versions_number"),
        sa.UniqueConstraint("id", "org_id", "system_id", name="uq_ai_system_versions_owner"),
        sa.CheckConstraint("version_number > 0", name="ck_ai_system_versions_positive"),
    )
    op.create_foreign_key(
        "fk_ai_systems_current_version_owner",
        "ai_systems",
        "ai_system_versions",
        ["current_version_id", "org_id", "id"],
        ["id", "org_id", "system_id"],
        ondelete="RESTRICT",
    )

    op.create_table(
        "ai_data_use_revisions",
        _identity(),
        _org(),
        sa.Column("system_id", UUID(as_uuid=True), nullable=False),
        sa.Column("version_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", UUID(as_uuid=True), nullable=False),
        sa.Column("table_id", UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("use_kind", sa.String(24), nullable=False),
        sa.Column("fields", JSONB, nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("necessity", sa.Text(), nullable=False),
        sa.Column("steward", sa.String(255), nullable=False),
        sa.Column("sensitivity_ceiling", sa.String(32), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("residency", JSONB, nullable=False, server_default="[]"),
        sa.Column("allowed_transformations", JSONB, nullable=False, server_default="[]"),
        sa.Column("expected_db_roles", JSONB, nullable=False, server_default="[]"),
        sa.Column("vector_contract", JSONB, nullable=True),
        sa.Column("schema_fingerprint", sa.String(64), nullable=False),
        sa.Column("canonical_definition", JSONB, nullable=False),
        sa.Column("definition_hash", sa.String(64), nullable=False),
        sa.Column("evidence_class", sa.String(32), nullable=False, server_default="customer_assertion"),
        sa.Column("change_rationale", sa.Text(), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        _created(),
        sa.ForeignKeyConstraint(["version_id", "org_id", "system_id"], ["ai_system_versions.id", "ai_system_versions.org_id", "ai_system_versions.system_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_id", "org_id"], ["data_sources.id", "data_sources.org_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["table_id", "source_id"], ["monitored_tables.id", "monitored_tables.source_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("version_id", "ordinal", name="uq_ai_data_use_revision_ordinal"),
        sa.UniqueConstraint("id", "org_id", "system_id", name="uq_ai_data_use_revision_owner"),
        sa.CheckConstraint("use_kind IN ('training','fine_tuning','validation','rag','inference','feedback','telemetry')", name="ck_ai_data_use_kind"),
        sa.CheckConstraint("ordinal > 0", name="ck_ai_data_use_revision_positive"),
        sa.CheckConstraint("evidence_class = 'customer_assertion'", name="ck_ai_data_use_assertion_class"),
    )

    op.create_table(
        "ai_release_manifests",
        _identity(),
        _org(),
        sa.Column("system_id", UUID(as_uuid=True), nullable=False),
        sa.Column("version_id", UUID(as_uuid=True), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False, server_default="aigov-manifest/v1"),
        sa.Column("canonical_manifest", JSONB, nullable=False),
        sa.Column("manifest_hash", sa.String(64), nullable=False),
        sa.Column("evidence_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        _created(),
        sa.ForeignKeyConstraint(["version_id", "org_id", "system_id"], ["ai_system_versions.id", "ai_system_versions.org_id", "ai_system_versions.system_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("org_id", "system_id", "manifest_hash", name="uq_ai_release_manifest_hash"),
        sa.UniqueConstraint("id", "org_id", "system_id", name="uq_ai_release_manifest_owner"),
    )

    op.create_table(
        "ai_deployments",
        _identity(),
        _org(),
        sa.Column("system_id", UUID(as_uuid=True), nullable=False),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("region", sa.String(64), nullable=False, server_default="global"),
        sa.Column("workload_identity_hash", sa.String(128), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="registered"),
        sa.Column("active_manifest_id", UUID(as_uuid=True), nullable=True),
        sa.Column("active_manifest_hash", sa.String(64), nullable=True),
        sa.Column("activation_generation", sa.Integer(), nullable=False, server_default="0"),
        _created(),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["system_id", "org_id"], ["ai_systems.id", "ai_systems.org_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["active_manifest_id", "org_id", "system_id"], ["ai_release_manifests.id", "ai_release_manifests.org_id", "ai_release_manifests.system_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("org_id", "system_id", "environment", "region", name="uq_ai_deployment_scope"),
        sa.UniqueConstraint("id", "org_id", "system_id", name="uq_ai_deployment_owner"),
        sa.CheckConstraint("activation_generation >= 0", name="ck_ai_deployment_generation"),
    )

    op.create_table(
        "ai_approvals",
        _identity(),
        _org(),
        sa.Column("system_id", UUID(as_uuid=True), nullable=False),
        sa.Column("manifest_id", UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_id", UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_role", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("evidence_class", sa.String(32), nullable=False, server_default="reviewer_decision"),
        _created(),
        sa.ForeignKeyConstraint(["manifest_id", "org_id", "system_id"], ["ai_release_manifests.id", "ai_release_manifests.org_id", "ai_release_manifests.system_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewer_id", "org_id"], ["users.id", "users.org_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("id", "org_id", "system_id", name="uq_ai_approvals_owner"),
        sa.CheckConstraint("decision IN ('noted','approved','rejected','changes_requested')", name="ck_ai_approvals_decision"),
        sa.CheckConstraint("evidence_class = 'reviewer_decision'", name="ck_ai_approvals_evidence_class"),
    )

    op.create_table(
        "ai_control_evaluations",
        _identity(),
        _org(),
        sa.Column("system_id", UUID(as_uuid=True), nullable=False),
        sa.Column("deployment_id", UUID(as_uuid=True), nullable=False),
        sa.Column("manifest_id", UUID(as_uuid=True), nullable=False),
        sa.Column("data_use_revision_id", UUID(as_uuid=True), nullable=True),
        sa.Column("control_id", sa.String(80), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("evidence_class", sa.String(32), nullable=False),
        sa.Column("observed", JSONB, nullable=False, server_default="{}"),
        sa.Column("expected", JSONB, nullable=False, server_default="{}"),
        sa.Column("reason_code", sa.String(80), nullable=False),
        sa.Column("evaluator_version", sa.String(64), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        _created(),
        sa.ForeignKeyConstraint(["deployment_id", "org_id", "system_id"], ["ai_deployments.id", "ai_deployments.org_id", "ai_deployments.system_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["manifest_id", "org_id", "system_id"], ["ai_release_manifests.id", "ai_release_manifests.org_id", "ai_release_manifests.system_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["data_use_revision_id", "org_id", "system_id"], ["ai_data_use_revisions.id", "ai_data_use_revisions.org_id", "ai_data_use_revisions.system_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("org_id", "idempotency_key", name="uq_ai_control_evaluation_idempotency"),
        sa.UniqueConstraint("id", "org_id", "system_id", name="uq_ai_control_evaluation_owner"),
        sa.CheckConstraint("status IN ('pass','fail','unknown','unsupported','not_applicable','error')", name="ck_ai_control_evaluation_status"),
        sa.CheckConstraint("evidence_class IN ('customer_assertion','connector_observation')", name="ck_ai_control_evaluation_evidence_class"),
    )
    op.create_index("ix_ai_control_evaluations_system_created", "ai_control_evaluations", ["system_id", "created_at"])

    op.create_table(
        "ai_governance_incidents",
        _identity(),
        _org(),
        sa.Column("system_id", UUID(as_uuid=True), nullable=False),
        sa.Column("deployment_id", UUID(as_uuid=True), nullable=False),
        sa.Column("evaluation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("control_id", sa.String(80), nullable=False),
        sa.Column("dedupe_key", sa.String(128), nullable=False),
        sa.Column("severity", sa.String(8), nullable=False, server_default="P2"),
        sa.Column("status", sa.String(24), nullable=False, server_default="open"),
        sa.Column("title", sa.String(500), nullable=False),
        _created(),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["deployment_id", "org_id", "system_id"], ["ai_deployments.id", "ai_deployments.org_id", "ai_deployments.system_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["evaluation_id", "org_id", "system_id"], ["ai_control_evaluations.id", "ai_control_evaluations.org_id", "ai_control_evaluations.system_id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_ai_governance_incidents_system_status", "ai_governance_incidents", ["system_id", "status"])
    op.create_index(
        "uq_ai_governance_incident_active_dedupe",
        "ai_governance_incidents",
        ["org_id", "dedupe_key"],
        unique=True,
        postgresql_where=sa.text("status IN ('open', 'acknowledged')"),
    )

    op.execute("""
        CREATE FUNCTION reject_ai_governance_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'AI governance audit records are append-only';
        END;
        $$ LANGUAGE plpgsql;
    """)
    for table in ("ai_system_versions", "ai_data_use_revisions", "ai_release_manifests", "ai_approvals", "ai_control_evaluations"):
        op.execute(f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_ai_governance_mutation()")


def downgrade() -> None:
    op.execute("DROP FUNCTION reject_ai_governance_mutation() CASCADE")
    op.drop_table("ai_governance_incidents")
    op.drop_table("ai_control_evaluations")
    op.drop_table("ai_approvals")
    op.drop_table("ai_deployments")
    op.drop_table("ai_release_manifests")
    op.drop_table("ai_data_use_revisions")
    op.drop_constraint("fk_ai_systems_current_version_owner", "ai_systems", type_="foreignkey")
    op.drop_table("ai_system_versions")
    op.drop_table("ai_systems")
    op.drop_constraint("uq_monitored_tables_id_source", "monitored_tables", type_="unique")
    op.drop_constraint("uq_data_sources_id_org", "data_sources", type_="unique")
    op.drop_constraint("uq_teams_id_org", "teams", type_="unique")
    op.drop_constraint("uq_users_id_org", "users", type_="unique")
