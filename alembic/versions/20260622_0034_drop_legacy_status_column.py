"""Drop the legacy WorkOrder.status column; make is_incomplete_on_arrival the single source (NA41)

The legacy `status` enum was redundant with `is_incomplete_on_arrival` (set/cleared together at every
write site) yet load-bearing in the `incomplete_requires_unplanned` CHECK. This migration rewrites that
CHECK to reference only `is_incomplete_on_arrival` and drops the `status` column. Existing planned rows
already satisfy `is_incomplete_on_arrival = 0` (the old CHECK required it), so there is no dirty data.

The read-model `status` field stays — it is derived from `process_status`, not stored.

Revision ID: 20260622_0034
Revises: 20260622_0033
Create Date: 2026-06-22 12:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260622_0034"
down_revision = "20260622_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("work_orders", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_work_orders_incomplete_requires_unplanned", type_="check")
        batch_op.create_check_constraint(
            "ck_work_orders_incomplete_requires_unplanned",
            "queue_position IS NULL OR is_incomplete_on_arrival = 0",
        )
        batch_op.drop_column("status")


def downgrade() -> None:
    with op.batch_alter_table("work_orders", recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="ENTERED",
            )
        )
        batch_op.drop_constraint("ck_work_orders_incomplete_requires_unplanned", type_="check")
        batch_op.create_check_constraint(
            "ck_work_orders_incomplete_requires_unplanned",
            "queue_position IS NULL OR (is_incomplete_on_arrival = 0 AND status != 'INCOMPLETE')",
        )
