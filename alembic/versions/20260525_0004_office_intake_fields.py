"""Add office intake fields to work orders

Revision ID: 20260525_0004
Revises: 20260525_0003
Create Date: 2026-05-25 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260525_0004"
down_revision = "20260525_0003"
branch_labels = None
depends_on = None


work_orders_table = sa.table(
    "work_orders",
    sa.column("id", sa.Integer()),
    sa.column("customer_name", sa.String()),
    sa.column("ral_code", sa.String()),
    sa.column("paint_producer", sa.String()),
    sa.column("received_date", sa.Date()),
    sa.column("profiles_to_count", sa.Boolean()),
    sa.column("accessories_to_count", sa.Boolean()),
)


def upgrade() -> None:
    op.add_column("work_orders", sa.Column("ral_code", sa.String(length=64), nullable=True))
    op.add_column("work_orders", sa.Column("paint_producer", sa.String(length=255), nullable=True))
    op.add_column("work_orders", sa.Column("received_date", sa.Date(), nullable=True))
    op.add_column("work_orders", sa.Column("planned_pickup_date", sa.Date(), nullable=True))
    op.add_column("work_orders", sa.Column("total_area_m2", sa.Float(), nullable=True))
    op.add_column("work_orders", sa.Column("profiles_quantity", sa.Integer(), nullable=True))
    op.add_column("work_orders", sa.Column("profiles_to_count", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("work_orders", sa.Column("accessories_quantity", sa.Integer(), nullable=True))
    op.add_column("work_orders", sa.Column("accessories_to_count", sa.Boolean(), nullable=False, server_default=sa.true()))

    connection = op.get_bind()
    connection.execute(
        work_orders_table.update().values(
            customer_name=sa.func.coalesce(work_orders_table.c.customer_name, "Nieuzupełnione"),
            ral_code=sa.func.coalesce(work_orders_table.c.ral_code, "Nieuzupełnione"),
            paint_producer=sa.func.coalesce(work_orders_table.c.paint_producer, "Nieuzupełnione"),
            received_date=sa.func.coalesce(work_orders_table.c.received_date, sa.func.current_date()),
            profiles_to_count=True,
            accessories_to_count=True,
        )
    )

    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.alter_column("customer_name", existing_type=sa.String(length=255), nullable=False)
        batch_op.alter_column("ral_code", existing_type=sa.String(length=64), nullable=False)
        batch_op.alter_column("paint_producer", existing_type=sa.String(length=255), nullable=False)
        batch_op.alter_column("received_date", existing_type=sa.Date(), nullable=False)
        batch_op.alter_column("profiles_to_count", existing_type=sa.Boolean(), server_default=None)
        batch_op.alter_column("accessories_to_count", existing_type=sa.Boolean(), server_default=None)


def downgrade() -> None:
    op.drop_column("work_orders", "accessories_to_count")
    op.drop_column("work_orders", "accessories_quantity")
    op.drop_column("work_orders", "profiles_to_count")
    op.drop_column("work_orders", "profiles_quantity")
    op.drop_column("work_orders", "total_area_m2")
    op.drop_column("work_orders", "planned_pickup_date")
    op.drop_column("work_orders", "received_date")
    op.drop_column("work_orders", "paint_producer")
    op.drop_column("work_orders", "ral_code")