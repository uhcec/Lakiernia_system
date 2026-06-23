"""Per-line queue position uniqueness (MANUAL / AUTOMATIC numbered independently)

Revision ID: 20260620_0033
Revises: 491d1bfa0b62
Create Date: 2026-06-20 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260620_0033"
down_revision = "491d1bfa0b62"
branch_labels = None
depends_on = None


def _renumber_per_line(connection) -> None:
    """Renumber planned orders so each production_type gets a fresh 1..N sequence."""
    rows = connection.execute(
        sa.text(
            """
            SELECT id, production_type
            FROM work_orders
            WHERE queue_position IS NOT NULL AND production_type IS NOT NULL
            ORDER BY production_type ASC, queue_position ASC, id ASC
            """
        )
    ).fetchall()

    next_position: dict[str, int] = {}
    # Park every row at a high temporary position first so the renumbering cannot collide
    # with positions that are still occupied under the about-to-change unique index.
    temporary = 1000000
    for row in rows:
        connection.execute(
            sa.text("UPDATE work_orders SET queue_position = :pos WHERE id = :id"),
            {"pos": temporary, "id": row.id},
        )
        temporary += 1

    for row in rows:
        line = row.production_type
        position = next_position.get(line, 0) + 1
        next_position[line] = position
        connection.execute(
            sa.text("UPDATE work_orders SET queue_position = :pos WHERE id = :id"),
            {"pos": position, "id": row.id},
        )


def upgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS uq_work_orders_queue_position"))

    _renumber_per_line(op.get_bind())

    op.create_index(
        "uq_work_orders_line_queue_position",
        "work_orders",
        ["production_type", "queue_position"],
        unique=True,
        sqlite_where=sa.text("queue_position IS NOT NULL"),
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS uq_work_orders_line_queue_position"))

    # Collapse the two per-line sequences back into a single global sequence.
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT id
            FROM work_orders
            WHERE queue_position IS NOT NULL
            ORDER BY queue_position ASC, production_type ASC, id ASC
            """
        )
    ).fetchall()

    temporary = 1000000
    for row in rows:
        connection.execute(
            sa.text("UPDATE work_orders SET queue_position = :pos WHERE id = :id"),
            {"pos": temporary, "id": row.id},
        )
        temporary += 1

    next_position = 0
    for row in rows:
        next_position += 1
        connection.execute(
            sa.text("UPDATE work_orders SET queue_position = :pos WHERE id = :id"),
            {"pos": next_position, "id": row.id},
        )

    op.create_index(
        "uq_work_orders_queue_position",
        "work_orders",
        ["queue_position"],
        unique=True,
        sqlite_where=sa.text("queue_position IS NOT NULL"),
    )
