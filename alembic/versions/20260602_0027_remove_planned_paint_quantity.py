"""Remove planned paint quantity from work orders

Revision ID: 20260602_0027
Revises: 20260602_0026
Create Date: 2026-06-02 20:45:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260602_0027"
down_revision = "20260602_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("work_orders", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_work_orders_planned_paint_quantity_positive_if_present", type_="check")
        batch_op.drop_column("planned_paint_quantity_kg")


def downgrade() -> None:
    with op.batch_alter_table("work_orders", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("planned_paint_quantity_kg", sa.Float(), nullable=True))
        batch_op.create_check_constraint(
            "ck_work_orders_planned_paint_quantity_positive_if_present",
            "planned_paint_quantity_kg IS NULL OR planned_paint_quantity_kg > 0",
        )