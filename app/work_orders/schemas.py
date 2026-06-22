from datetime import date, datetime
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

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
from app.foils.schemas import FoilSummaryRead
from app.shared.enums import WorkOrderStatus
from app.shared.enums import QueueNamespace, WorkOrderKind, get_queue_namespace_label, get_work_order_kind_label


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


class WorkOrderKindView(BaseModel):
    value: WorkOrderKind
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
    external_order_number: str | None = None
    title: str
    customer_name: str
    ral_code: str
    paint_code: str | None = None
    paint_stock_snapshot_quantity_kg: float | None = None
    total_area_m2: float | None
    total_quantity: int
    completed_quantity: int
    current_active_quantity: int
    planned_pickup_date: date | None = None
    is_correction: bool
    is_historical_correction: bool = False
    is_decoral_incomplete: bool = False
    work_order_kind: WorkOrderKindView
    is_ocynk: bool = False
    correction_reason_category: str | None = None
    correction_reason_note: str | None = None
    process_status: ProcessStatusView


def _validate_counting_rule(field_name: str, quantity: int | None, to_count: bool) -> None:
    if quantity is None and not to_count:
        raise ValueError(f"{field_name}: podaj ilość albo zaznacz 'Do policzenia na produkcji'.")
    if quantity is not None and to_count:
        raise ValueError(f"{field_name}: wybierz ilość albo 'Do policzenia na produkcji', nie oba naraz.")


def _validate_category_quantity(field_name: str, quantity: int | None, to_count: bool, total_quantity: int) -> None:
    _validate_counting_rule(field_name, quantity, to_count)
    if quantity is None:
        return
    if quantity > total_quantity:
        raise ValueError(f"{field_name}: ilość nie może przekraczać ilości całkowitej.")


def _validate_category_quantity_sum(
    profiles_quantity: int | None,
    accessories_quantity: int | None,
    total_quantity: int,
) -> None:
    if profiles_quantity is None or accessories_quantity is None:
        return
    if profiles_quantity + accessories_quantity != total_quantity:
        raise ValueError("Profile + Akcesoria: suma musi być równa ilości całkowitej.")


class WorkOrderCreate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    external_order_number: str | None = Field(default=None, min_length=1, max_length=128)
    total_quantity: int = Field(default=1, gt=0)
    description: str | None = None
    customer_name: str = Field(min_length=1, max_length=255)
    ral_code: str = Field(min_length=1, max_length=64)
    paint_code: str = Field(min_length=1, max_length=64)
    paint_producer: str = Field(min_length=1, max_length=255)
    coating_type: CoatingType
    decoral_foil_id: int | None = Field(default=None, ge=1)
    work_order_kind: WorkOrderKind = WorkOrderKind.STANDARD
    is_ocynk: bool = False
    received_date: date
    planned_pickup_date: date | None = None
    total_area_m2: float = Field(gt=0)
    is_incomplete_on_arrival: bool = False
    profiles_quantity: int | None = Field(default=None, ge=0)
    profiles_to_count: bool = False
    accessories_quantity: int | None = Field(default=None, ge=0)
    accessories_to_count: bool = False
    notes: str | None = None

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def validate_counting_fields(self) -> "WorkOrderCreate":
        _validate_category_quantity("Profile", self.profiles_quantity, self.profiles_to_count, self.total_quantity)
        _validate_category_quantity("Akcesoria", self.accessories_quantity, self.accessories_to_count, self.total_quantity)
        _validate_category_quantity_sum(self.profiles_quantity, self.accessories_quantity, self.total_quantity)
        return self


class WorkOrderUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    external_order_number: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    customer_name: str | None = Field(default=None, max_length=255)
    ral_code: str | None = Field(default=None, min_length=1, max_length=64)
    paint_code: str | None = Field(default=None, min_length=1, max_length=64)
    paint_producer: str | None = Field(default=None, min_length=1, max_length=255)
    decoral_foil_id: int | None = Field(default=None, ge=1)
    received_date: date | None = None
    planned_pickup_date: date | None = None
    total_area_m2: float | None = Field(default=None, gt=0)
    profiles_quantity: int | None = Field(default=None, ge=0)
    profiles_to_count: bool | None = None
    accessories_quantity: int | None = Field(default=None, ge=0)
    accessories_to_count: bool | None = None
    notes: str | None = None

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class WorkOrderReleaseUpdate(BaseModel):
    is_released_to_client: bool

    model_config = ConfigDict(extra="forbid")


class WorkOrderRead(BaseModel):
    id: int
    order_number: str
    external_order_number: str | None = None
    title: str
    total_quantity: int
    completed_quantity: int
    current_active_quantity: int
    waiting_ok_quantity: int
    pending_correction_quantity: int
    total_progress_quantity: int
    is_correction: bool
    is_historical_correction: bool = False
    is_decoral_incomplete: bool = False
    work_order_kind: WorkOrderKindView
    is_ocynk: bool = False
    correction_reason_category: str | None = None
    correction_reason_note: str | None = None
    parent_order: WorkOrderRelationSummaryRead | None = None
    correction_orders: list[WorkOrderRelationSummaryRead] = Field(default_factory=list)
    description: str | None
    customer_name: str
    ral_code: str
    paint_code: str | None = None
    paint_producer: str
    predicted_paint_quantity_kg: float | None = None
    current_paint_stock_quantity_kg: float | None = None
    paint_inventory_insufficient_for_prediction: bool = False
    paint_inventory_shortage_quantity_kg: float | None = None
    paint_stock_snapshot_quantity_kg: float | None = None
    consumed_paint_quantity_kg: float
    status: WorkOrderStatusView = Field(description="Derived compatibility field. Lifecycle truth comes from process_status and stage_states.")
    process_status: ProcessStatusView
    queue_blocked_by_resource: str | None = None
    queue_blocked_reason: str | None = None
    coating_type: CoatingTypeView
    decoral_foil: FoilSummaryRead | None = None
    production_type: ProductionTypeView | None
    queue_namespace: QueueNamespaceView
    queue_position: int | None
    stage_states: list[WorkOrderStageStateRead]
    batches: list[WorkOrderQuantityBatchRead]
    received_date: date
    planned_pickup_date: date | None
    is_overdue: bool = False
    is_released_to_client: bool = False
    released_to_client_at: datetime | None = None
    total_area_m2: float | None
    is_incomplete_on_arrival: bool
    surface_preparation_counted_quantity: int | None = None
    surface_preparation_quantity_difference: int | None = None
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


def build_work_order_kind_view(work_order_kind: WorkOrderKind) -> WorkOrderKindView:
    return WorkOrderKindView(value=work_order_kind, label=get_work_order_kind_label(work_order_kind))


def build_process_status_view(process_status: ProcessDisplayStatus) -> ProcessStatusView:
    return ProcessStatusView(value=process_status, label=get_process_display_status_label(process_status))


def build_process_stage_view(stage: ProcessStage) -> ProcessStageView:
    return ProcessStageView(value=stage, label=get_process_stage_label(stage))


def build_stage_status_info_view(status: StageStatus) -> StageStatusInfoView:
    return StageStatusInfoView(value=status, label=get_stage_status_label(status))


def build_quantity_batch_type_view(batch_type: QuantityBatchType) -> QuantityBatchTypeView:
    return QuantityBatchTypeView(value=batch_type, label=get_quantity_batch_type_label(batch_type))


def calculate_predicted_paint_quantity_kg(total_area_m2: float | None) -> float | None:
    if total_area_m2 is None:
        return None
    predicted_quantity = total_area_m2 / 4 if total_area_m2 < 100 else total_area_m2 / 6
    return float(Decimal(str(predicted_quantity)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def calculate_paint_shortage_quantity_kg(
    predicted_paint_quantity_kg: float | None,
    current_paint_stock_quantity_kg: float | None,
) -> float | None:
    if predicted_paint_quantity_kg is None or current_paint_stock_quantity_kg is None:
        return None
    if predicted_paint_quantity_kg <= current_paint_stock_quantity_kg:
        return None
    return float(
        Decimal(str(predicted_paint_quantity_kg - current_paint_stock_quantity_kg)).quantize(
            Decimal("1"),
            rounding=ROUND_CEILING,
        )
    )


def build_work_order_relation_summary(work_order: "WorkOrder") -> WorkOrderRelationSummaryRead:
    process_status = ProcessDisplayStatus.READY
    if work_order.is_incomplete_on_arrival:
        process_status = ProcessDisplayStatus.INCOMPLETE
    elif work_order.production_type is None or work_order.queue_position is None:
        process_status = ProcessDisplayStatus.TO_BE_PLANNED

    return WorkOrderRelationSummaryRead(
        id=work_order.id,
        order_number=work_order.order_number,
        external_order_number=work_order.external_order_number,
        title=work_order.title,
        customer_name=work_order.customer_name,
        ral_code=work_order.ral_code,
        paint_code=work_order.paint_code,
        paint_stock_snapshot_quantity_kg=work_order.paint_stock_snapshot_quantity_kg,
        total_area_m2=work_order.total_area_m2,
        total_quantity=work_order.total_quantity,
        completed_quantity=work_order.completed_quantity,
        current_active_quantity=work_order.current_active_quantity,
        planned_pickup_date=work_order.planned_pickup_date,
        is_correction=work_order.is_correction,
        work_order_kind=build_work_order_kind_view(work_order.work_order_kind),
        is_ocynk=work_order.is_ocynk,
        correction_reason_category=work_order.correction_reason_category,
        correction_reason_note=work_order.correction_reason_note,
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