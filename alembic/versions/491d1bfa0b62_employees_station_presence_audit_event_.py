"""employees, station presence, audit event actors

Revision ID: 491d1bfa0b62
Revises: 20260617_0032
Create Date: 2026-06-18 00:34:01.185015
"""

from alembic import op
import sqlalchemy as sa

from app.shared.enums import StationId


# revision identifiers, used by Alembic.
revision = '491d1bfa0b62'
down_revision = '20260617_0032'
branch_labels = None
depends_on = None


_presence_station_id = sa.Enum(
    StationId,
    name="presence_station_id",
    native_enum=False,
    values_callable=lambda station_ids: [station_id.value for station_id in station_ids],
)


def upgrade() -> None:
    op.create_table(
        "employees",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "station_presence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("station_id", _presence_station_id, nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checked_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_station_presence_employee_id", "station_presence", ["employee_id"])
    op.create_index("ix_station_presence_station_id", "station_presence", ["station_id"])
    op.create_table(
        "audit_event_actors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("audit_event_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=True),
        sa.Column("employee_name", sa.String(length=120), nullable=False),
        sa.ForeignKeyConstraint(["audit_event_id"], ["audit_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_event_actors_audit_event_id", "audit_event_actors", ["audit_event_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_event_actors_audit_event_id", table_name="audit_event_actors")
    op.drop_table("audit_event_actors")
    op.drop_index("ix_station_presence_station_id", table_name="station_presence")
    op.drop_index("ix_station_presence_employee_id", table_name="station_presence")
    op.drop_table("station_presence")
    op.drop_table("employees")
