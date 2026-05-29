"""Drop legacy work order due date column

Revision ID: 20260529_0014
Revises: 20260528_0013
Create Date: 2026-05-29 00:10:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260529_0014"
down_revision = "20260528_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.drop_column("due_date")


def downgrade() -> None:
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.add_column(sa.Column("due_date", sa.Date(), nullable=True))