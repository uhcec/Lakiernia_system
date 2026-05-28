"""Add durable process resource locks

Revision ID: 20260528_0013
Revises: 20260527_0012
Create Date: 2026-05-28 00:10:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260528_0013"
down_revision = "20260527_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    active_hanging_ids = _active_hanging_work_order_ids(connection)
    active_automatic_ids = _active_automatic_line_work_order_ids(connection)

    _assert_single_holder(active_hanging_ids, "HANGING")
    _assert_single_holder(active_automatic_ids, "AUTOMATIC_LINE")

    op.create_table(
        "process_resource_locks",
        sa.Column("resource_key", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_process_resource_locks_work_order_id",
        "process_resource_locks",
        ["work_order_id"],
    )

    for resource_key, holder_ids in (("HANGING", active_hanging_ids), ("AUTOMATIC_LINE", active_automatic_ids)):
        if holder_ids:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO process_resource_locks (resource_key, work_order_id, created_at, updated_at)
                    VALUES (:resource_key, :work_order_id, :created_at, :updated_at)
                    """
                ),
                {
                    "resource_key": resource_key,
                    "work_order_id": holder_ids[0],
                    "created_at": "2026-05-28T00:10:00+00:00",
                    "updated_at": "2026-05-28T00:10:00+00:00",
                },
            )


def downgrade() -> None:
    op.drop_index("ix_process_resource_locks_work_order_id", table_name="process_resource_locks")
    op.drop_table("process_resource_locks")


def _active_hanging_work_order_ids(connection) -> list[int]:
    rows = connection.execute(
        sa.text(
            """
            SELECT DISTINCT work_order_id
            FROM (
                SELECT work_order_id
                FROM work_order_stage_states
                WHERE stage = 'HANGING' AND status = 'IN_PROGRESS'

                UNION

                SELECT work_order_id
                FROM work_order_quantity_batches
                WHERE is_active = true
                  AND current_stage = 'HANGING'
                  AND current_stage_status = 'IN_PROGRESS'
            ) active_hanging
            ORDER BY work_order_id
            """
        )
    ).fetchall()
    return [int(row[0]) for row in rows]


def _active_automatic_line_work_order_ids(connection) -> list[int]:
    rows = connection.execute(
        sa.text(
            """
            SELECT DISTINCT work_order_id
            FROM (
                SELECT wo.id AS work_order_id
                FROM work_orders wo
                JOIN work_order_stage_states hanging
                  ON hanging.work_order_id = wo.id AND hanging.stage = 'HANGING'
                JOIN work_order_stage_states packing
                  ON packing.work_order_id = wo.id AND packing.stage = 'PACKING'
                WHERE wo.production_type = 'AUTOMATIC'
                  AND hanging.status = 'IN_PROGRESS'
                  AND packing.status != 'DONE'

                UNION

                SELECT wo.id AS work_order_id
                FROM work_orders wo
                JOIN work_order_quantity_batches batch
                  ON batch.work_order_id = wo.id
                WHERE wo.production_type = 'AUTOMATIC'
                  AND batch.is_active = true
                  AND batch.current_stage IN ('HANGING', 'PACKING')
                  AND batch.current_stage_status = 'IN_PROGRESS'
            ) active_automatic
            ORDER BY work_order_id
            """
        )
    ).fetchall()
    return [int(row[0]) for row in rows]


def _assert_single_holder(holder_ids: list[int], resource_key: str) -> None:
    if len(holder_ids) <= 1:
        return

    raise RuntimeError(
        f"Cannot apply migration {revision}: resource {resource_key} is already held by multiple active work orders: {holder_ids}. "
        "Resolve the resource conflict before upgrading."
    )
