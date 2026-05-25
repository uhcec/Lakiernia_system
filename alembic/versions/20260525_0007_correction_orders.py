"""Add correction order relations

Revision ID: 20260525_0007
Revises: 20260525_0006
Create Date: 2026-05-25 01:20:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260525_0007"
down_revision = "20260525_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.add_column(sa.Column("parent_order_id", sa.Integer(), nullable=True))

    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.add_column(sa.Column("is_correction", sa.Boolean(), nullable=False, server_default=sa.false()))

    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.create_foreign_key(
            "fk_work_orders_parent_order_id_work_orders",
            "work_orders",
            ["parent_order_id"],
            ["id"],
            ondelete="SET NULL",
        )
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.alter_column("is_correction", existing_type=sa.Boolean(), server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.drop_constraint("fk_work_orders_parent_order_id_work_orders", type_="foreignkey")
        batch_op.drop_column("is_correction")
        batch_op.drop_column("parent_order_id")