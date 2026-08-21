"""AI governance phase-two immutable evidence ledger.

Revision ID: 015
Revises: 014
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("system_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deployment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("manifest_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data_use_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evidence_type", sa.String(80), nullable=False),
        sa.Column("evidence_class", sa.String(32), nullable=False),
        sa.Column("producer", sa.String(120), nullable=False),
        sa.Column("descriptor", postgresql.JSONB(), nullable=False),
        sa.Column("provenance", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("evaluator_version", sa.String(64), nullable=False),
        sa.Column("redaction_class", sa.String(32), nullable=False, server_default="metadata_only"),
        sa.Column("retention_class", sa.String(32), nullable=False, server_default="governance_indefinite"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "evidence_class IN ('customer_assertion', 'connector_observation', 'signed_workload_event', 'reviewer_decision', 'external_assessment')",
            name="ck_ai_evidence_class",
        ),
        sa.CheckConstraint(
            "redaction_class IN ('metadata_only', 'hashed', 'bounded_attachment')",
            name="ck_ai_evidence_redaction",
        ),
        sa.CheckConstraint(
            "retention_class IN ('governance_indefinite', 'operational_365d', 'customer_policy')",
            name="ck_ai_evidence_retention",
        ),
        sa.CheckConstraint("valid_until IS NULL OR valid_until >= valid_from", name="ck_ai_evidence_validity"),
        sa.UniqueConstraint("org_id", "idempotency_key", name="uq_ai_evidence_idempotency"),
        sa.UniqueConstraint("id", "org_id", "system_id", name="uq_ai_evidence_owner"),
        sa.ForeignKeyConstraint(
            ["deployment_id", "org_id", "system_id"],
            ["ai_deployments.id", "ai_deployments.org_id", "ai_deployments.system_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["manifest_id", "org_id", "system_id"],
            ["ai_release_manifests.id", "ai_release_manifests.org_id", "ai_release_manifests.system_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["data_use_revision_id", "org_id", "system_id"],
            ["ai_data_use_revisions.id", "ai_data_use_revisions.org_id", "ai_data_use_revisions.system_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["source_profile_id"], ["table_profiles.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_ai_evidence_system_collected", "ai_evidence", ["system_id", "collected_at"])
    op.execute(
        "CREATE TRIGGER ai_evidence_append_only BEFORE UPDATE OR DELETE ON ai_evidence "
        "FOR EACH ROW EXECUTE FUNCTION reject_ai_governance_mutation()"
    )
    op.add_column(
        "ai_control_evaluations",
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_ai_control_evaluations_evidence_owner",
        "ai_control_evaluations",
        "ai_evidence",
        ["evidence_id", "org_id", "system_id"],
        ["id", "org_id", "system_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_ai_control_evaluations_evidence_owner", "ai_control_evaluations", type_="foreignkey"
    )
    op.drop_column("ai_control_evaluations", "evidence_id")
    op.drop_table("ai_evidence")
