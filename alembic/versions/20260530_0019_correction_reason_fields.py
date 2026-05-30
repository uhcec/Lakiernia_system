"""Add correction reason fields

Revision ID: 20260530_0019
Revises: 20260529_0018
Create Date: 2026-05-30 21:15:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260530_0019"
down_revision = "20260529_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("work_orders", sa.Column("correction_reason_category", sa.String(length=64), nullable=True))
    op.add_column("work_orders", sa.Column("correction_reason_note", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.drop_column("correction_reason_note")
        batch_op.drop_column("correction_reason_category")
