"""Add request IDs to audit events

Revision ID: 20260529_0017
Revises: 20260529_0016
Create Date: 2026-05-29 04:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260529_0017"
down_revision = "20260529_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_events", sa.Column("request_id", sa.String(length=128), nullable=True))
    op.create_index("ix_audit_events_request_id", "audit_events", ["request_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_request_id", table_name="audit_events")
    op.drop_column("audit_events", "request_id")
