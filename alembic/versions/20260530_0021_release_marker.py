"""Add work-order release marker

Revision ID: 20260530_0021
Revises: 20260530_0020
Create Date: 2026-05-30 23:10:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260530_0021"
down_revision = "20260530_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "work_orders",
        sa.Column("released_to_client_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.drop_column("released_to_client_at")
