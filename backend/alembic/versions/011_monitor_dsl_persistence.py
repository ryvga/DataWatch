"""Add versioned safe monitor persistence

Revision ID: 011
Revises: 010
Create Date: 2026-07-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monitors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("table_id", UUID(as_uuid=True), sa.ForeignKey("monitored_tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(63), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False, server_default="dsl"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("current_revision", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("mode IN ('dsl', 'legacy_sql')", name="ck_monitors_mode"),
        sa.CheckConstraint("status IN ('draft', 'active', 'paused', 'archived')", name="ck_monitors_status"),
        sa.UniqueConstraint("org_id", "table_id", "name", name="uq_monitors_org_table_name"),
    )
    op.create_index("ix_monitors_org_status", "monitors", ["org_id", "status"])
    op.create_index("ix_monitors_table_id", "monitors", ["table_id"])

    op.create_table(
        "monitor_revisions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("monitor_id", UUID(as_uuid=True), sa.ForeignKey("monitors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("definition_version", sa.String(64), nullable=False),
        sa.Column("definition_hash", sa.String(64), nullable=False),
        sa.Column("definition", JSONB, nullable=False),
        sa.Column("validation_status", sa.String(20), nullable=False, server_default="valid"),
        sa.Column("schema_fingerprint", sa.String(64), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("revision > 0", name="ck_monitor_revisions_positive"),
        sa.UniqueConstraint("monitor_id", "revision", name="uq_monitor_revisions_number"),
    )
    op.create_index("ix_monitor_revisions_hash", "monitor_revisions", ["definition_hash"])
    op.create_index("ix_monitor_revisions_monitor_id", "monitor_revisions", ["monitor_id"])

    op.create_table(
        "monitor_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("monitor_id", UUID(as_uuid=True), sa.ForeignKey("monitors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision_id", UUID(as_uuid=True), sa.ForeignKey("monitor_revisions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("table_id", UUID(as_uuid=True), sa.ForeignKey("monitored_tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("measurements", JSONB, nullable=True),
        sa.Column("result", JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('queued', 'running', 'passed', 'failed', 'error', 'cancelled')", name="ck_monitor_runs_status"),
        sa.UniqueConstraint("org_id", "idempotency_key", name="uq_monitor_runs_idempotency"),
    )
    op.create_index("ix_monitor_runs_monitor_started", "monitor_runs", ["monitor_id", "started_at"])
    op.create_index("ix_monitor_runs_revision_id", "monitor_runs", ["revision_id"])
    op.create_index("ix_monitor_runs_table_id", "monitor_runs", ["table_id"])


def downgrade() -> None:
    op.drop_index("ix_monitor_runs_table_id", table_name="monitor_runs")
    op.drop_index("ix_monitor_runs_revision_id", table_name="monitor_runs")
    op.drop_index("ix_monitor_runs_monitor_started", table_name="monitor_runs")
    op.drop_table("monitor_runs")
    op.drop_index("ix_monitor_revisions_monitor_id", table_name="monitor_revisions")
    op.drop_index("ix_monitor_revisions_hash", table_name="monitor_revisions")
    op.drop_table("monitor_revisions")
    op.drop_index("ix_monitors_table_id", table_name="monitors")
    op.drop_index("ix_monitors_org_status", table_name="monitors")
    op.drop_table("monitors")
