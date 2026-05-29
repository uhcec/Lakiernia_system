from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.shared.enums import StationId


station_id_enum = Enum(
    StationId,
    name="station_id",
    native_enum=False,
    values_callable=lambda station_ids: [station_id.value for station_id in station_ids],
)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_event_type", "event_type"),
        Index("ix_audit_events_work_order_id", "work_order_id"),
        Index("ix_audit_events_request_id", "request_id"),
        Index("ix_audit_events_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    station_id: Mapped[StationId] = mapped_column(station_id_enum, default=StationId.UNKNOWN, nullable=False)
    work_order_id: Mapped[int | None] = mapped_column(ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True)
    target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_id: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    summary: Mapped[str] = mapped_column(String(255), nullable=False)
    details_json: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)