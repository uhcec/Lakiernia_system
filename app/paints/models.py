from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.shared.enums import PaintStockMovementType
from app.shared import clock


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: clock.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: clock.now(),
        onupdate=lambda: clock.now(),
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
    # Automatic consumption is recorded once per paint run (CHANGES #22), so its movement points at the
    # run rather than at a single work order.
    paint_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("paint_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    movement_type: Mapped[PaintStockMovementType] = mapped_column(paint_stock_movement_type_enum, nullable=False)
    quantity_delta_kg: Mapped[float] = mapped_column(Float(), nullable=False)
    resulting_quantity_kg: Mapped[float] = mapped_column(Float(), nullable=False)
    movement_date: Mapped[date] = mapped_column(Date(), nullable=False, default=lambda: clock.now().date())
    note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: clock.now(), nullable=False)

    paint = relationship("Paint", back_populates="stock_movements")


class PaintRun(Base):
    """A run of consecutively hung automatic-line orders sharing one paint (CHANGES #22).

    The operator cannot weigh paint per order — cartons are not swapped between orders of the same
    paint — so consumption is entered once for the whole run, after its last order finished hanging,
    and split onto the member orders by painted m². An order joins the newest run when hanging starts if
    that run is still open and has the same paint; otherwise it opens a new run. A run stays open (and
    is flagged on the automatic-line and manager screens) until its consumption is entered; nothing on
    the floor is blocked by an open run (owner decision 2026-10-09).
    """

    __tablename__ = "paint_runs"
    __table_args__ = (
        CheckConstraint(
            "(closed_at IS NULL AND consumed_kg IS NULL) OR (closed_at IS NOT NULL AND consumed_kg > 0)",
            name="closed_run_has_positive_consumption",
        ),
        Index("ix_paint_runs_closed_at", "closed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    paint_id: Mapped[int] = mapped_column(ForeignKey("paints.id", ondelete="CASCADE"), nullable=False, index=True)
    consumed_kg: Mapped[float | None] = mapped_column(Float(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: clock.now(), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    paint = relationship("Paint")
    members = relationship(
        "PaintRunMember",
        back_populates="paint_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PaintRunMember.id",
    )


class PaintRunMember(Base):
    """One order's hanging pass inside a paint run, with its m² weight and (once closed) its kg share."""

    __tablename__ = "paint_run_members"
    __table_args__ = (
        UniqueConstraint("paint_run_id", "work_order_id", name="uq_paint_run_members_run_work_order"),
        CheckConstraint("area_m2 >= 0", name="area_non_negative"),
        CheckConstraint("allocated_kg IS NULL OR allocated_kg >= 0", name="allocated_kg_non_negative_if_present"),
        Index("ix_paint_run_members_work_order_id", "work_order_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    paint_run_id: Mapped[int] = mapped_column(ForeignKey("paint_runs.id", ondelete="CASCADE"), nullable=False)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False)
    area_m2: Mapped[float] = mapped_column(Float(), nullable=False)
    allocated_kg: Mapped[float | None] = mapped_column(Float(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: clock.now(), nullable=False)

    paint_run = relationship("PaintRun", back_populates="members")
    work_order = relationship("WorkOrder")
