"""Add incomplete-on-arrival flag to work orders

Revision ID: 20260525_0005
Revises: 20260525_0004
Create Date: 2026-05-25 00:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260525_0005"
down_revision = "20260525_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "work_orders",
        sa.Column("is_incomplete_on_arrival", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.alter_column("is_incomplete_on_arrival", existing_type=sa.Boolean(), server_default=None)


def downgrade() -> None:
    op.drop_column("work_orders", "is_incomplete_on_arrival")