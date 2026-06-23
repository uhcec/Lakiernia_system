"""Make planned_pickup_date a required (NOT NULL) deadline (N49-1)

``planned_pickup_date`` IS the hard "Termin odbioru" — owner-confirmed to be always set at intake — but
the column was historically nullable and the schema treated it as optional. The NA49 multi-day capacity
planner needs every active order to carry a hard deadline, so this makes the column NOT NULL.

Legacy rows with a NULL pickup date are backfilled to ``received_date`` (the most conservative value:
an order is treated as due on the day it arrived, so it surfaces as at-risk/overdue rather than being
granted false slack; completed orders are READY and are not flagged overdue regardless).

Revision ID: 20260624_0039
Revises: 20260623_0038
Create Date: 2026-06-24 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260624_0039"
down_revision = "20260623_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE work_orders "
        "SET planned_pickup_date = received_date "
        "WHERE planned_pickup_date IS NULL"
    )
    with op.batch_alter_table("work_orders", recreate="always") as batch_op:
        batch_op.alter_column(
            "planned_pickup_date",
            existing_type=sa.Date(),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("work_orders", recreate="always") as batch_op:
        batch_op.alter_column(
            "planned_pickup_date",
            existing_type=sa.Date(),
            nullable=True,
        )
