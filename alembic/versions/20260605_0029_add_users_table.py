"""Add users table for authentication

Revision ID: 20260605_0029
Revises: 20260602_0028
Create Date: 2026-06-05 12:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260605_0029"
down_revision = "20260602_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("login", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("station_id", sa.String(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.create_index("ix_users_login", "users", ["login"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_login", table_name="users")
    op.drop_table("users")
