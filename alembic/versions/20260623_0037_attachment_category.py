"""Add a structured `category` discriminator to work-order attachments (NA36)

Adds a non-null ``category`` string column to ``work_order_attachments`` so a technical drawing is
distinguishable from any other attachment. Existing rows backfill to ``DOCUMENT`` via the server
default. The value set is enforced at the application layer (WorkOrderAttachmentCategory), so no DB
CHECK constraint is added — consistent with the free-text ``attachment_type`` column it sits beside.

Revision ID: 20260623_0037
Revises: 20260622_0036
Create Date: 2026-06-23 09:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260623_0037"
down_revision = "20260622_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "work_order_attachments",
        sa.Column("category", sa.String(length=32), nullable=False, server_default="DOCUMENT"),
    )


def downgrade() -> None:
    with op.batch_alter_table("work_order_attachments") as batch_op:
        batch_op.drop_column("category")
