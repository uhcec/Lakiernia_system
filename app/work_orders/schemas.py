from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import WorkOrderStatus


class WorkOrderStatusOption(BaseModel):
    value: WorkOrderStatus
    label: str


class WorkOrderStatusView(BaseModel):
    value: WorkOrderStatus
    label: str


class WorkOrderCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    customer_name: str | None = Field(default=None, max_length=255)
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
    due_date: date | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class WorkOrderListResponse(BaseModel):
    items: list[WorkOrderRead]
    total: int
    limit: int
    offset: int