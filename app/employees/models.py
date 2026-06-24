from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.shared.enums import StationId
from app.shared import clock


_presence_station_id_enum = Enum(
    StationId,
    name="presence_station_id",
    native_enum=False,
    values_callable=lambda station_ids: [station_id.value for station_id in station_ids],
)


class Employee(Base):
    """A factory worker on the station presence roster. Distinct from `users` (login accounts):
    employees do not authenticate; they are checked in/out at stations and attribute actions."""

    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: clock.now(), nullable=False
    )


class StationPresence(Base):
    """Append-only check-in/out log. An employee is "currently present" at a station while a row
    with that ``station_id`` + ``employee_id`` has ``checked_out_at IS NULL``."""

    __tablename__ = "station_presence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    station_id: Mapped[StationId] = mapped_column(_presence_station_id_enum, nullable=False, index=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    checked_in_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: clock.now(), nullable=False
    )
    checked_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    employee: Mapped[Employee] = relationship("Employee", lazy="joined")
