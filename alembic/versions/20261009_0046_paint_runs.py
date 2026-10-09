"""Paint runs: automatic paint consumption recorded once per same-paint run (CHANGES #22)

Consumption on the automatic line used to be entered per work order and gated packing completion.
The operator cannot weigh paint per order (cartons are not swapped between orders of the same paint),
so it is now entered once per *paint run* — consecutively hung orders sharing one paint — and split
onto the member orders by m². The per-order gate column ``work_orders.consumed_paint_quantity_kg`` is
dropped; an order's kg is now the sum of its run-member shares.

Owner decision 2026-10-09: existing data is test data, so old per-order consumption is not migrated
(the stock movements already written stay as history).

Revision ID: 20261009_0046
Revises: 20260711_0045
Create Date: 2026-10-09 12:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20261009_0046"
down_revision = "20260711_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paint_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("paint_id", sa.Integer(), nullable=False),
        sa.Column("consumed_kg", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(closed_at IS NULL AND consumed_kg IS NULL) OR (closed_at IS NOT NULL AND consumed_kg > 0)",
            name=op.f("ck_paint_runs_closed_run_has_positive_consumption"),
        ),
        sa.ForeignKeyConstraint(
            ["paint_id"], ["paints.id"], name=op.f("fk_paint_runs_paint_id_paints"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_paint_runs")),
    )
    op.create_index("ix_paint_runs_closed_at", "paint_runs", ["closed_at"], unique=False)
    op.create_index(op.f("ix_paint_runs_paint_id"), "paint_runs", ["paint_id"], unique=False)

    op.create_table(
        "paint_run_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("paint_run_id", sa.Integer(), nullable=False),
        sa.Column("work_order_id", sa.Integer(), nullable=False),
        sa.Column("area_m2", sa.Float(), nullable=False),
        sa.Column("allocated_kg", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("area_m2 >= 0", name=op.f("ck_paint_run_members_area_non_negative")),
        sa.CheckConstraint(
            "allocated_kg IS NULL OR allocated_kg >= 0",
            name=op.f("ck_paint_run_members_allocated_kg_non_negative_if_present"),
        ),
        sa.ForeignKeyConstraint(
            ["paint_run_id"],
            ["paint_runs.id"],
            name=op.f("fk_paint_run_members_paint_run_id_paint_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["work_order_id"],
            ["work_orders.id"],
            name=op.f("fk_paint_run_members_work_order_id_work_orders"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_paint_run_members")),
        sa.UniqueConstraint("paint_run_id", "work_order_id", name="uq_paint_run_members_run_work_order"),
    )
    op.create_index("ix_paint_run_members_work_order_id", "paint_run_members", ["work_order_id"], unique=False)

    with op.batch_alter_table("paint_stock_movements", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("paint_run_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_paint_stock_movements_paint_run_id_paint_runs"),
            "paint_runs",
            ["paint_run_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(batch_op.f("ix_paint_stock_movements_paint_run_id"), ["paint_run_id"], unique=False)

    with op.batch_alter_table("work_orders", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_work_orders_consumed_paint_quantity_non_negative", type_="check")
        batch_op.drop_column("consumed_paint_quantity_kg")


def downgrade() -> None:
    with op.batch_alter_table("work_orders", recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column("consumed_paint_quantity_kg", sa.Float(), nullable=False, server_default="0")
        )
        batch_op.create_check_constraint(
            "ck_work_orders_consumed_paint_quantity_non_negative",
            "consumed_paint_quantity_kg >= 0",
        )

    with op.batch_alter_table("paint_stock_movements", recreate="always") as batch_op:
        batch_op.drop_index(batch_op.f("ix_paint_stock_movements_paint_run_id"))
        batch_op.drop_constraint(batch_op.f("fk_paint_stock_movements_paint_run_id_paint_runs"), type_="foreignkey")
        batch_op.drop_column("paint_run_id")

    op.drop_index("ix_paint_run_members_work_order_id", table_name="paint_run_members")
    op.drop_table("paint_run_members")
    op.drop_index(op.f("ix_paint_runs_paint_id"), table_name="paint_runs")
    op.drop_index("ix_paint_runs_closed_at", table_name="paint_runs")
    op.drop_table("paint_runs")
