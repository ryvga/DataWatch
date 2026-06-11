"""add check_config to monitored_tables

Revision ID: 010
Revises: 009
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('monitored_tables', sa.Column('check_config', postgresql.JSONB, nullable=True))

def downgrade():
    op.drop_column('monitored_tables', 'check_config')
