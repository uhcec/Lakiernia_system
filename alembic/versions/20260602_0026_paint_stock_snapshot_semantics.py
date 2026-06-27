"""Add paint stock snapshot semantics

Revision ID: 20260602_0026
Revises: 20260602_0025
Create Date: 2026-06-02 18:20:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260602_0026"
down_revision = "20260602_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("work_orders", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("paint_stock_snapshot_quantity_kg", sa.Float(), nullable=True))
        batch_op.drop_constraint("ck_work_orders_paint_consumption_requires_planned_quantity", type_="check")
        batch_op.drop_constraint("ck_work_orders_consumed_paint_quantity_lte_planned_if_known", type_="check")
        batch_op.create_check_constraint(
            "ck_work_orders_paint_stock_snapshot_quantity_positive_if_present",
            "paint_stock_snapshot_quantity_kg IS NULL OR paint_stock_snapshot_quantity_kg > 0",
        )


def downgrade() -> None:
    with op.batch_alter_table("work_orders", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_work_orders_paint_stock_snapshot_quantity_positive_if_present", type_="check")
        batch_op.create_check_constraint(
            "ck_work_orders_paint_consumption_requires_planned_quantity",
            "planned_paint_quantity_kg IS NOT NULL OR consumed_paint_quantity_kg = 0",
        )
        batch_op.create_check_constraint(
            "ck_work_orders_consumed_paint_quantity_lte_planned_if_known",
            "planned_paint_quantity_kg IS NULL OR consumed_paint_quantity_kg <= planned_paint_quantity_kg",
        )
        batch_op.drop_column("paint_stock_snapshot_quantity_kg")
