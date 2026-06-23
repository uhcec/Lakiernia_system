"""Drop the stored WorkOrder.current_active_batch_id pointer; derive active_batch (NA46 §A4)

The active batch is now derived from ``active_batches`` — the partial-unique index
``uq_work_order_quantity_batches_one_active_per_work_order`` (WHERE is_active = 1) guarantees at most
one active batch per work order, so the single active batch *is* the active batch. The hand-synced
``current_active_batch_id`` pointer was redundant bookkeeping (a forgotten sync could desync it from
the real ``is_active`` state), so it is removed. The column was a plain nullable Integer with no FK or
constraint, so this is a simple column drop.

Revision ID: 20260622_0035
Revises: 20260622_0034
Create Date: 2026-06-22 13:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260622_0035"
down_revision = "20260622_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("work_orders", recreate="always") as batch_op:
        batch_op.drop_column("current_active_batch_id")


def downgrade() -> None:
    with op.batch_alter_table("work_orders", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("current_active_batch_id", sa.Integer(), nullable=True))
