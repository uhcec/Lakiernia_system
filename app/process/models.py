from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.process.enums import ProcessStage, QuantityBatchType, StageStatus


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
    __table_args__ = (UniqueConstraint("work_order_id", "stage"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False)
    stage: Mapped[ProcessStage] = mapped_column(process_stage_enum, nullable=False)
    status: Mapped[StageStatus] = mapped_column(stage_status_enum, default=StageStatus.NOT_STARTED, nullable=False)
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

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer(), nullable=False)
    type: Mapped[QuantityBatchType] = mapped_column(quantity_batch_type_enum, nullable=False)
    parent_batch_id: Mapped[int | None] = mapped_column(ForeignKey("work_order_quantity_batches.id", ondelete="SET NULL"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    current_stage: Mapped[ProcessStage | None] = mapped_column(process_stage_enum, nullable=True)
    current_stage_status: Mapped[StageStatus | None] = mapped_column(stage_status_enum, nullable=True)
    is_partial: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)

    work_order = relationship("WorkOrder", back_populates="quantity_batches")
    parent_batch = relationship("WorkOrderQuantityBatch", remote_side="WorkOrderQuantityBatch.id")
