from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import PaintStockMovementType, get_paint_stock_movement_type_label


class PaintRead(BaseModel):
    id: int
    ral_code: str
    paint_producer: str
    paint_code: str
    current_quantity_kg: float
    created_at: datetime
    updated_at: datetime


class PaintLookupRead(BaseModel):
    paint_id: int | None = None
    ral_code: str
    paint_producer: str
    paint_code: str
    current_quantity_kg: float
    exists_in_inventory: bool


class PaintListResponse(BaseModel):
    items: list[PaintRead]
    total: int
    limit: int
    offset: int


class PaintStockMovementTypeView(BaseModel):
    value: PaintStockMovementType
    label: str


class PaintStockMovementRead(BaseModel):
    id: int
    paint_id: int
    work_order_id: int | None = None
    movement_type: PaintStockMovementTypeView
    quantity_delta_kg: float
    resulting_quantity_kg: float
    movement_date: date
    note: str | None = None
    created_at: datetime


class PaintStockMovementListResponse(BaseModel):
    items: list[PaintStockMovementRead]
    total: int
    limit: int
    offset: int


class PaintDeliveryCreate(BaseModel):
    ral_code: str = Field(min_length=1, max_length=64)
    paint_producer: str = Field(min_length=1, max_length=255)
    paint_code: str = Field(min_length=1, max_length=64)
    quantity_kg: float = Field(gt=0)
    movement_date: date | None = None
    note: str | None = None

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PaintManualAdjustmentCreate(BaseModel):
    ral_code: str = Field(min_length=1, max_length=64)
    paint_producer: str = Field(min_length=1, max_length=255)
    paint_code: str = Field(min_length=1, max_length=64)
    quantity_delta_kg: float
    movement_date: date | None = None
    note: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def build_paint_stock_movement_type_view(movement_type: PaintStockMovementType) -> PaintStockMovementTypeView:
    return PaintStockMovementTypeView(value=movement_type, label=get_paint_stock_movement_type_label(movement_type))
