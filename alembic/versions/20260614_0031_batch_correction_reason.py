"""Store correction reason/category on correction quantity batches

Revision ID: 20260614_0031
Revises: 20260613_0030
Create Date: 2026-06-14 09:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260614_0031"
down_revision = "20260613_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "work_order_quantity_batches",
        sa.Column("correction_reason_category", sa.Text(), nullable=True),
    )
    op.add_column(
        "work_order_quantity_batches",
        sa.Column("correction_reason_note", sa.Text(), nullable=True),
    )

    # Backfill correction batches from the legacy work-order-level reason fields so existing
    # correction statistics keep aggregating after the unified correction model.
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE work_order_quantity_batches
            SET correction_reason_category = (
                    SELECT wo.correction_reason_category
                    FROM work_orders AS wo
                    WHERE wo.id = work_order_quantity_batches.work_order_id
                ),
                correction_reason_note = (
                    SELECT wo.correction_reason_note
                    FROM work_orders AS wo
                    WHERE wo.id = work_order_quantity_batches.work_order_id
                )
            WHERE work_order_quantity_batches.type = 'CORRECTION'
            """
        )
    )


def downgrade() -> None:
    op.drop_column("work_order_quantity_batches", "correction_reason_note")
    op.drop_column("work_order_quantity_batches", "correction_reason_category")
