"""SaaS schema: staff users, invites, teams, org billing fields, user roles

Revision ID: 003
Revises: 002
Create Date: 2026-06-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. organizations — billing + LLM fields
    op.add_column("organizations", sa.Column("llm_api_key_encrypted", sa.Text, nullable=True))
    op.add_column("organizations", sa.Column("llm_model", sa.String(200), nullable=True))
    op.add_column("organizations", sa.Column("stripe_customer_id", sa.String(100), nullable=True))
    op.add_column("organizations", sa.Column("subscription_status", sa.String(50), nullable=False, server_default="trialing"))
    op.add_column("organizations", sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True))

    # 2. users — replace is_admin with role, add full_name, last_login_at
    op.add_column("users", sa.Column("full_name", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("role", sa.String(50), nullable=False, server_default="owner"))
    op.drop_column("users", "is_admin")

    # 3. staff_users — DataWatch team members
    op.create_table(
        "staff_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_staff_users_email", "staff_users", ["email"])

    # 4. invites — org member invitations
    op.create_table(
        "invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="member"),
        sa.Column("token", sa.String(255), nullable=False, unique=True),
        sa.Column("invited_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_invites_org_id", "invites", ["org_id"])
    op.create_index("ix_invites_email", "invites", ["email"])
    op.create_index("ix_invites_token", "invites", ["token"])

    # 5. teams
    op.create_table(
        "teams",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_teams_org_id", "teams", ["org_id"])

    # 6. team_members
    op.create_table(
        "team_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="member"),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_team_members_team_id", "team_members", ["team_id"])
    op.create_index("ix_team_members_user_id", "team_members", ["user_id"])


def downgrade() -> None:
    op.drop_table("team_members")
    op.drop_table("teams")
    op.drop_table("invites")
    op.drop_table("staff_users")

    op.add_column("users", sa.Column("is_admin", sa.Boolean, nullable=False, server_default="true"))
    op.drop_column("users", "role")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "full_name")

    op.drop_column("organizations", "trial_ends_at")
    op.drop_column("organizations", "subscription_status")
    op.drop_column("organizations", "stripe_customer_id")
    op.drop_column("organizations", "llm_model")
    op.drop_column("organizations", "llm_api_key_encrypted")
