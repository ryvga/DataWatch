"""Persist profile provenance and widen population counts

Revision ID: 013
Revises: 012
Create Date: 2026-07-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "table_profiles",
        "row_count",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=True,
    )
    op.add_column(
        "table_profiles",
        sa.Column("profile_provenance", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM table_profiles "
        "WHERE row_count > 2147483647 OR row_count < -2147483648) THEN "
        "RAISE EXCEPTION 'cannot downgrade profile row_count with 64-bit values'; "
        "END IF; END $$"
    )
    op.drop_column("table_profiles", "profile_provenance")
    op.alter_column(
        "table_profiles",
        "row_count",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=True,
    )
