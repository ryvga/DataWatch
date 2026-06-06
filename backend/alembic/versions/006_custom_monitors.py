"""Add custom_monitors table

Revision ID: 006
Revises: 005
Create Date: 2026-06-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op


revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "custom_monitors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("table_id", UUID(as_uuid=True), sa.ForeignKey("monitored_tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("sql_query", sa.Text, nullable=False),
        sa.Column("severity", sa.String(10), nullable=False, server_default="P3"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("run_on_profile", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_result", JSONB, nullable=True),
    )
    op.create_index("ix_custom_monitors_table_id", "custom_monitors", ["table_id"])
    op.create_index("ix_custom_monitors_org_id", "custom_monitors", ["org_id"])
    op.create_index("ix_custom_monitors_table_active", "custom_monitors", ["table_id", "is_active"])


def downgrade() -> None:
    op.drop_index("ix_custom_monitors_table_active", table_name="custom_monitors")
    op.drop_index("ix_custom_monitors_org_id", table_name="custom_monitors")
    op.drop_index("ix_custom_monitors_table_id", table_name="custom_monitors")
    op.drop_table("custom_monitors")
