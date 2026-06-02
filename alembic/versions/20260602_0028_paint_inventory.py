"""Add paint inventory tables and work-order paint relation

Revision ID: 20260602_0028
Revises: 20260602_0027
Create Date: 2026-06-02 23:20:00
"""

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


revision = "20260602_0028"
down_revision = "20260602_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paints",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ral_code", sa.String(length=64), nullable=False),
        sa.Column("paint_producer", sa.String(length=255), nullable=False),
        sa.Column("paint_code", sa.String(length=64), nullable=False),
        sa.Column("current_quantity_kg", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("current_quantity_kg >= 0", name="ck_paints_current_quantity_non_negative"),
        sa.UniqueConstraint("ral_code", "paint_producer", "paint_code", name="uq_paints_identity"),
    )
    op.create_index("ix_paints_ral_code", "paints", ["ral_code"])
    op.create_index("ix_paints_paint_producer", "paints", ["paint_producer"])
    op.create_index("ix_paints_paint_code", "paints", ["paint_code"])

    op.create_table(
        "paint_stock_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("paint_id", sa.Integer(), nullable=False),
        sa.Column("work_order_id", sa.Integer(), nullable=True),
        sa.Column(
            "movement_type",
            sa.Enum(
                "OPENING_BALANCE",
                "DELIVERY",
                "AUTOMATIC_CONSUMPTION",
                "MANUAL_ADJUSTMENT",
                name="paint_stock_movement_type",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("quantity_delta_kg", sa.Float(), nullable=False),
        sa.Column("resulting_quantity_kg", sa.Float(), nullable=False),
        sa.Column("movement_date", sa.Date(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity_delta_kg != 0", name="ck_paint_stock_movements_quantity_delta_non_zero"),
        sa.CheckConstraint("resulting_quantity_kg >= 0", name="ck_paint_stock_movements_resulting_quantity_non_negative"),
        sa.ForeignKeyConstraint(["paint_id"], ["paints.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_paint_stock_movements_paint_id", "paint_stock_movements", ["paint_id"])
    op.create_index("ix_paint_stock_movements_movement_type", "paint_stock_movements", ["movement_type"])
    op.create_index("ix_paint_stock_movements_movement_date", "paint_stock_movements", ["movement_date"])
    op.create_index("ix_paint_stock_movements_work_order_id", "paint_stock_movements", ["work_order_id"])

    with op.batch_alter_table("work_orders", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_work_orders_paint_stock_snapshot_quantity_positive_if_present", type_="check")
        batch_op.add_column(sa.Column("paint_id", sa.Integer(), nullable=True))
        batch_op.create_check_constraint(
            "ck_work_orders_paint_stock_snapshot_quantity_positive_if_present",
            "paint_stock_snapshot_quantity_kg IS NULL OR paint_stock_snapshot_quantity_kg >= 0",
        )
        batch_op.create_foreign_key("fk_work_orders_paint_id_paints", "paints", ["paint_id"], ["id"], ondelete="SET NULL")
        batch_op.create_index("ix_work_orders_paint_id", ["paint_id"])

    connection = op.get_bind()
    now = datetime.now(UTC)
    work_order_rows = connection.execute(
        sa.text(
            """
            SELECT id, ral_code, paint_producer, paint_code, paint_stock_snapshot_quantity_kg
            FROM work_orders
            WHERE paint_code IS NOT NULL AND paint_code != ''
              AND paint_producer IS NOT NULL AND paint_producer != ''
              AND ral_code IS NOT NULL AND ral_code != ''
            ORDER BY id DESC
            """
        )
    ).mappings()

    latest_snapshot_by_identity: dict[tuple[str, str, str], float] = {}
    for row in work_order_rows:
        key = (row["ral_code"], row["paint_producer"], row["paint_code"])
        if key in latest_snapshot_by_identity:
            continue
        latest_snapshot_by_identity[key] = float(row["paint_stock_snapshot_quantity_kg"] or 0)

    paint_identity_to_id: dict[tuple[str, str, str], int] = {}
    movement_date = now.date()
    for identity, current_quantity in latest_snapshot_by_identity.items():
        ral_code, paint_producer, paint_code = identity
        result = connection.execute(
            sa.text(
                """
                INSERT INTO paints (ral_code, paint_producer, paint_code, current_quantity_kg, created_at, updated_at)
                VALUES (:ral_code, :paint_producer, :paint_code, :current_quantity_kg, :created_at, :updated_at)
                """
            ),
            {
                "ral_code": ral_code,
                "paint_producer": paint_producer,
                "paint_code": paint_code,
                "current_quantity_kg": current_quantity,
                "created_at": now,
                "updated_at": now,
            },
        )
        paint_id = result.lastrowid
        paint_identity_to_id[identity] = paint_id

        if current_quantity > 0:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO paint_stock_movements (
                        paint_id,
                        work_order_id,
                        movement_type,
                        quantity_delta_kg,
                        resulting_quantity_kg,
                        movement_date,
                        note,
                        created_at
                    ) VALUES (
                        :paint_id,
                        NULL,
                        :movement_type,
                        :quantity_delta_kg,
                        :resulting_quantity_kg,
                        :movement_date,
                        :note,
                        :created_at
                    )
                    """
                ),
                {
                    "paint_id": paint_id,
                    "movement_type": "OPENING_BALANCE",
                    "quantity_delta_kg": current_quantity,
                    "resulting_quantity_kg": current_quantity,
                    "movement_date": movement_date,
                    "note": "Migrated from latest work-order stock snapshot.",
                    "created_at": now,
                },
            )

    for identity, paint_id in paint_identity_to_id.items():
        ral_code, paint_producer, paint_code = identity
        connection.execute(
            sa.text(
                """
                UPDATE work_orders
                SET paint_id = :paint_id
                WHERE ral_code = :ral_code
                  AND paint_producer = :paint_producer
                  AND paint_code = :paint_code
                """
            ),
            {
                "paint_id": paint_id,
                "ral_code": ral_code,
                "paint_producer": paint_producer,
                "paint_code": paint_code,
            },
        )


def downgrade() -> None:
    with op.batch_alter_table("work_orders", recreate="always") as batch_op:
        batch_op.drop_constraint("fk_work_orders_paint_id_paints", type_="foreignkey")
        batch_op.drop_index("ix_work_orders_paint_id")
        batch_op.drop_column("paint_id")

    op.drop_index("ix_paint_stock_movements_work_order_id", table_name="paint_stock_movements")
    op.drop_index("ix_paint_stock_movements_movement_date", table_name="paint_stock_movements")
    op.drop_index("ix_paint_stock_movements_movement_type", table_name="paint_stock_movements")
    op.drop_index("ix_paint_stock_movements_paint_id", table_name="paint_stock_movements")
    op.drop_table("paint_stock_movements")

    op.drop_index("ix_paints_paint_code", table_name="paints")
    op.drop_index("ix_paints_paint_producer", table_name="paints")
    op.drop_index("ix_paints_ral_code", table_name="paints")
    op.drop_table("paints")