"""Add work_orders.planning_priority (manager pin/urgent planning lock, NA49.K)

Revision ID: 20260624_0040
Revises: 20260624_0039
Create Date: 2026-06-24 18:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260624_0040"
down_revision = "20260624_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.add_column(
            sa.Column(
                "planning_priority",
                sa.Enum("PINNED", "URGENT", name="planning_priority", native_enum=False),
                nullable=True,
            )
        )
        batch_op.create_check_constraint(
            "planning_priority_requires_planned",
            "planning_priority IS NULL OR queue_position IS NOT NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.drop_constraint("planning_priority_requires_planned", type_="check")
        batch_op.drop_column("planning_priority")
