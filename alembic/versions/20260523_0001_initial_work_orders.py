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
        sa.Column(
            "coating_type",
            sa.Enum("RAL", "DECORAL", name="coating_type", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "production_type",
            sa.Enum("MANUAL", "AUTOMATIC", name="production_type", native_enum=False),
            nullable=True,
        ),
        sa.Column("queue_position", sa.Integer(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_work_orders")),
        sa.UniqueConstraint("order_number", name=op.f("uq_work_orders_order_number")),
    )
    op.create_index(op.f("ix_work_orders_id"), "work_orders", ["id"], unique=False)
    op.create_index(op.f("ix_work_orders_queue_position"), "work_orders", ["queue_position"], unique=False)
    op.create_table(
        "work_order_stage_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("work_order_id", sa.Integer(), nullable=False),
        sa.Column(
            "stage",
            sa.Enum(
                "SURFACE_PREPARATION",
                "HANGING",
                "PRODUCTION",
                "DECORAL_PRODUCTION",
                "PACKING",
                name="process_stage",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("NOT_STARTED", "IN_PROGRESS", "DONE", name="stage_status", native_enum=False),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"], name=op.f("fk_work_order_stage_states_work_order_id_work_orders"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_work_order_stage_states")),
        sa.UniqueConstraint("work_order_id", "stage", name=op.f("uq_work_order_stage_states_work_order_id")),
    )
    op.create_index(op.f("ix_work_order_stage_states_id"), "work_order_stage_states", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_work_order_stage_states_id"), table_name="work_order_stage_states")
    op.drop_table("work_order_stage_states")
    op.drop_index(op.f("ix_work_orders_queue_position"), table_name="work_orders")
    op.drop_index(op.f("ix_work_orders_id"), table_name="work_orders")
    op.drop_table("work_orders")