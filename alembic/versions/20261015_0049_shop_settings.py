"""Shop settings: how many orders may hang at once (CHANGES #29)

Owner decision 2026-10-15: a small order takes only part of a beam, so the hanging station must be able
to start the next order next to it. The limit is a setting the manager calibrates from the "Ustawienia"
tab. No row = default 1 (the old fixed rule), so nothing changes until the manager raises it.

Revision ID: 20261015_0049
Revises: 20261015_0048
Create Date: 2026-10-15 16:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20261015_0049"
down_revision = "20261015_0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shop_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("hanging_max_active_orders", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_shop_settings_single_row")),
        sa.CheckConstraint(
            "hanging_max_active_orders >= 1",
            name=op.f("ck_shop_settings_hanging_max_active_orders_positive"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shop_settings")),
    )


def downgrade() -> None:
    op.drop_table("shop_settings")
