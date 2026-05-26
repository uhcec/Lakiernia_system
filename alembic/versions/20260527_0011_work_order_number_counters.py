"""Add DB-owned work order number counters

Revision ID: 20260527_0011
Revises: 20260526_0010
Create Date: 2026-05-27 00:00:00
"""

from datetime import UTC, datetime
import re

from alembic import op
import sqlalchemy as sa


revision = "20260527_0011"
down_revision = "20260526_0010"
branch_labels = None
depends_on = None


ORDER_NUMBER_PATTERN = re.compile(r"^WO-(\d{4})-(\d+)$")


def upgrade() -> None:
    op.create_table(
        "work_order_number_counters",
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("last_value", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("year", name=op.f("pk_work_order_number_counters")),
    )

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT order_number FROM work_orders")).fetchall()

    counters_by_year: dict[int, int] = {}
    for row in rows:
        order_number = row.order_number
        if not isinstance(order_number, str):
            continue

        match = ORDER_NUMBER_PATTERN.match(order_number)
        if match is None:
            continue

        year = int(match.group(1))
        sequence = int(match.group(2))
        counters_by_year[year] = max(counters_by_year.get(year, 0), sequence)

    if counters_by_year:
        now = datetime.now(UTC)
        counter_table = sa.table(
            "work_order_number_counters",
            sa.column("year", sa.Integer()),
            sa.column("last_value", sa.Integer()),
            sa.column("created_at", sa.DateTime(timezone=True)),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        )
        op.bulk_insert(
            counter_table,
            [
                {
                    "year": year,
                    "last_value": last_value,
                    "created_at": now,
                    "updated_at": now,
                }
                for year, last_value in sorted(counters_by_year.items())
            ],
        )


def downgrade() -> None:
    op.drop_table("work_order_number_counters")