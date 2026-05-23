"""Initial work orders foundation

Revision ID: 20260523_0001
Revises:
Create Date: 2026-05-23 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260523_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "work_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_number", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("customer_name", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            sa.Enum("ENTERED", "ASSIGNED", "IN_PROGRESS", "FINISHED", name="work_order_status", native_enum=False),
            nullable=False,
        ),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_work_orders")),
        sa.UniqueConstraint("order_number", name=op.f("uq_work_orders_order_number")),
    )
    op.create_index(op.f("ix_work_orders_id"), "work_orders", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_work_orders_id"), table_name="work_orders")
    op.drop_table("work_orders")