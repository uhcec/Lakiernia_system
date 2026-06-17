"""Add stage_transition_events append-only analytics log

Records every stage status transition with the moment it occurred, so cycle times,
per-stage throughput, queue waits, and bottleneck stats can be derived reliably (unlike
work_order_stage_states, which keeps only the latest updated_at). Rows are append-only.

Revision ID: 20260617_0032
Revises: 20260614_0031
Create Date: 2026-06-17 15:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260617_0032"
down_revision = "20260614_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stage_transition_events",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("work_order_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=True),
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
        sa.Column("counted_quantity", sa.Integer(), nullable=True),
        sa.Column("station_id", sa.String(length=20), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["work_order_id"],
            ["work_orders.id"],
            name=op.f("fk_stage_transition_events_work_order_id_work_orders"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_stage_transition_events_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stage_transition_events")),
    )
    op.create_index(op.f("ix_stage_transition_events_id"), "stage_transition_events", ["id"], unique=False)
    op.create_index(
        "ix_stage_transition_events_work_order_id", "stage_transition_events", ["work_order_id"], unique=False
    )
    op.create_index(
        "ix_stage_transition_events_occurred_at", "stage_transition_events", ["occurred_at"], unique=False
    )
    op.create_index(
        "ix_stage_transition_events_stage_status_occurred",
        "stage_transition_events",
        ["stage", "status", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_stage_transition_events_stage_status_occurred", table_name="stage_transition_events")
    op.drop_index("ix_stage_transition_events_occurred_at", table_name="stage_transition_events")
    op.drop_index("ix_stage_transition_events_work_order_id", table_name="stage_transition_events")
    op.drop_index(op.f("ix_stage_transition_events_id"), table_name="stage_transition_events")
    op.drop_table("stage_transition_events")
