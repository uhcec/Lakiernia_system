from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.process.enums import CoatingType, ProductionType, get_coating_type_label, get_production_type_label
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


class WorkOrderCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    customer_name: str | None = Field(default=None, max_length=255)
    coating_type: CoatingType = Field(default=CoatingType.RAL)
    production_type: ProductionType | None = None
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
    coating_type: CoatingTypeView
    production_type: ProductionTypeView | None
    queue_position: int
    due_date: date | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


def build_coating_type_view(coating_type: CoatingType) -> CoatingTypeView:
    return CoatingTypeView(value=coating_type, label=get_coating_type_label(coating_type))


def build_production_type_view(production_type: ProductionType) -> ProductionTypeView:
    return ProductionTypeView(value=production_type, label=get_production_type_label(production_type))


class WorkOrderListResponse(BaseModel):
    items: list[WorkOrderRead]
    total: int
    limit: int
    offset: int