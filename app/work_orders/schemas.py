from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.process.enums import (
    CoatingType,
    ProcessDisplayStatus,
    ProcessStage,
    ProductionType,
    StageStatus,
    get_coating_type_label,
    get_process_display_status_label,
    get_process_stage_label,
    get_production_type_label,
    get_stage_status_label,
)
from app.shared.enums import WorkOrderStatus


class WorkOrderStatusOption(BaseModel):
    value: WorkOrderStatus
    label: str


class WorkOrderStatusView(BaseModel):
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


class WorkOrderStageStateRead(BaseModel):
    stage: ProcessStageView
    status: StageStatusInfoView


class WorkOrderCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    customer_name: str | None = Field(default=None, max_length=255)
    coating_type: CoatingType
    due_date: date | None = None
    notes: str | None = None

    model_config = ConfigDict(extra="forbid")


class WorkOrderStatusTransitionRequest(BaseModel):
    target_status: WorkOrderStatus
    comment: str | None = None

    model_config = ConfigDict(extra="forbid")


class WorkOrderUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    customer_name: str | None = Field(default=None, max_length=255)
    due_date: date | None = None
    notes: str | None = None

    model_config = ConfigDict(extra="forbid")


class WorkOrderRead(BaseModel):
    id: int
    order_number: str
    title: str
    description: str | None
    customer_name: str | None
    status: WorkOrderStatusView
    process_status: ProcessStatusView
    coating_type: CoatingTypeView
    production_type: ProductionTypeView | None
    queue_position: int | None
    stage_states: list[WorkOrderStageStateRead]
    due_date: date | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


def build_coating_type_view(coating_type: CoatingType) -> CoatingTypeView:
    return CoatingTypeView(value=coating_type, label=get_coating_type_label(coating_type))


def build_production_type_view(production_type: ProductionType) -> ProductionTypeView:
    return ProductionTypeView(value=production_type, label=get_production_type_label(production_type))


def build_process_status_view(process_status: ProcessDisplayStatus) -> ProcessStatusView:
    return ProcessStatusView(value=process_status, label=get_process_display_status_label(process_status))


def build_process_stage_view(stage: ProcessStage) -> ProcessStageView:
    return ProcessStageView(value=stage, label=get_process_stage_label(stage))


def build_stage_status_info_view(status: StageStatus) -> StageStatusInfoView:
    return StageStatusInfoView(value=status, label=get_stage_status_label(status))


class WorkOrderListResponse(BaseModel):
    items: list[WorkOrderRead]
    total: int
    limit: int
    offset: int