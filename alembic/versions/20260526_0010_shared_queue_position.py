"""Switch queue position uniqueness to shared namespace

Revision ID: 20260526_0010
Revises: 20260526_0009
Create Date: 2026-05-26 00:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260526_0010"
down_revision = "20260526_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS uq_work_orders_namespace_queue_position"))

    connection = op.get_bind()
    max_queue_position = connection.execute(
        sa.text("SELECT COALESCE(MAX(queue_position), 0) FROM work_orders WHERE queue_position IS NOT NULL")
    ).scalar_one()

    correction_rows = connection.execute(
        sa.text(
            """
            SELECT id
            FROM work_orders
            WHERE is_correction = 1 AND queue_position IS NOT NULL
            ORDER BY queue_position ASC, id ASC
            """
        )
    ).fetchall()

    next_queue_position = int(max_queue_position)
    for row in correction_rows:
        next_queue_position += 1
        connection.execute(
            sa.text("UPDATE work_orders SET queue_position = :queue_position WHERE id = :work_order_id"),
            {"queue_position": next_queue_position, "work_order_id": row.id},
        )

    op.create_index(
        "uq_work_orders_queue_position",
        "work_orders",
        ["queue_position"],
        unique=True,
        sqlite_where=sa.text("queue_position IS NOT NULL"),
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS uq_work_orders_queue_position"))
    op.create_index(
        "uq_work_orders_namespace_queue_position",
        "work_orders",
        ["queue_namespace", "queue_position"],
        unique=True,
        sqlite_where=sa.text("queue_position IS NOT NULL"),
    )
