"""Declared quantity + discrepancy resolution (CHANGES #24)

Owner decision 2026-10-15: when surface prep counts a different number of pieces than the client
declared, the order shows it ("MNIEJ/WIĘCEJ NIŻ ZGŁOSZONO: 10 z 14") until the office ticks it as
explained. The declared amount is kept on the order once the system redefines total_quantity.

Backfill: orders already redefined by the D5 undercount path recover their declared amount from the
``work_order.total_quantity_redefined`` audit event (the only place it was kept until now).

Revision ID: 20261015_0048
Revises: 20261009_0047
Create Date: 2026-10-15 12:00:00
"""

import json

from alembic import op
import sqlalchemy as sa


revision = "20261015_0048"
down_revision = "20261009_0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.add_column(sa.Column("declared_quantity", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("declared_profiles_quantity", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("declared_accessories_quantity", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("quantity_discrepancy_resolved_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("quantity_discrepancy_resolved_by", sa.String(length=32), nullable=True))

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT work_order_id, details_json FROM audit_events "
            "WHERE event_type = 'work_order.total_quantity_redefined' AND work_order_id IS NOT NULL "
            "ORDER BY id"
        )
    ).fetchall()
    backfilled: set[int] = set()
    for work_order_id, details_json in rows:
        if work_order_id in backfilled:
            continue  # the first redefinition holds what the client declared
        details = json.loads(details_json or "{}")
        ordered_quantity = details.get("ordered_quantity")
        if ordered_quantity is None:
            continue
        connection.execute(
            sa.text(
                "UPDATE work_orders SET declared_quantity = :declared, "
                "declared_profiles_quantity = :profiles, declared_accessories_quantity = :accessories "
                "WHERE id = :work_order_id"
            ),
            {
                "declared": ordered_quantity,
                "profiles": details.get("ordered_profiles_quantity"),
                "accessories": details.get("ordered_accessories_quantity"),
                "work_order_id": work_order_id,
            },
        )
        backfilled.add(work_order_id)


def downgrade() -> None:
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.drop_column("quantity_discrepancy_resolved_by")
        batch_op.drop_column("quantity_discrepancy_resolved_at")
        batch_op.drop_column("declared_accessories_quantity")
        batch_op.drop_column("declared_profiles_quantity")
        batch_op.drop_column("declared_quantity")
