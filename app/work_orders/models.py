from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.process.enums import CoatingType, ProductionType
from app.shared.enums import WorkOrderStatus


work_order_status_enum = Enum(
    WorkOrderStatus,
    name="work_order_status",
    native_enum=False,
    values_callable=lambda statuses: [status.value for status in statuses],
)

coating_type_enum = Enum(
    CoatingType,
    name="coating_type",
    native_enum=False,
    values_callable=lambda coating_types: [coating_type.value for coating_type in coating_types],
)

production_type_enum = Enum(
    ProductionType,
    name="production_type",
    native_enum=False,
    values_callable=lambda production_types: [production_type.value for production_type in production_types],
)


class WorkOrder(Base):
    __tablename__ = "work_orders"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    order_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    total_quantity: Mapped[int] = mapped_column(Integer(), nullable=False, default=1)
    completed_quantity: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    current_active_batch_id: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    ral_code: Mapped[str] = mapped_column(String(64), nullable=False)
    paint_producer: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[WorkOrderStatus] = mapped_column(work_order_status_enum, default=WorkOrderStatus.ENTERED, nullable=False)
    coating_type: Mapped[CoatingType] = mapped_column(coating_type_enum, default=CoatingType.RAL, nullable=False)
    production_type: Mapped[ProductionType | None] = mapped_column(production_type_enum, nullable=True)
    queue_position: Mapped[int | None] = mapped_column(Integer(), nullable=True, index=True)
    received_date: Mapped[date] = mapped_column(Date(), nullable=False)
    planned_pickup_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    total_area_m2: Mapped[float | None] = mapped_column(Float(), nullable=True)
    is_incomplete_on_arrival: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    profiles_quantity: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    profiles_to_count: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    accessories_quantity: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    accessories_to_count: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    stage_states = relationship(
        "WorkOrderStageState",
        back_populates="work_order",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    quantity_batches = relationship(
        "WorkOrderQuantityBatch",
        back_populates="work_order",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def active_batches(self):
        return [batch for batch in self.quantity_batches if batch.is_active]

    @property
    def active_batch(self):
        for batch in self.active_batches:
            if batch.id == self.current_active_batch_id:
                return batch
        for batch in self.quantity_batches:
            if batch.id == self.current_active_batch_id:
                return batch
        if len(self.active_batches) == 1:
            return self.active_batches[0]
        return None

    @property
    def current_active_quantity(self) -> int:
        return sum(batch.quantity for batch in self.active_batches)