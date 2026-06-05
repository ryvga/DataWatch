"""Add PayPal billing fields to organizations

Revision ID: 004
Revises: 003
Create Date: 2026-06-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("paypal_subscription_id", sa.String(100), nullable=True))
    op.add_column("organizations", sa.Column("billing_period", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("organizations", "billing_period")
    op.drop_column("organizations", "paypal_subscription_id")
