"""Add counted quantity to stage states

Revision ID: 20260525_0006
Revises: 20260525_0005
Create Date: 2026-05-25 00:45:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260525_0006"
down_revision = "20260525_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("work_order_stage_states", sa.Column("counted_quantity", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("work_order_stage_states", "counted_quantity")