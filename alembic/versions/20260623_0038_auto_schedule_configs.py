"""Add auto_schedule_configs table (painting auto-scheduler rule priority, NA33)

Revision ID: 20260623_0038
Revises: 20260620_0033
Create Date: 2026-06-23 12:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260623_0038"
down_revision = "20260620_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auto_schedule_configs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("production_type", sa.String(length=32), nullable=False),
        sa.Column("rules_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("production_type", name="uq_auto_schedule_configs_production_type"),
    )


def downgrade() -> None:
    op.drop_table("auto_schedule_configs")
