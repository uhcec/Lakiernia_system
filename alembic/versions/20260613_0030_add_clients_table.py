"""Add clients table for customer registry

Revision ID: 20260613_0030
Revises: 20260605_0029
Create Date: 2026-06-13 09:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260613_0030"
down_revision = "20260605_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("contact_phone", sa.String(length=64), nullable=True),
        sa.Column("nip", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_name", name="uq_clients_company_name"),
    )
    op.create_index("ix_clients_company_name", "clients", ["company_name"])


def downgrade() -> None:
    op.drop_index("ix_clients_company_name", table_name="clients")
    op.drop_table("clients")
