from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.process.enums import (
    CoatingType,
    ProcessDisplayStatus,
    ProcessStage,
    ProductionType,
    QuantityBatchType,
    StageStatus,
    get_coating_type_label,
    get_process_display_status_label,
    get_process_stage_label,
    get_production_type_label,
    get_quantity_batch_type_label,
    get_stage_status_label,
)
from app.shared.enums import WorkOrderStatus
from app.shared.enums import QueueNamespace, get_queue_namespace_label


class WorkOrderStatusOption(BaseModel):
    value: WorkOrderStatus
    label: str


class WorkOrderStatusView(BaseModel):
    """Legacy/internal work-order status kept for API compatibility."""

    value: WorkOrderStatus
    label: str


class CoatingTypeView(BaseModel):
    value: CoatingType
    label: str


class ProductionTypeView(BaseModel):
    value: ProductionType
    label: str


class ProcessStatusView(BaseModel):
    value: ProcessDisplayStatus
    label: str


class ProcessStageView(BaseModel):
    value: ProcessStage
    label: str


class StageStatusInfoView(BaseModel):
    value: StageStatus
    label: str


class QueueNamespaceView(BaseModel):
    value: QueueNamespace
    label: str


class WorkOrderStageStateRead(BaseModel):
    stage: ProcessStageView
    status: StageStatusInfoView


class QuantityBatchTypeView(BaseModel):
    value: QuantityBatchType
    label: str


class WorkOrderQuantityBatchRead(BaseModel):
    id: int
    quantity: int
    type: QuantityBatchTypeView
    parent_batch_id: int | None
    is_active: bool
    is_finished: bool
    current_stage: ProcessStageView | None = None
    current_stage_status: StageStatusInfoView | None = None
    is_partial: bool = False
    created_at: datetime


class WorkOrderAttachmentRead(BaseModel):
    id: int
    work_order_id: int
    original_filename: str
    stored_filename: str
    storage_path: str
    content_type: str
    file_size: int
    attachment_type: str | None
    description: str | None
    uploaded_at: datetime


class WorkOrderRelationSummaryRead(BaseModel):
    id: int
    order_number: str
    title: str
    customer_name: str
    ral_code: str
    total_area_m2: float | None
    total_quantity: int
    completed_quantity: int
    current_active_quantity: int
    is_correction: bool
    process_status: ProcessStatusView


def _validate_counting_rule(field_name: str, quantity: int | None, to_count: bool) -> None:
    if quantity is None and not to_count:
        raise ValueError(f"{field_name}: podaj ilość albo zaznacz 'Do policzenia na produkcji'.")
    if quantity is not None and to_count:
        raise ValueError(f"{field_name}: wybierz ilość albo 'Do policzenia na produkcji', nie oba naraz.")


class WorkOrderCreate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    total_quantity: int = Field(default=1, gt=0)
    description: str | None = None
    customer_name: str = Field(min_length=1, max_length=255)
    ral_code: str = Field(min_length=1, max_length=64)
    paint_producer: str = Field(min_length=1, max_length=255)
    coating_type: CoatingType
    received_date: date
    planned_pickup_date: date | None = None
    total_area_m2: float | None = Field(default=None, gt=0)
    is_incomplete_on_arrival: bool = False
    profiles_quantity: int | None = Field(default=None, gt=0)
    profiles_to_count: bool = False
    accessories_quantity: int | None = Field(default=None, gt=0)
    accessories_to_count: bool = False
    notes: str | None = None

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def validate_counting_fields(self) -> "WorkOrderCreate":
        _validate_counting_rule("Profile", self.profiles_quantity, self.profiles_to_count)
        _validate_counting_rule("Akcesoria", self.accessories_quantity, self.accessories_to_count)
        return self


class WorkOrderStatusTransitionRequest(BaseModel):
    target_status: WorkOrderStatus
    comment: str | None = None

    model_config = ConfigDict(extra="forbid")


class WorkOrderUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    customer_name: str | None = Field(default=None, max_length=255)
    ral_code: str | None = Field(default=None, min_length=1, max_length=64)
    paint_producer: str | None = Field(default=None, min_length=1, max_length=255)
    received_date: date | None = None
    planned_pickup_date: date | None = None
    total_area_m2: float | None = Field(default=None, gt=0)
    profiles_quantity: int | None = Field(default=None, gt=0)
    profiles_to_count: bool | None = None
    accessories_quantity: int | None = Field(default=None, gt=0)
    accessories_to_count: bool | None = None
    notes: str | None = None

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class WorkOrderRead(BaseModel):
    id: int
    order_number: str
    title: str
    total_quantity: int
    completed_quantity: int
    current_active_quantity: int
    waiting_ok_quantity: int
    pending_correction_quantity: int
    total_progress_quantity: int
    is_correction: bool
    parent_order: WorkOrderRelationSummaryRead | None = None
    correction_orders: list[WorkOrderRelationSummaryRead] = Field(default_factory=list)
    description: str | None
    customer_name: str
    ral_code: str
    paint_producer: str
    status: WorkOrderStatusView = Field(description="Derived compatibility field. Lifecycle truth comes from process_status and stage_states.")
    process_status: ProcessStatusView
    coating_type: CoatingTypeView
    production_type: ProductionTypeView | None
    queue_namespace: QueueNamespaceView
    queue_position: int | None
    stage_states: list[WorkOrderStageStateRead]
    batches: list[WorkOrderQuantityBatchRead]
    received_date: date
    planned_pickup_date: date | None
    total_area_m2: float | None
    is_incomplete_on_arrival: bool
    profiles_quantity: int | None
    profiles_to_count: bool
    accessories_quantity: int | None
    accessories_to_count: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime


def build_coating_type_view(coating_type: CoatingType) -> CoatingTypeView:
    return CoatingTypeView(value=coating_type, label=get_coating_type_label(coating_type))


def build_production_type_view(production_type: ProductionType) -> ProductionTypeView:
    return ProductionTypeView(value=production_type, label=get_production_type_label(production_type))


def build_queue_namespace_view(queue_namespace: QueueNamespace) -> QueueNamespaceView:
    return QueueNamespaceView(value=queue_namespace, label=get_queue_namespace_label(queue_namespace))


def build_process_status_view(process_status: ProcessDisplayStatus) -> ProcessStatusView:
    return ProcessStatusView(value=process_status, label=get_process_display_status_label(process_status))


def build_process_stage_view(stage: ProcessStage) -> ProcessStageView:
    return ProcessStageView(value=stage, label=get_process_stage_label(stage))


def build_stage_status_info_view(status: StageStatus) -> StageStatusInfoView:
    return StageStatusInfoView(value=status, label=get_stage_status_label(status))


def build_quantity_batch_type_view(batch_type: QuantityBatchType) -> QuantityBatchTypeView:
    return QuantityBatchTypeView(value=batch_type, label=get_quantity_batch_type_label(batch_type))


def build_work_order_relation_summary(work_order: "WorkOrder") -> WorkOrderRelationSummaryRead:
    process_status = ProcessDisplayStatus.READY
    if work_order.is_incomplete_on_arrival:
        process_status = ProcessDisplayStatus.INCOMPLETE
    elif work_order.production_type is None or work_order.queue_position is None:
        process_status = ProcessDisplayStatus.TO_BE_PLANNED

    return WorkOrderRelationSummaryRead(
        id=work_order.id,
        order_number=work_order.order_number,
        title=work_order.title,
        customer_name=work_order.customer_name,
        ral_code=work_order.ral_code,
        total_area_m2=work_order.total_area_m2,
        total_quantity=work_order.total_quantity,
        completed_quantity=work_order.completed_quantity,
        current_active_quantity=work_order.current_active_quantity,
        is_correction=work_order.is_correction,
        process_status=build_process_status_view(process_status),
    )


def build_work_order_attachment_read(attachment: "WorkOrderAttachment") -> WorkOrderAttachmentRead:
    return WorkOrderAttachmentRead(
        id=attachment.id,
        work_order_id=attachment.work_order_id,
        original_filename=attachment.original_filename,
        stored_filename=attachment.stored_filename,
        storage_path=attachment.storage_path,
        content_type=attachment.content_type,
        file_size=attachment.file_size,
        attachment_type=attachment.attachment_type,
        description=attachment.description,
        uploaded_at=attachment.uploaded_at,
    )


class WorkOrderListResponse(BaseModel):
    items: list[WorkOrderRead]
    total: int
    limit: int
    offset: int