"""Keep incomplete work orders out of planned queues

Revision ID: 20260529_0018
Revises: 20260529_0017
Create Date: 2026-05-29 14:40:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260529_0018"
down_revision = "20260529_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    _assert_no_planned_incomplete_orders(connection)

    with op.batch_alter_table("work_orders", recreate="always") as batch_op:
        batch_op.create_check_constraint(
            "ck_work_orders_incomplete_requires_unplanned",
            "queue_position IS NULL OR (is_incomplete_on_arrival = 0 AND status != 'INCOMPLETE')",
        )


def downgrade() -> None:
    with op.batch_alter_table("work_orders", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_work_orders_incomplete_requires_unplanned", type_="check")


def _assert_no_planned_incomplete_orders(connection) -> None:
    _assert_clean(
        connection,
        """
        SELECT id
        FROM work_orders
        WHERE queue_position IS NOT NULL
          AND (is_incomplete_on_arrival = 1 OR status = 'INCOMPLETE')
        LIMIT 1
        """,
        "incomplete work orders must remain unplanned",
        "work_order_id",
    )


def _assert_clean(connection, query: str, invariant_label: str, id_label: str) -> None:
    row = connection.execute(sa.text(query)).fetchone()
    if row is None:
        return

    violating_id = row[0]
    raise RuntimeError(
        f"Cannot apply migration {revision}: dirty data violates {invariant_label}. "
        f"Example {id_label}={violating_id}. Clean the data before upgrading."
    )