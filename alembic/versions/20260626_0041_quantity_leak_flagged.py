"""Add work_orders.quantity_leak_flagged (NA19 leak safety net, CHANGES #10)

The finalization safety net forces ``completed_quantity`` to ``total_quantity`` when a
quantity-conservation leak is detected (credited pieces ≠ total at close). Previously this was only
written to the technical log, so no human saw it. This column persists the flag so the leak is
surfaced in the read models for investigation instead of silently auto-completing.

Existing rows are backfilled to 0 (not flagged) via the server default.

Revision ID: 20260626_0041
Revises: 20260624_0040
Create Date: 2026-06-26 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260626_0041"
down_revision = "20260624_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.add_column(
            sa.Column(
                "quantity_leak_flagged",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.drop_column("quantity_leak_flagged")
