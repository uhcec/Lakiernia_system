from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.process.enums import CoatingType, ProcessStage, ProductionType


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
    # Coating partition of the same total (counted once per order): RAL-only + decoral = m2_total.
    m2_ral_only: float
    m2_decoral: float
    # Decoral *pass* ("przejazd") workload — overlaps the base coat, NOT part of m2_total.
    m2_decoral_pass: float
    m2_total: float
    orders_count: int
    correction_pieces: int
    correction_orders_count: int


class ThroughputStats(BaseModel):
    periods: list[ThroughputPeriod]
    totals: ThroughputPeriod
    orders_without_m2_count: int


class CycleTimeSegment(BaseModel):
    """One slice of a cycle-time average for a sub-cohort (e.g. manual orders only).

    The overall average is the count-weighted mean of either pair of segments, so the breakdown
    reconciles to the whole (the two partitions are independent cross-sections of the same cohort).
    """

    key: str
    label: str
    average_seconds: float
    # Total active seconds across this segment's orders — sums across the partition to the stage total,
    # so a "suma czasu" view can stack the segments into the whole (cf. average, which is a weighted mean).
    total_seconds: float = 0.0
    orders_count: int


class CycleTimeBreakdown(BaseModel):
    """The same average cut two independent ways (NA23): by production method and by order coating.

    Each list is a full partition of the cohort that produced the headline average; empty segments
    (no orders of that kind) are omitted.
    """

    by_method: list[CycleTimeSegment] = Field(default_factory=list)
    by_coating: list[CycleTimeSegment] = Field(default_factory=list)


class StageCycleTime(BaseModel):
    stage: ProcessStage
    stage_label: str
    average_seconds: float
    # Sum of active time across all cohort orders at this stage — the headline of the "suma" chart;
    # the breakdown segment totals sum to it.
    total_seconds: float = 0.0
    orders_count: int
    average_wait_before_seconds: float | None = None
    wait_orders_count: int = 0
    breakdown: CycleTimeBreakdown = Field(default_factory=CycleTimeBreakdown)


class CycleTimeStats(BaseModel):
    date_from: date
    date_to: date
    orders_count: int
    overall_average_seconds: float | None
    stages: list[StageCycleTime]
    overall_breakdown: CycleTimeBreakdown = Field(default_factory=CycleTimeBreakdown)


class WipAgingItem(BaseModel):
    work_order_id: int
    order_number: str
    customer_name: str | None
    stage: ProcessStage
    stage_label: str
    production_type: ProductionType | None
    coating_type: CoatingType | None = None
    queue_position: int | None
    age_seconds: float


class WipAgingSegment(BaseModel):
    key: str
    label: str
    orders_count: int


class WipAgingBreakdown(BaseModel):
    """Count of currently-in-progress orders cut two independent ways (NA23): method and coating.

    Each list fully partitions the live cohort, so the segment counts in either list sum to the
    total number of items.
    """

    by_method: list[WipAgingSegment] = Field(default_factory=list)
    by_coating: list[WipAgingSegment] = Field(default_factory=list)


class WipAgingStats(BaseModel):
    generated_at: datetime
    items: list[WipAgingItem]
    breakdown: WipAgingBreakdown = Field(default_factory=WipAgingBreakdown)