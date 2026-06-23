from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Foil(Base):
    """Decoral foil registry (lookup table). One foil may be selected per decoral work order at
    intake (NA38). Code is the stable unique identifier; name is the human label."""

    __tablename__ = "foils"
    __table_args__ = (
        UniqueConstraint("code", name="uq_foils_code"),
        Index("ix_foils_name", "name"),
        Index("ix_foils_code", "code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    supplier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    work_orders = relationship("WorkOrder", back_populates="decoral_foil")
