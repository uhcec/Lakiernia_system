"""Add wz_number_counters (per-year sequential WZ document numbering)

WZ (wydanie z magazynu) documents are generated on demand and NOT persisted (owner decision
2026-07-11: a WZ is a one-off printout, not a stored register). The only durable state is this
per-year counter, so numbers run "kolejny / rok" (e.g. 12/2026) and reset each January. Reprints
consume the next number; small gaps are accepted.

Revision ID: 20260711_0045
Revises: 20260626_0044
Create Date: 2026-07-11 12:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260711_0045"
down_revision = "20260626_0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wz_number_counters",
        sa.Column("year", sa.Integer(), primary_key=True),
        sa.Column("last_value", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("wz_number_counters")
