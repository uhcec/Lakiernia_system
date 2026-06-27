"""Add work-order kind and Ocynk marker

Revision ID: 20260531_0022
Revises: 20260530_0021
Create Date: 2026-05-31 15:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260531_0022"
down_revision = "20260530_0021"
branch_labels = None
depends_on = None

work_order_kind_enum = sa.Enum(
    "STANDARD",
    "PRZEMALOWANKA",
    name="work_order_kind",
    native_enum=False,
)


def upgrade() -> None:
    op.add_column(
        "work_orders",
        sa.Column(
            "work_order_kind",
            work_order_kind_enum,
            nullable=False,
            server_default="STANDARD",
        ),
    )
    op.add_column(
        "work_orders",
        sa.Column(
            "is_ocynk",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.alter_column("work_order_kind", server_default=None)
        batch_op.alter_column("is_ocynk", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.drop_column("is_ocynk")
        batch_op.drop_column("work_order_kind")
