"""Add day_shift_lengths (persist the actual shift length run per day, CHANGES #9)

The "good day" measure used to judge every past day against the long-day bar (800 m² / 14 h) because
the shift length actually run that day was not stored. This table persists it (one row per day), so a
day is measured against the shift it was run on. A day with no row falls back to LONG.

Revision ID: 20260626_0044
Revises: 20260626_0043
Create Date: 2026-06-26 03:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260626_0044"
down_revision = "20260626_0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "day_shift_lengths",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("shift_length", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("day", name="uq_day_shift_lengths_day"),
    )
    op.create_index("ix_day_shift_lengths_day", "day_shift_lengths", ["day"])


def downgrade() -> None:
    op.drop_index("ix_day_shift_lengths_day", table_name="day_shift_lengths")
    op.drop_table("day_shift_lengths")
