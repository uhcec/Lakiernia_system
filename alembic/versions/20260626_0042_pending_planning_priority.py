"""Add work_orders.pending_planning_priority (remember pin/urgent across a correction round, CHANGES #1)

A planning lock (pin/urgent) can only sit on a planned order, so a correction round that unplans the
order (queue_position → NULL) used to drop the lock entirely. This column remembers the manager's
pin/urgent intent while the order is out for correction; ``assign_plan`` re-applies it (and clears
this) when the order is re-planned. It is intentionally NOT bound by ``planning_priority_requires_planned``.

Revision ID: 20260626_0042
Revises: 20260626_0041
Create Date: 2026-06-26 01:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260626_0042"
down_revision = "20260626_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.add_column(
            sa.Column(
                "pending_planning_priority",
                sa.Enum("PINNED", "URGENT", name="planning_priority", native_enum=False),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.drop_column("pending_planning_priority")
