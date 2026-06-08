from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.process.enums import ProductionType


class WorkOrderPlanAssignRequest(BaseModel):
    production_type: ProductionType
    queue_position: int = Field(ge=1)

    model_config = ConfigDict(extra="forbid")


class WorkOrderProductionTypeUpdateRequest(BaseModel):
    production_type: ProductionType

    model_config = ConfigDict(extra="forbid")


class WorkOrderQueuePositionUpdateRequest(BaseModel):
    queue_position: int = Field(ge=1)

    model_config = ConfigDict(extra="forbid")


class WorkOrderQueueReorderRequest(BaseModel):
    work_order_id: int = Field(ge=1)
    queue_position: int = Field(ge=1)

    model_config = ConfigDict(extra="forbid")


class WorkOrderQueueReorderBatchRequest(BaseModel):
    queue_revision: datetime
    items: list[WorkOrderQueueReorderRequest]

    model_config = ConfigDict(extra="forbid")


class CorrectionReasonReportItem(BaseModel):
    correction_reason_category: str | None
    work_order_count: int = Field(ge=0)
    total_correction_quantity: int = Field(ge=0)


class ThroughputPeriod(BaseModel):
    period_start: date
    period_label: str
    m2_manual: float
    m2_automatic: float
    m2_decoral: float
    m2_total: float
    orders_count: int
    correction_pieces: int
    correction_orders_count: int


class ThroughputStats(BaseModel):
    periods: list[ThroughputPeriod]
    totals: ThroughputPeriod
    orders_without_m2_count: int