"""Parked packing of a paint run's last order (CHANGES #23)

Owner decision 2026-10-09: the last order of an open paint run does not complete packing until the
run's paint consumption is entered. The operator's submitted packing numbers are kept on the run member
(JSON) and the system completes the packing right after the consumption entry.

Revision ID: 20261009_0047
Revises: 20261009_0046
Create Date: 2026-10-09 16:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20261009_0047"
down_revision = "20261009_0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("paint_run_members") as batch_op:
        batch_op.add_column(sa.Column("pending_packing_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("paint_run_members") as batch_op:
        batch_op.drop_column("pending_packing_json")
