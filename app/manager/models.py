from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.shared import clock


class AutoScheduleConfig(Base):
    """Per production line, the manager's configured painting auto-scheduler rule priority (NA33).

    One row per ``production_type`` (its ``ProductionType.value``). ``rules_json`` stores the manager's
    ordered, toggled view of the rule catalog as a JSON array of ``{"key": str, "enabled": bool}`` in
    priority order. The scheduler applies the *enabled* keys in this order; the full catalog (labels,
    descriptions, defaults) lives in ``app.manager.enums``. Absence of a row = the default order."""

    __tablename__ = "auto_schedule_configs"
    __table_args__ = (UniqueConstraint("production_type", name="uq_auto_schedule_configs_production_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    production_type: Mapped[str] = mapped_column(String(32), nullable=False)
    rules_json: Mapped[str] = mapped_column(Text(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: clock.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: clock.now(),
        onupdate=lambda: clock.now(),
        nullable=False,
    )
