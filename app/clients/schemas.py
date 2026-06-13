from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.work_orders.schemas import ProcessStatusView, ProductionTypeView, WorkOrderStatusView


class ClientCreate(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=64)
    nip: str | None = Field(default=None, max_length=32)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ClientUpdate(BaseModel):
    company_name: str | None = Field(default=None, min_length=1, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=64)
    nip: str | None = Field(default=None, max_length=32)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ClientRead(BaseModel):
    id: int
    company_name: str
    contact_phone: str | None = None
    nip: str | None = None
    order_count: int
    created_at: datetime
    updated_at: datetime


class ClientListResponse(BaseModel):
    items: list[ClientRead]
    total: int
    limit: int
    offset: int


class ClientOrderHistoryItem(BaseModel):
    id: int
    order_number: str
    external_order_number: str | None = None
    title: str
    total_quantity: int
    ral_code: str
    received_date: date
    planned_pickup_date: date | None = None
    status: WorkOrderStatusView
    production_type: ProductionTypeView | None = None
    process_status: ProcessStatusView | None = None


class ClientDetailRead(BaseModel):
    id: int
    company_name: str
    contact_phone: str | None = None
    nip: str | None = None
    created_at: datetime
    updated_at: datetime
    orders: list[ClientOrderHistoryItem]
