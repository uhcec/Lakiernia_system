"""Add per-work-order paint tracking

Revision ID: 20260602_0025
Revises: 20260531_0024
Create Date: 2026-06-02 12:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260602_0025"
down_revision = "20260531_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("work_orders", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("paint_code", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("planned_paint_quantity_kg", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "consumed_paint_quantity_kg",
                sa.Float(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.create_check_constraint(
            "ck_work_orders_planned_paint_quantity_positive_if_present",
            "planned_paint_quantity_kg IS NULL OR planned_paint_quantity_kg > 0",
        )
        batch_op.create_check_constraint(
            "ck_work_orders_consumed_paint_quantity_non_negative",
            "consumed_paint_quantity_kg >= 0",
        )
        batch_op.create_check_constraint(
            "ck_work_orders_paint_consumption_requires_planned_quantity",
            "planned_paint_quantity_kg IS NOT NULL OR consumed_paint_quantity_kg = 0",
        )
        batch_op.create_check_constraint(
            "ck_work_orders_consumed_paint_quantity_lte_planned_if_known",
            "planned_paint_quantity_kg IS NULL OR consumed_paint_quantity_kg <= planned_paint_quantity_kg",
        )


def downgrade() -> None:
    with op.batch_alter_table("work_orders", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_work_orders_consumed_paint_quantity_lte_planned_if_known", type_="check")
        batch_op.drop_constraint("ck_work_orders_paint_consumption_requires_planned_quantity", type_="check")
        batch_op.drop_constraint("ck_work_orders_consumed_paint_quantity_non_negative", type_="check")
        batch_op.drop_constraint("ck_work_orders_planned_paint_quantity_positive_if_present", type_="check")
        batch_op.drop_column("consumed_paint_quantity_kg")
        batch_op.drop_column("planned_paint_quantity_kg")
        batch_op.drop_column("paint_code")
