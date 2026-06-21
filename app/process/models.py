from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.audit.models import station_id_enum
from app.database.base import Base
from app.process.enums import ProcessStage, QuantityBatchType, StageStatus
from app.shared.enums import StationId


process_stage_enum = Enum(
    ProcessStage,
    name="process_stage",
    native_enum=False,
    values_callable=lambda stages: [stage.value for stage in stages],
)

stage_status_enum = Enum(
    StageStatus,
    name="stage_status",
    native_enum=False,
    values_callable=lambda statuses: [status.value for status in statuses],
)

quantity_batch_type_enum = Enum(
    QuantityBatchType,
    name="quantity_batch_type",
    native_enum=False,
    values_callable=lambda batch_types: [batch_type.value for batch_type in batch_types],
)


class WorkOrderStageState(Base):
    __tablename__ = "work_order_stage_states"
    __table_args__ = (
        UniqueConstraint("work_order_id", "stage"),
        CheckConstraint("counted_quantity IS NULL OR counted_quantity > 0", name="counted_quantity_positive_if_present"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False)
    stage: Mapped[ProcessStage] = mapped_column(process_stage_enum, nullable=False)
    status: Mapped[StageStatus] = mapped_column(stage_status_enum, default=StageStatus.NOT_STARTED, nullable=False)
    counted_quantity: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    work_order = relationship("WorkOrder", back_populates="stage_states")


class WorkOrderQuantityBatch(Base):
    __tablename__ = "work_order_quantity_batches"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint(
            "(current_stage IS NULL AND current_stage_status IS NULL) OR (current_stage IS NOT NULL AND current_stage_status IS NOT NULL)",
            name="current_stage_and_status_nullness_match",
        ),
        CheckConstraint("is_active = 1 OR current_stage_status = 'DONE'", name="inactive_batch_requires_done_status"),
        Index(
            "uq_work_order_quantity_batches_one_active_per_work_order",
            "work_order_id",
            unique=True,
            sqlite_where=text("is_active = 1"),
            postgresql_where=text("is_active = true"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer(), nullable=False)
    type: Mapped[QuantityBatchType] = mapped_column(quantity_batch_type_enum, nullable=False)
    parent_batch_id: Mapped[int | None] = mapped_column(ForeignKey("work_order_quantity_batches.id", ondelete="SET NULL"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    current_stage: Mapped[ProcessStage | None] = mapped_column(process_stage_enum, nullable=True)
    current_stage_status: Mapped[StageStatus | None] = mapped_column(stage_status_enum, nullable=True)
    is_partial: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    correction_reason_category: Mapped[str | None] = mapped_column(Text(), nullable=True)
    correction_reason_note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)

    work_order = relationship("WorkOrder", back_populates="quantity_batches")
    parent_batch = relationship("WorkOrderQuantityBatch", remote_side="WorkOrderQuantityBatch.id")


class StageTransitionEvent(Base):
    """Append-only log of stage status transitions, for analytics/statistics.

    Unlike ``WorkOrderStageState`` (which keeps only the latest ``updated_at`` and is overwritten
    on every change), this table records *every* transition with the moment it ``occurred_at``, so
    cycle times, per-stage throughput, queue waits, and bottleneck analysis can be derived reliably.
    Rows are never updated or deleted (except by ``work_orders`` cascade). ``station_id`` is always
    captured; ``user_id`` is recorded when available — it stays NULL today (stations share an
    identity) and will populate automatically once operators get personal login. Writers cover the
    audit-event choke points (stage start/finish/reopen, packing completion, decoral-pass completion)
    plus the automatic implicit transitions (PRODUCTION/PACKING set to IN_PROGRESS when automatic
    HANGING finishes, and the automatic PRODUCTION->DONE at packing). Internal correction-reset/merge
    state changes (e.g. reopening the root Decoral pass when a correction child returns) are not
    individually logged; the subsequent normal finish re-logs the DONE, so analytics stay correct.
    """

    __tablename__ = "stage_transition_events"
    __table_args__ = (
        Index("ix_stage_transition_events_work_order_id", "work_order_id"),
        Index("ix_stage_transition_events_occurred_at", "occurred_at"),
        Index("ix_stage_transition_events_stage_status_occurred", "stage", "status", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False)
    batch_id: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    stage: Mapped[ProcessStage] = mapped_column(process_stage_enum, nullable=False)
    status: Mapped[StageStatus] = mapped_column(stage_status_enum, nullable=False)
    counted_quantity: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    station_id: Mapped[StationId] = mapped_column(station_id_enum, default=StationId.UNKNOWN, nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)


class StatOnlyCorrection(Base):
    """A "fixed on the spot" (od razu poprawiona) correction recorded at packing (NA34).

    The defect was corrected immediately, so the pieces are good and the order completes as-is — this
    row is *purely a statistic* (reason + quantity), not a `CORRECTION` batch or a child work order, so
    it never re-enters the workflow and never participates in the quantity-partition model. The shared
    correction-event source (`ManagerRepository.correction_events_select`) unions it in, so the reason
    report and throughput correction counters count it alongside replan/child corrections.
    """

    __tablename__ = "stat_only_corrections"
    __table_args__ = (
        CheckConstraint("correction_quantity > 0", name="stat_only_correction_quantity_positive"),
        Index("ix_stat_only_corrections_work_order_id", "work_order_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False)
    correction_quantity: Mapped[int] = mapped_column(Integer(), nullable=False)
    correction_reason_category: Mapped[str] = mapped_column(Text(), nullable=False)
    correction_reason_note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    correction_profiles_quantity: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    correction_accessories_quantity: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)

    work_order = relationship("WorkOrder")


class ProcessResourceLock(Base):
    __tablename__ = "process_resource_locks"

    resource_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
