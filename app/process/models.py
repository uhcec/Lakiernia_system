from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.process.enums import ProcessStage, StageStatus


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
