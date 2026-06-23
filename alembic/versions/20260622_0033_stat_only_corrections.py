"""Add stat_only_corrections table (NA34)

Records a "fixed on the spot" (od razu poprawiona) packing correction as a pure statistic: the
pieces were corrected immediately and the order completes as-is, so this is neither a CORRECTION
batch nor a child work order. The shared correction-event source unions it in so the reason report
and throughput counters count it alongside replan/child corrections.

Revision ID: 20260622_0033
Revises: 491d1bfa0b62
Create Date: 2026-06-22 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260622_0033"
down_revision = "491d1bfa0b62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stat_only_corrections",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("work_order_id", sa.Integer(), nullable=False),
        sa.Column("correction_quantity", sa.Integer(), nullable=False),
        sa.Column("correction_reason_category", sa.Text(), nullable=False),
        sa.Column("correction_reason_note", sa.Text(), nullable=True),
        sa.Column("correction_profiles_quantity", sa.Integer(), nullable=True),
        sa.Column("correction_accessories_quantity", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("correction_quantity > 0", name="stat_only_correction_quantity_positive"),
        sa.ForeignKeyConstraint(
            ["work_order_id"],
            ["work_orders.id"],
            name=op.f("fk_stat_only_corrections_work_order_id_work_orders"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stat_only_corrections")),
    )
    op.create_index(op.f("ix_stat_only_corrections_id"), "stat_only_corrections", ["id"], unique=False)
    op.create_index(
        "ix_stat_only_corrections_work_order_id", "stat_only_corrections", ["work_order_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_stat_only_corrections_work_order_id", table_name="stat_only_corrections")
    op.drop_index(op.f("ix_stat_only_corrections_id"), table_name="stat_only_corrections")
    op.drop_table("stat_only_corrections")
