"""Harden typed monitor run and policy state

Revision ID: 012
Revises: 011
Create Date: 2026-07-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None

REVISION_TRIGGER_FUNCTION_SQL = """
CREATE FUNCTION datawatch_reject_monitor_revision_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'monitor revisions are append-only';
END;
$$
"""
REVISION_TRIGGER_SQL = """
CREATE TRIGGER trg_monitor_revisions_append_only
BEFORE UPDATE OR DELETE ON monitor_revisions
FOR EACH ROW EXECUTE FUNCTION datawatch_reject_monitor_revision_mutation()
"""
RUN_TRIGGER_FUNCTION_SQL = """
CREATE FUNCTION datawatch_reject_terminal_monitor_run_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status IN ('passed', 'failed', 'error', 'cancelled') THEN
        IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN
            RETURN OLD;
        END IF;
        RAISE EXCEPTION 'terminal monitor runs are immutable';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$
"""
RUN_TRIGGER_SQL = """
CREATE TRIGGER trg_monitor_runs_terminal_immutable
BEFORE UPDATE OR DELETE ON monitor_runs
FOR EACH ROW EXECUTE FUNCTION datawatch_reject_terminal_monitor_run_mutation()
"""


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM monitor_runs) THEN "
        "RAISE EXCEPTION 'migration 012 requires empty monitor_runs; activation was gated'; "
        "END IF; END $$"
    )
    op.create_unique_constraint("uq_monitors_org_id", "monitors", ["org_id", "id"])
    op.create_unique_constraint("uq_monitors_id_table", "monitors", ["id", "table_id"])
    op.create_unique_constraint(
        "uq_monitor_revisions_monitor_id",
        "monitor_revisions",
        ["monitor_id", "id"],
    )
    op.add_column("monitors", sa.Column("active_revision_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_monitors_active_revision_owner",
        "monitors",
        "monitor_revisions",
        ["id", "active_revision_id"],
        ["monitor_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_monitors_active_revision",
        "monitors",
        "status != 'active' OR active_revision_id IS NOT NULL",
    )

    op.add_column("monitor_runs", sa.Column("trigger_type", sa.String(20), nullable=False))
    op.add_column(
        "monitor_runs",
        sa.Column(
            "profile_id",
            UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column("monitor_runs", sa.Column("sequence_at", sa.DateTime(timezone=True), nullable=False))
    op.add_column(
        "monitor_runs",
        sa.Column("queued_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column("monitor_runs", sa.Column("plan_hash", sa.String(64), nullable=False))
    op.add_column("monitor_runs", sa.Column("planner_version", sa.String(64), nullable=False))
    op.add_column("monitor_runs", sa.Column("definition_hash", sa.String(64), nullable=False))
    op.add_column("monitor_runs", sa.Column("schema_fingerprint", sa.String(64), nullable=True))
    op.add_column(
        "monitor_runs",
        sa.Column("attempt", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column("monitor_runs", sa.Column("claim_token", UUID(as_uuid=True), nullable=True))
    op.add_column("monitor_runs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("monitor_runs", sa.Column("error_code", sa.String(64), nullable=True))
    op.alter_column("monitor_runs", "started_at", nullable=True, server_default=None)

    op.create_unique_constraint(
        "uq_monitor_runs_monitor_id",
        "monitor_runs",
        ["monitor_id", "id"],
    )
    op.create_foreign_key(
        "fk_monitor_runs_monitor_owner",
        "monitor_runs",
        "monitors",
        ["org_id", "monitor_id"],
        ["org_id", "id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_monitor_runs_revision_owner",
        "monitor_runs",
        "monitor_revisions",
        ["monitor_id", "revision_id"],
        ["monitor_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_monitor_runs_table_owner",
        "monitor_runs",
        "monitors",
        ["monitor_id", "table_id"],
        ["id", "table_id"],
        ondelete="CASCADE",
    )

    op.create_check_constraint(
        "ck_monitor_runs_trigger_profile",
        "monitor_runs",
        "(trigger_type = 'on_profile' AND profile_id IS NOT NULL) OR "
        "(trigger_type = 'manual' AND profile_id IS NULL)",
    )
    op.create_check_constraint("ck_monitor_runs_attempt_positive", "monitor_runs", "attempt > 0")
    op.create_check_constraint(
        "ck_monitor_runs_lifecycle",
        "monitor_runs",
        "(status = 'queued' AND claim_token IS NULL AND started_at IS NULL "
        "AND lease_expires_at IS NULL AND completed_at IS NULL) OR "
        "(status = 'running' AND claim_token IS NOT NULL AND started_at IS NOT NULL "
        "AND lease_expires_at IS NOT NULL AND completed_at IS NULL) OR "
        "(status IN ('passed', 'failed', 'error', 'cancelled') "
        "AND completed_at IS NOT NULL AND claim_token IS NULL AND lease_expires_at IS NULL)",
    )
    op.create_check_constraint(
        "ck_monitor_runs_terminal_result",
        "monitor_runs",
        "status NOT IN ('passed', 'failed') OR (measurements IS NOT NULL AND result IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_monitor_runs_error_payload",
        "monitor_runs",
        "status != 'error' OR (error_code IS NOT NULL AND error IS NOT NULL)",
    )
    op.create_index(
        "uq_monitor_runs_profile_trigger",
        "monitor_runs",
        ["monitor_id", "revision_id", "profile_id"],
        unique=True,
        postgresql_where=sa.text("profile_id IS NOT NULL"),
    )
    op.create_index(
        "uq_monitor_runs_one_running",
        "monitor_runs",
        ["monitor_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )

    op.create_table(
        "monitor_evaluation_states",
        sa.Column(
            "monitor_id",
            UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "revision_id",
            UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("phase", sa.String(20), server_default="healthy", nullable=False),
        sa.Column("breach_streak", sa.Integer(), server_default="0", nullable=False),
        sa.Column("recovery_streak", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_run_id",
            UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("last_sequence_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_idempotency_key", sa.String(128), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("phase IN ('healthy', 'breached')", name="ck_monitor_eval_phase"),
        sa.CheckConstraint(
            "breach_streak >= 0 AND recovery_streak >= 0",
            name="ck_monitor_eval_streaks_nonnegative",
        ),
        sa.CheckConstraint("version > 0", name="ck_monitor_eval_version_positive"),
        sa.ForeignKeyConstraint(
            ["org_id", "monitor_id"],
            ["monitors.org_id", "monitors.id"],
            name="fk_monitor_eval_monitor_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["monitor_id", "revision_id"],
            ["monitor_revisions.monitor_id", "monitor_revisions.id"],
            name="fk_monitor_eval_revision_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["monitor_id", "last_run_id"],
            ["monitor_runs.monitor_id", "monitor_runs.id"],
            name="fk_monitor_eval_last_run_owner",
        ),
    )
    op.create_index(
        "ix_monitor_evaluation_states_org_id",
        "monitor_evaluation_states",
        ["org_id"],
    )
    op.execute(REVISION_TRIGGER_FUNCTION_SQL)
    op.execute(REVISION_TRIGGER_SQL)
    op.execute(RUN_TRIGGER_FUNCTION_SQL)
    op.execute(RUN_TRIGGER_SQL)


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_monitor_runs_terminal_immutable ON monitor_runs")
    op.execute("DROP FUNCTION datawatch_reject_terminal_monitor_run_mutation()")
    op.execute("DROP TRIGGER trg_monitor_revisions_append_only ON monitor_revisions")
    op.execute("DROP FUNCTION datawatch_reject_monitor_revision_mutation()")
    op.drop_index("ix_monitor_evaluation_states_org_id", table_name="monitor_evaluation_states")
    op.drop_table("monitor_evaluation_states")
    op.drop_index("uq_monitor_runs_one_running", table_name="monitor_runs")
    op.drop_index("uq_monitor_runs_profile_trigger", table_name="monitor_runs")
    for constraint in (
        "ck_monitor_runs_error_payload",
        "ck_monitor_runs_terminal_result",
        "ck_monitor_runs_lifecycle",
        "ck_monitor_runs_attempt_positive",
        "ck_monitor_runs_trigger_profile",
    ):
        op.drop_constraint(constraint, "monitor_runs", type_="check")
    for constraint in (
        "fk_monitor_runs_table_owner",
        "fk_monitor_runs_revision_owner",
        "fk_monitor_runs_monitor_owner",
    ):
        op.drop_constraint(constraint, "monitor_runs", type_="foreignkey")
    op.drop_constraint("uq_monitor_runs_monitor_id", "monitor_runs", type_="unique")
    op.execute("UPDATE monitor_runs SET started_at = queued_at WHERE started_at IS NULL")
    op.alter_column(
        "monitor_runs",
        "started_at",
        nullable=False,
        server_default=sa.func.now(),
    )
    for column in (
        "error_code",
        "lease_expires_at",
        "claim_token",
        "attempt",
        "schema_fingerprint",
        "definition_hash",
        "planner_version",
        "plan_hash",
        "queued_at",
        "sequence_at",
        "profile_id",
        "trigger_type",
    ):
        op.drop_column("monitor_runs", column)
    op.drop_constraint("ck_monitors_active_revision", "monitors", type_="check")
    op.drop_constraint("fk_monitors_active_revision_owner", "monitors", type_="foreignkey")
    op.drop_column("monitors", "active_revision_id")
    op.drop_constraint(
        "uq_monitor_revisions_monitor_id",
        "monitor_revisions",
        type_="unique",
    )
    op.drop_constraint("uq_monitors_id_table", "monitors", type_="unique")
    op.drop_constraint("uq_monitors_org_id", "monitors", type_="unique")
