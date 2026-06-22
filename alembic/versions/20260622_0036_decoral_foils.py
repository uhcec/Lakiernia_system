"""Add Decoral foil registry + one foil per work order (NA38)

Creates the ``foils`` lookup table and adds a nullable ``decoral_foil_id`` FK on ``work_orders``
(``ON DELETE SET NULL``, like ``paint_id``). A CHECK constraint enforces that a foil can only be set on
a Decoral-coating order. The work_orders change uses a batch rebuild because SQLite cannot add a column
with a new CHECK constraint in place.

Revision ID: 20260622_0036
Revises: 20260622_0035
Create Date: 2026-06-22 16:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260622_0036"
down_revision = "20260622_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "foils",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("supplier", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code", name="uq_foils_code"),
    )
    op.create_index("ix_foils_name", "foils", ["name"])
    op.create_index("ix_foils_code", "foils", ["code"])

    with op.batch_alter_table("work_orders", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("decoral_foil_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_work_orders_decoral_foil_id_foils",
            "foils",
            ["decoral_foil_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_check_constraint(
            "decoral_foil_requires_decoral_coating",
            "decoral_foil_id IS NULL OR coating_type = 'DECORAL'",
        )
        batch_op.create_index("ix_work_orders_decoral_foil_id", ["decoral_foil_id"])


def downgrade() -> None:
    with op.batch_alter_table("work_orders", recreate="always") as batch_op:
        batch_op.drop_index("ix_work_orders_decoral_foil_id")
        batch_op.drop_constraint("decoral_foil_requires_decoral_coating", type_="check")
        batch_op.drop_constraint("fk_work_orders_decoral_foil_id_foils", type_="foreignkey")
        batch_op.drop_column("decoral_foil_id")

    op.drop_index("ix_foils_code", table_name="foils")
    op.drop_index("ix_foils_name", table_name="foils")
    op.drop_table("foils")
