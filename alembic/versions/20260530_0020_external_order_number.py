"""Add external work-order number

Revision ID: 20260530_0020
Revises: 20260530_0019
Create Date: 2026-05-30 22:05:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260530_0020"
down_revision = "20260530_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "work_orders",
        sa.Column("external_order_number", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.drop_column("external_order_number")
