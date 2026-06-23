from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.manager.enums import DEFAULT_RULE_ORDER, ScheduleRuleKey
from app.process.enums import CoatingType, ProcessStage, ProductionType
from app.work_orders.schemas import WorkOrderRead


class WorkOrderPlanAssignRequest(BaseModel):
    production_type: ProductionType
    # Optional: when omitted the order is appended to the end of its production line's queue.
    # A position may still be supplied (e.g. by seeds/tests) to place it explicitly.
    queue_position: int | None = Field(default=None, ge=1)

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
    # The production line whose queue is being reordered. Each line (MANUAL / AUTOMATIC) is
    # reordered independently, so a reorder only touches orders on this line.
    production_type: ProductionType
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


class ScheduleRuleConfigItem(BaseModel):
    """One rule in the manager's painting auto-scheduler priority list (NA33)."""

    key: ScheduleRuleKey
    label: str
    description: str
    enabled: bool


class ScheduleRuleConfigRead(BaseModel):
    production_type: ProductionType
    rules: list[ScheduleRuleConfigItem]


class ScheduleRuleConfigUpdateItem(BaseModel):
    key: ScheduleRuleKey
    enabled: bool

    model_config = ConfigDict(extra="forbid")


class ScheduleRuleConfigUpdate(BaseModel):
    # The full rule catalog, in the manager's chosen priority order, each toggled on/off. Must list
    # every known rule exactly once so the stored order is unambiguous.
    rules: list[ScheduleRuleConfigUpdateItem]

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _require_each_rule_exactly_once(self) -> "ScheduleRuleConfigUpdate":
        submitted = [item.key for item in self.rules]
        if sorted(submitted, key=lambda key: key.value) != sorted(DEFAULT_RULE_ORDER, key=lambda key: key.value):
            raise ValueError("Rules payload must list every scheduler rule exactly once.")
        return self


class AutoScheduleProposal(BaseModel):
    """A non-committal proposed painting order plus the colour-changeover improvement (NA33).

    The manager applies it (as-is or after editing) through the existing queue-reorder endpoint;
    ``queue_revision`` is the per-line snapshot the proposal was built from. ``proposed_order`` lists
    only the *active* planned orders on the line, in the proposed sequence."""

    production_type: ProductionType
    queue_revision: datetime | None
    current_colour_changeovers: int
    proposed_colour_changeovers: int
    # current − proposed; > 0 means the proposal removes that many colour changes (drives the banner).
    colour_changeover_reduction: int
    proposed_order: list[WorkOrderRead]