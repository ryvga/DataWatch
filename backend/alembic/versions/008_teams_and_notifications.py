"""Add teams/oncall/notification-prefs schema

Revision ID: 008
Revises: 007
Create Date: 2026-06-07

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Ensure teams table exists (create if missing) ─────────────────────────
    # The teams table may not exist on this branch yet; create it if absent.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS teams (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_teams_org_id ON teams (org_id)"
    )

    # ── Ensure team_members table exists ──────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS team_members (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role VARCHAR(50) NOT NULL DEFAULT 'member',
            joined_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_team_members_team_id ON team_members (team_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_team_members_user_id ON team_members (user_id)"
    )

    # ── Add columns to teams ──────────────────────────────────────────────────
    op.add_column("teams", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("teams", sa.Column("color", sa.String(7), nullable=True))

    # ── Add columns to incidents ──────────────────────────────────────────────
    op.add_column(
        "incidents",
        sa.Column("assignee_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_incidents_assignee_id",
        "incidents", "users",
        ["assignee_id"], ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "incidents",
        sa.Column("assigned_team_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_incidents_assigned_team_id",
        "incidents", "teams",
        ["assigned_team_id"], ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "incidents",
        sa.Column("acknowledged_by_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_incidents_acknowledged_by_id",
        "incidents", "users",
        ["acknowledged_by_id"], ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "incidents",
        sa.Column("resolved_by_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_incidents_resolved_by_id",
        "incidents", "users",
        ["resolved_by_id"], ["id"],
        ondelete="SET NULL",
    )

    # ── Add columns to monitored_tables ───────────────────────────────────────
    op.add_column(
        "monitored_tables",
        sa.Column("owner_team_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_monitored_tables_owner_team_id",
        "monitored_tables", "teams",
        ["owner_team_id"], ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "monitored_tables",
        sa.Column("owner_user_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_monitored_tables_owner_user_id",
        "monitored_tables", "users",
        ["owner_user_id"], ["id"],
        ondelete="SET NULL",
    )

    # ── Create oncall_schedules ───────────────────────────────────────────────
    op.create_table(
        "oncall_schedules",
        sa.Column(
            "id",
            sa.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "team_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_oncall_team_starts", "oncall_schedules", ["team_id", "starts_at"])

    # ── Create user_notification_prefs ────────────────────────────────────────
    op.create_table(
        "user_notification_prefs",
        sa.Column(
            "id",
            sa.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "org_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("notify_assigned", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notify_team", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notify_status_change", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("daily_digest", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("digest_hour", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("mute_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_notif_prefs_user", "user_notification_prefs", ["user_id"])
    op.create_index("ix_notif_prefs_org", "user_notification_prefs", ["org_id"])


def downgrade() -> None:
    # Drop indexes and new tables first
    op.drop_index("ix_notif_prefs_org", table_name="user_notification_prefs")
    op.drop_index("ix_notif_prefs_user", table_name="user_notification_prefs")
    op.drop_table("user_notification_prefs")

    op.drop_index("ix_oncall_team_starts", table_name="oncall_schedules")
    op.drop_table("oncall_schedules")

    # Drop columns from monitored_tables
    op.drop_constraint("fk_monitored_tables_owner_user_id", "monitored_tables", type_="foreignkey")
    op.drop_column("monitored_tables", "owner_user_id")
    op.drop_constraint("fk_monitored_tables_owner_team_id", "monitored_tables", type_="foreignkey")
    op.drop_column("monitored_tables", "owner_team_id")

    # Drop columns from incidents
    op.drop_constraint("fk_incidents_resolved_by_id", "incidents", type_="foreignkey")
    op.drop_column("incidents", "resolved_by_id")
    op.drop_constraint("fk_incidents_acknowledged_by_id", "incidents", type_="foreignkey")
    op.drop_column("incidents", "acknowledged_by_id")
    op.drop_constraint("fk_incidents_assigned_team_id", "incidents", type_="foreignkey")
    op.drop_column("incidents", "assigned_team_id")
    op.drop_constraint("fk_incidents_assignee_id", "incidents", type_="foreignkey")
    op.drop_column("incidents", "assignee_id")

    # Drop columns from teams
    op.drop_column("teams", "color")
    op.drop_column("teams", "description")
