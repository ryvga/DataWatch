"""Add unique constraint on monitored_tables (source_id, schema_name, table_name)

Revision ID: 009
Revises: 008
Create Date: 2026-06-11
"""
from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove any existing duplicates before adding the constraint (keep the earliest created_at)
    op.execute("""
        DELETE FROM monitored_tables
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY source_id, schema_name, table_name
                           ORDER BY created_at ASC
                       ) AS rn
                FROM monitored_tables
            ) sub
            WHERE rn > 1
        )
    """)
    op.create_unique_constraint(
        "uq_monitored_table_source_schema_table",
        "monitored_tables",
        ["source_id", "schema_name", "table_name"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_monitored_table_source_schema_table", "monitored_tables", type_="unique")
