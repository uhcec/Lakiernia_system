from datetime import UTC, date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.shared.enums import PaintStockMovementType


paint_stock_movement_type_enum = Enum(
    PaintStockMovementType,
    name="paint_stock_movement_type",
    native_enum=False,
    values_callable=lambda movement_types: [movement_type.value for movement_type in movement_types],
)


class Paint(Base):
    __tablename__ = "paints"
    __table_args__ = (
        UniqueConstraint("ral_code", "paint_producer", "paint_code", name="uq_paints_identity"),
        CheckConstraint("current_quantity_kg >= 0", name="current_quantity_non_negative"),
        Index("ix_paints_ral_code", "ral_code"),
        Index("ix_paints_paint_producer", "paint_producer"),
        Index("ix_paints_paint_code", "paint_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ral_code: Mapped[str] = mapped_column(String(64), nullable=False)
    paint_producer: Mapped[str] = mapped_column(String(255), nullable=False)
    paint_code: Mapped[str] = mapped_column(String(64), nullable=False)
    current_quantity_kg: Mapped[float] = mapped_column(Float(), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    stock_movements = relationship(
        "PaintStockMovement",
        back_populates="paint",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PaintStockMovement.created_at.desc()",
    )
    work_orders = relationship("WorkOrder", back_populates="paint")


class PaintStockMovement(Base):
    __tablename__ = "paint_stock_movements"
    __table_args__ = (
        CheckConstraint("quantity_delta_kg != 0", name="quantity_delta_non_zero"),
        CheckConstraint("resulting_quantity_kg >= 0", name="resulting_quantity_non_negative"),
        Index("ix_paint_stock_movements_paint_id", "paint_id"),
        Index("ix_paint_stock_movements_movement_type", "movement_type"),
        Index("ix_paint_stock_movements_movement_date", "movement_date"),
        Index("ix_paint_stock_movements_work_order_id", "work_order_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    paint_id: Mapped[int] = mapped_column(ForeignKey("paints.id", ondelete="CASCADE"), nullable=False)
    work_order_id: Mapped[int | None] = mapped_column(ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True)
    movement_type: Mapped[PaintStockMovementType] = mapped_column(paint_stock_movement_type_enum, nullable=False)
    quantity_delta_kg: Mapped[float] = mapped_column(Float(), nullable=False)
    resulting_quantity_kg: Mapped[float] = mapped_column(Float(), nullable=False)
    movement_date: Mapped[date] = mapped_column(Date(), nullable=False, default=lambda: datetime.now(UTC).date())
    note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)

    paint = relationship("Paint", back_populates="stock_movements")