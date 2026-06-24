from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.process.enums import CoatingType, ProductionType
from app.work_orders.enums import WorkOrderAttachmentCategory
from app.shared.enums import PlanningPriority, QueueNamespace, WorkOrderKind
from app.shared import clock


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

queue_namespace_enum = Enum(
    QueueNamespace,
    name="queue_namespace",
    native_enum=False,
    values_callable=lambda namespaces: [namespace.value for namespace in namespaces],
)

work_order_kind_enum = Enum(
    WorkOrderKind,
    name="work_order_kind",
    native_enum=False,
    values_callable=lambda kinds: [kind.value for kind in kinds],
)

planning_priority_enum = Enum(
    PlanningPriority,
    name="planning_priority",
    native_enum=False,
    values_callable=lambda priorities: [priority.value for priority in priorities],
)


class WorkOrder(Base):
    __tablename__ = "work_orders"
    __table_args__ = (
        CheckConstraint("total_quantity > 0", name="total_quantity_positive"),
        CheckConstraint("completed_quantity >= 0", name="completed_quantity_non_negative"),
        CheckConstraint("completed_quantity <= total_quantity", name="completed_quantity_lte_total_quantity"),
        CheckConstraint(
            "paint_stock_snapshot_quantity_kg IS NULL OR paint_stock_snapshot_quantity_kg >= 0",
            name="paint_stock_snapshot_quantity_positive_if_present",
        ),
        CheckConstraint("consumed_paint_quantity_kg >= 0", name="consumed_paint_quantity_non_negative"),
        CheckConstraint("queue_position IS NULL OR queue_position >= 1", name="queue_position_positive_if_present"),
        CheckConstraint(
            "(production_type IS NULL AND queue_position IS NULL) OR (production_type IS NOT NULL AND queue_position IS NOT NULL)",
            name="planned_requires_production_type_and_queue_position",
        ),
        CheckConstraint(
            "queue_position IS NULL OR is_incomplete_on_arrival = 0",
            name="incomplete_requires_unplanned",
        ),
        # A planning lock (pin/urgent, NA49.K) is only meaningful on a planned order — it locks a queue
        # slot — so it must be cleared whenever the order leaves the queue (queue_position → NULL).
        CheckConstraint(
            "planning_priority IS NULL OR queue_position IS NOT NULL",
            name="planning_priority_requires_planned",
        ),
        CheckConstraint(
            "profiles_quantity IS NULL OR (profiles_quantity >= 0 AND profiles_quantity <= total_quantity)",
            name="profiles_quantity_within_total_if_known",
        ),
        CheckConstraint(
            "accessories_quantity IS NULL OR (accessories_quantity >= 0 AND accessories_quantity <= total_quantity)",
            name="accessories_quantity_within_total_if_known",
        ),
        CheckConstraint(
            "profiles_quantity IS NULL OR accessories_quantity IS NULL OR profiles_quantity + accessories_quantity = total_quantity",
            name="profile_accessory_quantities_sum_total_if_known",
        ),
        CheckConstraint(
            "decoral_foil_id IS NULL OR coating_type = 'DECORAL'",
            name="decoral_foil_requires_decoral_coating",
        ),
        CheckConstraint("parent_order_id IS NULL OR parent_order_id != id", name="parent_order_cannot_reference_self"),
        CheckConstraint("is_correction = 0 OR parent_order_id IS NOT NULL", name="correction_requires_parent"),
        CheckConstraint(
            "(is_correction = 1 AND queue_namespace = 'CORRECTIONS') OR (is_correction = 0 AND queue_namespace = 'MAIN')",
            name="correction_namespace_consistent",
        ),
        # Queue position is unique *per production line* (MANUAL vs AUTOMATIC), so the manual
        # and automatic plans are numbered independently (position 1 may exist on both lines).
        Index(
            "uq_work_orders_line_queue_position",
            "production_type",
            "queue_position",
            unique=True,
            sqlite_where=text("queue_position IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    paint_id: Mapped[int | None] = mapped_column(ForeignKey("paints.id", ondelete="SET NULL"), nullable=True, index=True)
    decoral_foil_id: Mapped[int | None] = mapped_column(ForeignKey("foils.id", ondelete="SET NULL"), nullable=True, index=True)
    order_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    external_order_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    total_quantity: Mapped[int] = mapped_column(Integer(), nullable=False, default=1)
    completed_quantity: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    parent_order_id: Mapped[int | None] = mapped_column(ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True)
    is_correction: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    correction_reason_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correction_reason_note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    ral_code: Mapped[str] = mapped_column(String(64), nullable=False)
    paint_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    paint_producer: Mapped[str] = mapped_column(String(255), nullable=False)
    paint_stock_snapshot_quantity_kg: Mapped[float | None] = mapped_column(Float(), nullable=True)
    consumed_paint_quantity_kg: Mapped[float] = mapped_column(Float(), nullable=False, default=0)
    coating_type: Mapped[CoatingType] = mapped_column(coating_type_enum, default=CoatingType.RAL, nullable=False)
    work_order_kind: Mapped[WorkOrderKind] = mapped_column(
        work_order_kind_enum,
        nullable=False,
        default=WorkOrderKind.STANDARD,
    )
    is_ocynk: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    production_type: Mapped[ProductionType | None] = mapped_column(production_type_enum, nullable=True)
    queue_namespace: Mapped[QueueNamespace] = mapped_column(
        queue_namespace_enum,
        nullable=False,
        default=QueueNamespace.MAIN,
        index=True,
    )
    queue_position: Mapped[int | None] = mapped_column(Integer(), nullable=True, index=True)
    # Manager planning lock respected by the painting auto-scheduler re-optimise (NA49.K). NULL = freely
    # re-orderable; PINNED = keep its queue slot; URGENT = force to the front of the line.
    planning_priority: Mapped[PlanningPriority | None] = mapped_column(planning_priority_enum, nullable=True)
    received_date: Mapped[date] = mapped_column(Date(), nullable=False)
    planned_pickup_date: Mapped[date] = mapped_column(Date(), nullable=False)
    released_to_client_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_area_m2: Mapped[float | None] = mapped_column(Float(), nullable=True)
    is_incomplete_on_arrival: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    profiles_quantity: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    profiles_to_count: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    accessories_quantity: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    accessories_to_count: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: clock.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: clock.now(),
        onupdate=lambda: clock.now(),
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
    parent_order = relationship(
        "WorkOrder",
        remote_side="WorkOrder.id",
        back_populates="correction_orders",
    )
    correction_orders = relationship("WorkOrder", back_populates="parent_order")
    attachments = relationship(
        "WorkOrderAttachment",
        back_populates="work_order",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="WorkOrderAttachment.uploaded_at.desc()",
    )
    paint = relationship("Paint", back_populates="work_orders")
    decoral_foil = relationship("Foil", back_populates="work_orders")

    @property
    def active_batches(self):
        return [batch for batch in self.quantity_batches if batch.is_active]

    @property
    def active_batch(self):
        # Derived from active_batches (NA46 §A4): the DB partial-unique index
        # (uq_work_order_quantity_batches_one_active_per_work_order, WHERE is_active=1) guarantees at
        # most one active batch per work order, so the single active batch IS the active batch — no
        # stored pointer to hand-sync. Returns None when there is none (or, defensively, if an
        # in-memory pre-flush window ever held more than one, which the index would reject on flush).
        active_batches = self.active_batches
        return active_batches[0] if len(active_batches) == 1 else None

    @property
    def current_active_quantity(self) -> int:
        return sum(batch.quantity for batch in self.active_batches)

    @property
    def correction_chain_ids(self) -> list[int]:
        # This order plus all descendant correction orders (recursively). Used to roll up
        # cumulative paint consumption across a correction chain (NA32).
        ids = [self.id]
        for child in self.correction_orders:
            ids.extend(child.correction_chain_ids)
        return ids


class WorkOrderNumberCounter(Base):
    __tablename__ = "work_order_number_counters"

    year: Mapped[int] = mapped_column(Integer(), primary_key=True)
    last_value: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: clock.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: clock.now(), nullable=False)


class WorkOrderAttachment(Base):
    __tablename__ = "work_order_attachments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer(), nullable=False)
    # Structured discriminator (NA36). Plain string validated at the app layer against
    # WorkOrderAttachmentCategory; defaults to DOCUMENT so every pre-existing attachment is a document.
    category: Mapped[str] = mapped_column(
        String(32), nullable=False, default=WorkOrderAttachmentCategory.DOCUMENT.value
    )
    # Optional free-text human sub-label (legacy; orthogonal to `category`).
    attachment_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: clock.now(), nullable=False)

    work_order = relationship("WorkOrder", back_populates="attachments")