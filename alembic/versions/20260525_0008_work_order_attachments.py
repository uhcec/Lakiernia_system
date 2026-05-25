"""add work order attachments

Revision ID: 20260525_0008
Revises: 20260525_0007
Create Date: 2026-05-25 00:08:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260525_0008"
down_revision = "20260525_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "work_order_attachments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("work_order_id", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_path", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("attachment_type", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_work_order_attachments_id"), "work_order_attachments", ["id"], unique=False)
    op.create_index(op.f("ix_work_order_attachments_work_order_id"), "work_order_attachments", ["work_order_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_work_order_attachments_work_order_id"), table_name="work_order_attachments")
    op.drop_index(op.f("ix_work_order_attachments_id"), table_name="work_order_attachments")
    op.drop_table("work_order_attachments")