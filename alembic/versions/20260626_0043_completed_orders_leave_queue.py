"""Loosen the planned invariant so completed orders can leave the queue keeping their line (CHANGES #3)

Previously an order was "planned" exactly when it had BOTH a production line and a queue position (both
set or both unset). To let a completed order leave the active queue (release its position) while keeping
the line it ran on — so throughput stats that split by line still work — the invariant is loosened to:
a queue position requires a line, but a line may exist without a position.

Allowed states after this:
* (line NULL, position NULL)      — never planned
* (line set,  position set)       — planned / active in the queue
* (line set,  position NULL)      — completed: left the active queue, line retained for stats
Forbidden: (line NULL, position set).

Revision ID: 20260626_0043
Revises: 20260626_0042
Create Date: 2026-06-26 02:00:00
"""

from alembic import op


revision = "20260626_0043"
down_revision = "20260626_0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("work_orders", recreate="always") as batch_op:
        batch_op.drop_constraint(
            "ck_work_orders_planned_requires_production_type_and_queue_position", type_="check"
        )
        batch_op.create_check_constraint(
            "ck_work_orders_queue_position_requires_production_type",
            "queue_position IS NULL OR production_type IS NOT NULL",
        )


def downgrade() -> None:
    # Reverting requires every "left the queue" row (line set, position NULL) to be fully unplanned
    # first, or the stricter constraint would reject it.
    op.execute(
        "UPDATE work_orders SET production_type = NULL "
        "WHERE queue_position IS NULL AND production_type IS NOT NULL"
    )
    with op.batch_alter_table("work_orders", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_work_orders_queue_position_requires_production_type", type_="check")
        batch_op.create_check_constraint(
            "ck_work_orders_planned_requires_production_type_and_queue_position",
            "(production_type IS NULL AND queue_position IS NULL) OR "
            "(production_type IS NOT NULL AND queue_position IS NOT NULL)",
        )
