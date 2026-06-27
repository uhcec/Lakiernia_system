"""Add parallel batch tracking fields

Revision ID: 20260525_0003
Revises: 20260524_0002
Create Date: 2026-05-25 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260525_0003"
down_revision = "20260524_0002"
branch_labels = None
depends_on = None


work_orders_table = sa.table(
    "work_orders",
    sa.column("id", sa.Integer()),
    sa.column("current_active_batch_id", sa.Integer()),
)

work_order_stage_states_table = sa.table(
    "work_order_stage_states",
    sa.column("work_order_id", sa.Integer()),
    sa.column("stage", sa.String()),
    sa.column("status", sa.String()),
)

work_order_quantity_batches_table = sa.table(
    "work_order_quantity_batches",
    sa.column("id", sa.Integer()),
    sa.column("work_order_id", sa.Integer()),
    sa.column("is_active", sa.Boolean()),
    sa.column("current_stage", sa.String()),
    sa.column("current_stage_status", sa.String()),
    sa.column("is_partial", sa.Boolean()),
)


def _infer_current_stage(connection, work_order_id: int) -> tuple[str | None, str | None]:
    rows = connection.execute(
        sa.select(
            work_order_stage_states_table.c.stage,
            work_order_stage_states_table.c.status,
        ).where(work_order_stage_states_table.c.work_order_id == work_order_id)
    ).all()
    if not rows:
        return None, None

    stage_order = [
        "SURFACE_PREPARATION",
        "HANGING",
        "PRODUCTION",
        "PACKING",
        "DECORAL_PRODUCTION",
    ]
    statuses = {stage: status for stage, status in rows}
    for stage in stage_order:
        status = statuses.get(stage)
        if status is None:
            continue
        if status != "DONE":
            return stage, status
    return None, None


def upgrade() -> None:
    op.add_column(
        "work_order_quantity_batches",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "work_order_quantity_batches",
        sa.Column(
            "current_stage",
            sa.Enum(
                "SURFACE_PREPARATION",
                "HANGING",
                "PRODUCTION",
                "DECORAL_PRODUCTION",
                "PACKING",
                name="process_stage",
                native_enum=False,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "work_order_quantity_batches",
        sa.Column(
            "current_stage_status",
            sa.Enum("NOT_STARTED", "IN_PROGRESS", "DONE", name="stage_status", native_enum=False),
            nullable=True,
        ),
    )
    op.add_column(
        "work_order_quantity_batches",
        sa.Column("is_partial", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.select(work_orders_table.c.id, work_orders_table.c.current_active_batch_id)
    ).all()

    for work_order_id, current_active_batch_id in rows:
        if current_active_batch_id is None:
            continue
        current_stage, current_stage_status = _infer_current_stage(connection, work_order_id)
        connection.execute(
            work_order_quantity_batches_table.update()
            .where(work_order_quantity_batches_table.c.id == current_active_batch_id)
            .values(
                is_active=True,
                current_stage=current_stage,
                current_stage_status=current_stage_status,
                is_partial=False,
            )
        )
        connection.execute(
            work_order_quantity_batches_table.update()
            .where(work_order_quantity_batches_table.c.work_order_id == work_order_id)
            .where(work_order_quantity_batches_table.c.id != current_active_batch_id)
            .values(is_active=False)
        )

    with op.batch_alter_table("work_order_quantity_batches") as batch_op:
        batch_op.alter_column("is_active", server_default=None)
        batch_op.alter_column("is_partial", server_default=None)


def downgrade() -> None:
    op.drop_column("work_order_quantity_batches", "is_partial")
    op.drop_column("work_order_quantity_batches", "current_stage_status")
    op.drop_column("work_order_quantity_batches", "current_stage")
    op.drop_column("work_order_quantity_batches", "is_active")
