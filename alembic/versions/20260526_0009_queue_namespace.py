"""Add queue namespace for main and corrections flows

Revision ID: 20260526_0009
Revises: 20260525_0008
Create Date: 2026-05-26 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260526_0009"
down_revision = "20260525_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "work_orders",
        sa.Column(
            "queue_namespace",
            sa.Enum("MAIN", "CORRECTIONS", name="queue_namespace", native_enum=False),
            nullable=False,
            server_default="MAIN",
        ),
    )

    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE work_orders
            SET queue_namespace = CASE
                WHEN is_correction = 1 THEN 'CORRECTIONS'
                ELSE 'MAIN'
            END
            """
        )
    )

    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.alter_column(
            "queue_namespace",
            existing_type=sa.Enum("MAIN", "CORRECTIONS", name="queue_namespace", native_enum=False),
            server_default=None,
        )

    op.create_index(op.f("ix_work_orders_queue_namespace"), "work_orders", ["queue_namespace"], unique=False)
    op.create_index(
        "uq_work_orders_namespace_queue_position",
        "work_orders",
        ["queue_namespace", "queue_position"],
        unique=True,
        sqlite_where=sa.text("queue_position IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_work_orders_namespace_queue_position", table_name="work_orders")
    op.drop_index(op.f("ix_work_orders_queue_namespace"), table_name="work_orders")
    op.drop_column("work_orders", "queue_namespace")
