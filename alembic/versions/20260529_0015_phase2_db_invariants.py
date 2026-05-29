"""Add phase 2 database invariants

Revision ID: 20260529_0015
Revises: 20260529_0014
Create Date: 2026-05-29 01:20:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260529_0015"
down_revision = "20260529_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    _assert_no_orphan_corrections(connection)
    _assert_no_multiple_active_batches(connection)
    _assert_no_inactive_batches_without_done_status(connection)

    with op.batch_alter_table("work_orders", recreate="always") as batch_op:
        batch_op.create_check_constraint(
            "ck_work_orders_correction_requires_parent",
            "is_correction = 0 OR parent_order_id IS NOT NULL",
        )

    with op.batch_alter_table("work_order_quantity_batches", recreate="always") as batch_op:
        batch_op.create_check_constraint(
            "ck_work_order_quantity_batches_inactive_batch_requires_done_status",
            "is_active = 1 OR current_stage_status = 'DONE'",
        )

    op.create_index(
        "uq_work_order_quantity_batches_one_active_per_work_order",
        "work_order_quantity_batches",
        ["work_order_id"],
        unique=True,
        sqlite_where=sa.text("is_active = 1"),
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_work_order_quantity_batches_one_active_per_work_order",
        table_name="work_order_quantity_batches",
    )

    with op.batch_alter_table("work_order_quantity_batches", recreate="always") as batch_op:
        batch_op.drop_constraint(
            "ck_work_order_quantity_batches_inactive_batch_requires_done_status",
            type_="check",
        )

    with op.batch_alter_table("work_orders", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_work_orders_correction_requires_parent", type_="check")


def _assert_no_orphan_corrections(connection) -> None:
    _assert_clean(
        connection,
        "SELECT id FROM work_orders WHERE is_correction = 1 AND parent_order_id IS NULL LIMIT 1",
        "correction work orders require parent_order_id",
        "work_order_id",
    )


def _assert_no_multiple_active_batches(connection) -> None:
    _assert_clean(
        connection,
        """
        SELECT work_order_id
        FROM work_order_quantity_batches
        WHERE is_active = 1
        GROUP BY work_order_id
        HAVING COUNT(*) > 1
        LIMIT 1
        """,
        "at most one active quantity batch per work order",
        "work_order_id",
    )


def _assert_no_inactive_batches_without_done_status(connection) -> None:
    _assert_clean(
        connection,
        """
        SELECT id
        FROM work_order_quantity_batches
        WHERE is_active = 0
          AND current_stage_status != 'DONE'
        LIMIT 1
        """,
        "inactive quantity batches require DONE status",
        "batch_id",
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