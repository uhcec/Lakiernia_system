from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.manager.capacity import ShiftLength
from app.manager.enums import DEFAULT_RULE_ORDER, ScheduleRuleKey
from app.manager.paint_feasibility import PaintFeasibilityStatus
from app.process.enums import CoatingType, ProcessStage, ProductionType
from app.shared.enums import PlanningPriority
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


class WorkOrderPlanningPriorityUpdateRequest(BaseModel):
    # The manager planning lock to set, or None to clear it (NA49.K). PINNED keeps the order in its
    # current queue slot when the auto-scheduler re-optimises; URGENT forces it to the front of the line.
    planning_priority: PlanningPriority | None = None

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


class LineRateMeasurement(BaseModel):
    """Effective automatic line throughput learned from the stage-transition log (N49-2).

    ``effective_rate_m2_per_h`` is the number the day-capacity planner consumes: the measured rate once
    enough passes are bracketed, otherwise the seed. ``measured_rate_m2_per_h`` is ``None`` until the
    sample is large enough, and ``is_measured`` says which of the two ``effective`` reflects.
    """

    sample_order_count: int
    observed_m2: float
    # Wall-clock hours the line was occupied (union of the bracketed passes, overlaps counted once).
    active_hours: float
    measured_rate_m2_per_h: float | None
    seed_rate_m2_per_h: float
    effective_rate_m2_per_h: float
    is_measured: bool


class ColourChangeoverMeasurement(BaseModel):
    """Statistical colour-changeover cost learned from the log, with the confirmed band seed (N49-2).

    ``estimated_changeover_minutes`` is what the planner consumes (measured residual once enough pairs
    are seen, else the seed midpoint). The structural ``band_*`` fields are the confirmed 15/30-min
    bands keyed off the 100 m² odzysk threshold — reference for a size-aware cost model (N49-6)."""

    same_colour_pair_count: int
    changed_colour_pair_count: int
    measured_changeover_minutes: float | None
    seed_changeover_minutes: float
    estimated_changeover_minutes: float
    is_measured: bool
    band_threshold_m2: float
    band_small_minutes: float
    band_large_minutes: float


class LineMeasurementStats(BaseModel):
    """The learned per-line numbers (rate + changeover) over a window — read-side of N49-2."""

    production_type: ProductionType
    date_from: date
    date_to: date
    rate: LineRateMeasurement
    changeover: ColourChangeoverMeasurement


class GoodDayMetricsRead(BaseModel):
    """One day measured against the capacity model's definition of a good day (NA50).

    Headline trio: ``output_m2`` vs the profitable ``floor_m2`` (``met_floor``), ``on_time_pct``
    (deadlines are hard), and the colour-``changeover_loss_m2`` capacity burned. Diagnostic:
    ``utilisation_pct`` / ``idle_hours`` ("fabryka nie stała"). The effective booth **rate** is a
    *period* figure (``GoodDayTotalsRead.rate_m2_per_h``), not per-day — a single day rarely has the
    ≥ 3 bracketed passes needed to measure it, so a per-day rate would just echo the seed (NA53).
    """

    day: date
    output_m2: float
    floor_m2: float
    met_floor: bool
    floor_shortfall_m2: float
    orders_completed: int
    orders_on_time: int
    on_time_pct: float | None
    changeover_count: int
    changeover_minutes_total: float
    changeover_loss_m2: float
    shift_hours: float
    active_hours: float
    idle_hours: float
    utilisation_pct: float | None


class GoodDayTotalsRead(BaseModel):
    days_count: int
    days_met_floor: int
    total_output_m2: float
    orders_completed: int
    orders_on_time: int
    on_time_pct: float | None
    total_changeover_count: int
    total_changeover_loss_m2: float
    avg_utilisation_pct: float | None
    # Effective booth rate over the whole period (measured once ≥ 3 passes are bracketed, else the seed) —
    # a period figure because a single day rarely has enough passes to measure it (NA53).
    rate_m2_per_h: float
    rate_is_measured: bool


class GoodDayStats(BaseModel):
    """Per-day good-day metrics for a line over a window, plus the period roll-up (NA50).

    ``floor_m2`` / ``shift_hours`` are the bar each day is measured against (the long-day full-shift
    constants — historical shift length is not yet persisted, see the service note);
    ``changeover_minutes_each`` is the learned per-change cost (N49-2) used to value the changeover loss.
    """

    production_type: ProductionType
    date_from: date
    date_to: date
    floor_m2: float
    shift_hours: float
    changeover_minutes_each: float
    changeover_is_measured: bool
    days: list[GoodDayMetricsRead]
    totals: GoodDayTotalsRead


class DayCapacityRead(BaseModel):
    """One working day as a capacity bucket — floor + ceiling + how the line's planned work fills it.

    Read-side of N49-3: the day-capacity foundation the multi-day placement (N49-4) and the capacity
    board (N49-9) build on. ``shift_advised`` is true when the shift length was derived from the
    available ready work rather than supplied by the caller. ``changeover_minutes`` is the **average
    per-change** cost folded into the net ceiling — size + direction-aware (N49-6): derived from the
    line's actual light→dark sweep (the 100 m² odzysk band × colour direction), not a flat constant.
    ``changeover_minutes_total`` is that sweep's full changeover cost.
    """

    production_type: ProductionType
    shift_length: ShiftLength
    shift_advised: bool
    shift_hours: float
    floor_m2: float
    ceiling_rate_m2_per_h: float
    gross_ceiling_m2: float
    net_ceiling_m2: float
    changeover_count: int
    changeover_minutes: float
    changeover_minutes_total: float
    changeover_loss_m2: float
    changeover_is_measured: bool
    placed_order_count: int
    placed_m2: float
    below_floor: bool
    over_ceiling: bool
    spill_m2: float
    headroom_m2: float


class OrderPlacementRead(BaseModel):
    """Where one order landed in the multi-day plan and whether that still ships it on time (N49-4).

    Within its day the orders are listed as a **light → dark colour sweep** (N49-5): ``sequence_position``
    is the order's 0-based slot in that sweep. ``suggested_production_type`` is the planner's proposed
    line (N49-8, small-m² colour-orphan → manual, else automatic) — a suggestion the manager can
    override; ``suggested_line_is_*`` expose the reason behind it.
    """

    work_order_id: int
    order_number: str
    customer_name: str
    ral_code: str | None
    total_area_m2: float | None
    # The order's CURRENT live queue position on its line (NA51) — lets the board show the manager's
    # actual running order alongside the suggested plan order, and apply the suggestion back to the queue.
    queue_position: int | None
    day_index: int
    # 0-based position within the day's light→dark sweep (N49-5).
    sequence_position: int
    scheduled_date: date | None
    planned_pickup_date: date
    meets_deadline: bool
    days_late: int
    # Suggested line (N49-8) — manager-overridable.
    suggested_production_type: ProductionType
    suggested_line_is_colour_orphan: bool
    suggested_line_is_small: bool
    # Paint-stock feasibility (N49-7): OK / WARNING (runs short or manual-used low-confidence) /
    # BLOCKED (metered colour out of stock — a hard block). ``paint_remaining_kg`` is the series stock
    # left after this order's cumulative demand (negative once overrun); None for an untracked colour.
    paint_status: PaintFeasibilityStatus = PaintFeasibilityStatus.OK
    paint_remaining_kg: float | None = None
    # Manager planning lock (NA49.K): PINNED / URGENT / None — surfaced so the board shows which orders
    # the manager has locked, since the auto-scheduler re-optimise respects them.
    planning_priority: PlanningPriority | None = None


class PlannedDayRead(BaseModel):
    """One working day in the multi-day plan: its capacity bucket and the orders placed in it (N49-4).

    ``placements`` are ordered as the day's **light → dark colour sweep** (N49-5). ``changeover_minutes``
    is the day's **size + direction-aware** total changeover cost for that sweep (N49-6) — identical
    colours cost zero, light→dark cheap, dark→light the full size band — not a flat per-change count.
    """

    day_index: int
    scheduled_date: date | None
    shift_length: ShiftLength
    floor_m2: float
    gross_ceiling_m2: float
    net_ceiling_m2: float
    changeover_count: int
    # Size + direction-aware total changeover minutes for the day's light→dark sweep (N49-6).
    changeover_minutes: float
    placed_order_count: int
    placed_m2: float
    below_floor: bool
    over_ceiling: bool
    placements: list[OrderPlacementRead]


class MultiDayPlanRead(BaseModel):
    """Deadline-feasible multi-day placement of a line's planned orders (N49-4, the planner heart).

    Lays the line's active planned orders across the next ``horizon_working_days`` working days,
    earliest-deadline-first, into net-ceiling-bounded day buckets (``app/manager/placement.py``).
    ``shift_advised`` is true when the shift length was derived from the available work rather than
    supplied; ``changeover_minutes`` is the learned per-change cost (N49-2) folded into each day's net
    ceiling. ``infeasible_order_ids`` is the "won't make it" set — orders whose scheduled day is past
    their hard pickup deadline or beyond the horizon.
    """

    production_type: ProductionType
    shift_length: ShiftLength
    shift_advised: bool
    horizon_working_days: int
    changeover_minutes: float
    changeover_is_measured: bool
    days: list[PlannedDayRead]
    infeasible_order_ids: list[int]
    # The line's queue snapshot the plan was built from (NA51) — the board echoes it back to
    # ``/manager/queue/reorder`` when the manager applies the suggested order, for stale-write protection.
    queue_revision: datetime | None


class OrderPaintFeasibilityRead(BaseModel):
    """One planned automatic order's paint-stock outlook in execution order (N49-7)."""

    work_order_id: int
    order_number: str
    customer_name: str
    ral_code: str | None
    colour_key: str | None
    demand_kg: float
    available_stock_kg: float
    cumulative_demand_kg: float
    # Series stock left after this order (negative once the series is overrun — "runs out here").
    remaining_after_kg: float
    is_tracked: bool
    # Colour also painted on the unmetered manual line → low-confidence balance (warn, never block).
    manual_used: bool
    status: PaintFeasibilityStatus


class PaintForwardViewRead(BaseModel):
    """Forward "paint suffices / runs out at order X" view for a line's planned work (N49-7).

    Orders are listed in execution (queue) order — the point at which a colour series runs dry is
    sequence-dependent. ``blocked_order_ids`` is the hard-block set (metered colour out of stock);
    ``warning_order_ids`` is the runs-short / manual-used low-confidence set.
    """

    production_type: ProductionType
    orders: list[OrderPaintFeasibilityRead]
    blocked_order_ids: list[int]
    warning_order_ids: list[int]


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