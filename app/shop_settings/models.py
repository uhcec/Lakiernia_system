from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.shared import clock


class ShopSettings(Base):
    """Shop-floor parameters the manager calibrates from the "Ustawienia" tab (CHANGES #29).

    A single row (id = 1). A missing row means every setting is at its default — today's behaviour.
    """

    __tablename__ = "shop_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="single_row"),
        CheckConstraint("hanging_max_active_orders >= 1", name="hanging_max_active_orders_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # How many orders may be "w trakcie" at the hanging station at once (owner 2026-10-15: a small order
    # takes part of a beam and the next one is hung next to it).
    hanging_max_active_orders: Mapped[int] = mapped_column(Integer(), nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: clock.now(),
        onupdate=lambda: clock.now(),
        nullable=False,
    )
