"""Add quantity batches for work orders

Revision ID: 20260524_0002
Revises: 20260523_0001
Create Date: 2026-05-24 00:00:00
"""

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


revision = "20260524_0002"
down_revision = "20260523_0001"
branch_labels = None
depends_on = None


work_orders_table = sa.table(
    "work_orders",
    sa.column("id", sa.Integer()),
    sa.column("total_quantity", sa.Integer()),
    sa.column("current_active_batch_id", sa.Integer()),
)

work_order_quantity_batches_table = sa.table(
    "work_order_quantity_batches",
    sa.column("id", sa.Integer()),
    sa.column("work_order_id", sa.Integer()),
    sa.column("quantity", sa.Integer()),
    sa.column("type", sa.String()),
    sa.column("parent_batch_id", sa.Integer()),
    sa.column("created_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    op.add_column("work_orders", sa.Column("total_quantity", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("work_orders", sa.Column("completed_quantity", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("work_orders", sa.Column("current_active_batch_id", sa.Integer(), nullable=True))
    op.create_table(
        "work_order_quantity_batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("work_order_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "type",
            sa.Enum("MAIN", "CORRECTION", name="quantity_batch_type", native_enum=False),
            nullable=False,
        ),
        sa.Column("parent_batch_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["parent_batch_id"], ["work_order_quantity_batches.id"], name=op.f("fk_work_order_quantity_batches_parent_batch_id_work_order_quantity_batches"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"], name=op.f("fk_work_order_quantity_batches_work_order_id_work_orders"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_work_order_quantity_batches")),
    )
    op.create_index(op.f("ix_work_order_quantity_batches_id"), "work_order_quantity_batches", ["id"], unique=False)

    connection = op.get_bind()
    rows = connection.execute(sa.select(work_orders_table.c.id, work_orders_table.c.total_quantity)).all()
    created_at = datetime.now(UTC)

    for work_order_id, total_quantity in rows:
        insert_result = connection.execute(
            work_order_quantity_batches_table.insert().values(
                work_order_id=work_order_id,
                quantity=total_quantity,
                type="MAIN",
                parent_batch_id=None,
                created_at=created_at,
            )
        )
        batch_id = insert_result.inserted_primary_key[0] if insert_result.inserted_primary_key else insert_result.lastrowid
        connection.execute(
            work_orders_table.update()
            .where(work_orders_table.c.id == work_order_id)
            .values(current_active_batch_id=batch_id)
        )

    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.alter_column("total_quantity", server_default=None)
        batch_op.alter_column("completed_quantity", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_work_order_quantity_batches_id"), table_name="work_order_quantity_batches")
    op.drop_table("work_order_quantity_batches")
    op.drop_column("work_orders", "current_active_batch_id")
    op.drop_column("work_orders", "completed_quantity")
    op.drop_column("work_orders", "total_quantity")