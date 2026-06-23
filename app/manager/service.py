import json
from datetime import UTC, date, datetime
from typing import Literal
from threading import RLock

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError

from app.audit.context import StationContext, ensure_station_allowed
from app.audit.models import AuditEvent
from app.audit.repository import AuditRepository
from app.paints.repository import PaintRepository
from app.paints.service import PaintService
from app.process.enums import CoatingType, ProcessDisplayStatus, ProductionType
from app.process.models import StageTransitionEvent, WorkOrderStageState
from app.process.repository import ProcessRepository
from app.process.service import ProcessService
from app.manager.repository import ManagerRepository
from app.manager.schemas import (
    CorrectionReasonReportItem,
    CycleTimeBreakdown,
    CycleTimeSegment,
    CycleTimeStats,
    StageCycleTime,
    ThroughputPeriod,
    ThroughputStats,
    WipAgingBreakdown,
    WipAgingItem,
    WipAgingSegment,
    WipAgingStats,
    WorkOrderPlanAssignRequest,
    WorkOrderProductionTypeUpdateRequest,
    WorkOrderQueuePositionUpdateRequest,
    WorkOrderQueueReorderBatchRequest,
    WorkOrderQueueReorderRequest,
)
from app.process.enums import ProcessStage, QuantityBatchType, StageStatus
from app.shared.enums import StationId
from app.shared.exceptions import InvalidManagerPlanningError, ResourceNotFoundError
from app.work_orders.models import WorkOrder
from app.work_orders.schemas import WorkOrderRead
from app.work_orders.schemas import (
    WorkOrderQuantityBatchRead,
    WorkOrderRelationSummaryRead,
    WorkOrderStageStateRead,
    calculate_paint_shortage_quantity_kg,
    calculate_predicted_paint_quantity_kg,
    build_coating_type_view,
    build_queue_namespace_view,
    build_process_stage_view,
    build_process_status_view,
    build_production_type_view,
    build_quantity_batch_type_view,
    build_stage_status_info_view,
    build_work_order_relation_summary,
    build_work_order_kind_view,
)
from app.work_orders.service import WorkOrderService


_QUEUE_MUTATION_LOCK = RLock()

# Canonical stage order + Polish labels for the cycle-time / bottleneck report.
_STAGE_DISPLAY_ORDER: tuple[ProcessStage, ...] = (
    ProcessStage.SURFACE_PREPARATION,
    ProcessStage.HANGING,
    ProcessStage.PRODUCTION,
    ProcessStage.PACKING,
    ProcessStage.DECORAL_PRODUCTION,
)
_STAGE_LABELS_PL: dict[ProcessStage, str] = {
    ProcessStage.SURFACE_PREPARATION: "Przygotowanie powierzchni",
    ProcessStage.HANGING: "Zawieszanie",
    ProcessStage.PRODUCTION: "Produkcja",
    ProcessStage.PACKING: "Pakowanie",
    ProcessStage.DECORAL_PRODUCTION: "Decoral",
}

# Two independent cross-sections every production stat is split along (NA23): by production method
# and by order coating. Each is a full partition of any order cohort (an order is exactly one method
# and exactly one coating), so segment values reconcile to the whole — see FACTORY_DOMAIN_MODEL §4.1.
_METHOD_SEGMENTS: tuple[tuple[str, str, ProductionType], ...] = (
    ("manual", "Ręczna", ProductionType.MANUAL),
    ("automatic", "Automat", ProductionType.AUTOMATIC),
)
_COATING_SEGMENTS: tuple[tuple[str, str, CoatingType], ...] = (
    ("ral_only", "Czysty RAL", CoatingType.RAL),
    ("decoral", "Decoral", CoatingType.DECORAL),
)


def _order_segment_keys(
    production_type: ProductionType | None, coating_type: CoatingType | None
) -> list[str]:
    """The breakdown buckets a single order contributes to (one method + one coating, when known)."""
    keys: list[str] = []
    for key, _label, value in _METHOD_SEGMENTS:
        if production_type == value:
            keys.append(key)
    for key, _label, value in _COATING_SEGMENTS:
        if coating_type == value:
            keys.append(key)
    return keys


def _as_naive_utc(value: datetime) -> datetime:
    """Normalize a datetime to naive UTC so log/now timestamps subtract cleanly.

    SQLite returns naive datetimes even for tz-aware columns, while ``datetime.now(UTC)`` is aware;
    coercing both avoids "can't subtract offset-naive and offset-aware" errors.
    """
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


class ManagerService:
    def __init__(self, repository: ManagerRepository) -> None:
        self.repository = repository
        self.process_service = ProcessService(ProcessRepository(repository.session))
        self.paint_service = PaintService(PaintRepository(repository.session))
        self.audit_repository = AuditRepository(repository.session)

    def _get_current_paint_stock_quantity_kg(self, work_order: WorkOrder) -> float | None:
        if not work_order.ral_code or not work_order.paint_producer or not work_order.paint_code:
            return None
        return self.paint_service.lookup_current_stock(
            ral_code=work_order.ral_code,
            paint_producer=work_order.paint_producer,
            paint_code=work_order.paint_code,
        ).current_quantity_kg

    def list_unplanned_work_orders(self) -> list[WorkOrderRead]:
        return [self._to_read_model(work_order) for work_order in self.repository.list_unplanned_work_orders()]

    def list_planned_work_orders(self) -> list[WorkOrderRead]:
        return [self._to_read_model(work_order) for work_order in self.repository.list_planned_work_orders()]

    def get_correction_reason_report(
        self, station_context: StationContext | None = None
    ) -> list[CorrectionReasonReportItem]:
        self._ensure_stats_viewer(station_context)
        return [
            CorrectionReasonReportItem(
                correction_reason_category=category,
                work_order_count=work_order_count,
                total_correction_quantity=total_correction_quantity,
            )
            for category, work_order_count, total_correction_quantity in self.repository.list_correction_reason_report()
        ]

    def get_throughput_stats(
        self,
        date_from: date,
        date_to: date,
        group_by: Literal["day", "week", "month"] = "day",
        station_context: StationContext | None = None,
    ) -> ThroughputStats:
        self._ensure_stats_viewer(station_context)
        session = self.repository.session
        # Week uses ISO year/week (%G-%V) so grouping matches date.fromisocalendar in
        # _parse_period_start; mixing %W (non-ISO) with fromisocalendar drifted around
        # year boundaries (NA7). Requires SQLite >= 3.46 for %G/%V.
        date_fmt = {"day": "%Y-%m-%d", "week": "%G-%V", "month": "%Y-%m"}[group_by]

        # Attribute packing throughput to the moment PACKING was completed. The durable source is
        # the append-only stage-transition log (occurred_at is never overwritten); we take the
        # latest PACKING->DONE event per order (corrections can re-complete packing). For orders
        # packed before this log existed (or rows built directly in tests), fall back to the stage
        # state's updated_at via COALESCE so historical data still counts.
        packing_done_events = (
            select(
                StageTransitionEvent.work_order_id,
                func.max(StageTransitionEvent.occurred_at).label("event_done_at"),
            )
            .where(
                StageTransitionEvent.stage == ProcessStage.PACKING,
                StageTransitionEvent.status == StageStatus.DONE,
            )
            .group_by(StageTransitionEvent.work_order_id)
            .subquery()
        )

        packing_done = (
            select(
                WorkOrderStageState.work_order_id,
                func.coalesce(
                    packing_done_events.c.event_done_at,
                    WorkOrderStageState.updated_at,
                ).label("packing_done_at"),
            )
            .join(
                packing_done_events,
                packing_done_events.c.work_order_id == WorkOrderStageState.work_order_id,
                isouter=True,
            )
            .where(
                WorkOrderStageState.stage == ProcessStage.PACKING,
                WorkOrderStageState.status == StageStatus.DONE,
            )
            .subquery()
        )

        period_expr = func.strftime(date_fmt, packing_done.c.packing_done_at)

        throughput_rows = session.execute(
            select(
                period_expr.label("period"),
                # Base-production throughput is split purely by production type, so a DECORAL
                # order's base coat counts toward manual/automatic just like RAL. The Decoral
                # pass itself (DECORAL_PRODUCTION) is a separate, additional series attributed at
                # its own completion date (decoral_by_period below), not a slice of this query.
                func.sum(
                    case(
                        (
                            WorkOrder.production_type == ProductionType.MANUAL,
                            func.coalesce(WorkOrder.total_area_m2, 0.0),
                        ),
                        else_=0.0,
                    )
                ).label("m2_manual"),
                func.sum(
                    case(
                        (
                            WorkOrder.production_type == ProductionType.AUTOMATIC,
                            func.coalesce(WorkOrder.total_area_m2, 0.0),
                        ),
                        else_=0.0,
                    )
                ).label("m2_automatic"),
                # Coating partition of the same base-coat total (each order counted once): a decoral
                # order's area lands on the decoral side, a RAL order's on the RAL-only side, so
                # m2_ral_only + m2_decoral(product) == m2_total. This is NOT the decoral pass workload
                # (that is decoral_by_period below, attributed at DECORAL_PRODUCTION completion).
                func.sum(
                    case(
                        (
                            WorkOrder.coating_type == CoatingType.RAL,
                            func.coalesce(WorkOrder.total_area_m2, 0.0),
                        ),
                        else_=0.0,
                    )
                ).label("m2_ral_only"),
                func.sum(
                    case(
                        (
                            WorkOrder.coating_type == CoatingType.DECORAL,
                            func.coalesce(WorkOrder.total_area_m2, 0.0),
                        ),
                        else_=0.0,
                    )
                ).label("m2_decoral_product"),
                func.sum(func.coalesce(WorkOrder.total_area_m2, 0.0)).label("m2_total"),
                func.count(WorkOrder.id).label("orders_count"),
            )
            .join(packing_done, WorkOrder.id == packing_done.c.work_order_id)
            .where(
                WorkOrder.is_correction == False,  # noqa: E712
                func.date(packing_done.c.packing_done_at) >= date_from,
                func.date(packing_done.c.packing_done_at) <= date_to,
            )
            .group_by(period_expr)
            .order_by(period_expr)
        ).all()

        # Corrections are read from the SINGLE shared correction-event source
        # (ManagerRepository.correction_events_select) so the chart and the reason report can never
        # drift (NA4). It already unions both origins (CORRECTION batches + child "P" orders); here we
        # just aggregate it by period over the requested window.
        corrections_by_period: dict[str, list[int]] = {}

        def _add_corrections(period: str, pieces: int, events: int) -> None:
            bucket = corrections_by_period.setdefault(period, [0, 0])
            bucket[0] += pieces
            bucket[1] += events

        correction_events = self.repository.correction_events_select()
        correction_period_expr = func.strftime(date_fmt, correction_events.c.created_at)
        correction_rows = session.execute(
            select(
                correction_period_expr.label("period"),
                func.coalesce(func.sum(correction_events.c.quantity), 0).label("pieces"),
                func.count().label("events"),
            )
            .where(
                func.date(correction_events.c.created_at) >= date_from,
                func.date(correction_events.c.created_at) <= date_to,
            )
            .group_by(correction_period_expr)
        ).all()
        for row in correction_rows:
            _add_corrections(row.period, int(row.pieces or 0), int(row.events))

        without_m2_count = session.execute(
            select(func.count(WorkOrder.id))
            .join(packing_done, WorkOrder.id == packing_done.c.work_order_id)
            .where(
                WorkOrder.is_correction == False,  # noqa: E712
                func.date(packing_done.c.packing_done_at) >= date_from,
                func.date(packing_done.c.packing_done_at) <= date_to,
                WorkOrder.total_area_m2.is_(None),
            )
        ).scalar() or 0

        # Decoral-pass m² is a separate, additional series (not a slice of base production):
        # the same parts get a base RAL coat (counted at packing, above) and then a Decoral
        # coating on the DECORAL_PRODUCTION stage afterwards. We attribute it to the actual pass
        # completion via the stage-transition log (latest DECORAL_PRODUCTION->DONE occurred_at),
        # using the order's total_area_m2. Like the base coat, only non-correction orders count.
        # There is no updated_at fallback here: the pass date is only reliable from the log, and
        # this intentionally replaces the old packing-time approximation, so passes completed
        # before the log existed simply do not appear.
        decoral_done_events = (
            select(
                StageTransitionEvent.work_order_id,
                func.max(StageTransitionEvent.occurred_at).label("event_done_at"),
            )
            .where(
                StageTransitionEvent.stage == ProcessStage.DECORAL_PRODUCTION,
                StageTransitionEvent.status == StageStatus.DONE,
            )
            .group_by(StageTransitionEvent.work_order_id)
            .subquery()
        )
        decoral_period_expr = func.strftime(date_fmt, decoral_done_events.c.event_done_at)
        decoral_rows = session.execute(
            select(
                decoral_period_expr.label("period"),
                func.sum(func.coalesce(WorkOrder.total_area_m2, 0.0)).label("m2_decoral"),
            )
            .join(decoral_done_events, WorkOrder.id == decoral_done_events.c.work_order_id)
            .where(
                WorkOrder.is_correction == False,  # noqa: E712
                func.date(decoral_done_events.c.event_done_at) >= date_from,
                func.date(decoral_done_events.c.event_done_at) <= date_to,
            )
            .group_by(decoral_period_expr)
        ).all()
        decoral_by_period = {row.period: float(row.m2_decoral or 0.0) for row in decoral_rows}

        throughput_by_period = {row.period: row for row in throughput_rows}
        all_period_keys = sorted(set(throughput_by_period) | set(corrections_by_period) | set(decoral_by_period))

        periods: list[ThroughputPeriod] = []
        for key in all_period_keys:
            t = throughput_by_period.get(key)
            c = corrections_by_period.get(key)
            periods.append(
                ThroughputPeriod(
                    period_start=_parse_period_start(key, group_by),
                    period_label=_format_period_label(key, group_by),
                    m2_manual=round(float(t.m2_manual) if t else 0.0, 2),
                    m2_automatic=round(float(t.m2_automatic) if t else 0.0, 2),
                    m2_ral_only=round(float(t.m2_ral_only) if t else 0.0, 2),
                    m2_decoral=round(float(t.m2_decoral_product) if t else 0.0, 2),
                    m2_decoral_pass=round(decoral_by_period.get(key, 0.0), 2),
                    m2_total=round(float(t.m2_total) if t else 0.0, 2),
                    orders_count=int(t.orders_count) if t else 0,
                    correction_pieces=c[0] if c else 0,
                    correction_orders_count=c[1] if c else 0,
                )
            )

        totals = ThroughputPeriod(
            period_start=date_from,
            period_label="Razem",
            m2_manual=round(sum(p.m2_manual for p in periods), 2),
            m2_automatic=round(sum(p.m2_automatic for p in periods), 2),
            m2_ral_only=round(sum(p.m2_ral_only for p in periods), 2),
            m2_decoral=round(sum(p.m2_decoral for p in periods), 2),
            m2_decoral_pass=round(sum(p.m2_decoral_pass for p in periods), 2),
            m2_total=round(sum(p.m2_total for p in periods), 2),
            orders_count=sum(p.orders_count for p in periods),
            correction_pieces=sum(p.correction_pieces for p in periods),
            correction_orders_count=sum(p.correction_orders_count for p in periods),
        )

        return ThroughputStats(periods=periods, totals=totals, orders_without_m2_count=without_m2_count)

    def get_cycle_time_stats(
        self,
        date_from: date,
        date_to: date,
        station_context: StationContext | None = None,
    ) -> CycleTimeStats:
        """Average active processing time per stage, derived from the stage-transition log.

        Cohort: non-correction work orders whose latest ``PACKING``->``DONE`` falls in
        ``[date_from, date_to]`` (the same "completed in window" cohort as throughput). For each
        order and stage we measure the **most recent completed pass** — the gap from the latest
        ``IN_PROGRESS`` to the latest ``DONE`` (at or after it) of that stage — so correction
        re-runs report the final pass rather than a sum. ``overall_average_seconds`` is the average
        production lead time per order (earliest stage ``IN_PROGRESS`` to the packing ``DONE``).
        Bottleneck visibility for managers; reads only the append-only log so values are durable.
        """
        self._ensure_stats_viewer(station_context)
        session = self.repository.session

        packing_done_events = (
            select(
                StageTransitionEvent.work_order_id,
                func.max(StageTransitionEvent.occurred_at).label("packing_done_at"),
            )
            .where(
                StageTransitionEvent.stage == ProcessStage.PACKING,
                StageTransitionEvent.status == StageStatus.DONE,
            )
            .group_by(StageTransitionEvent.work_order_id)
            .subquery()
        )
        cohort_ids = [
            row.work_order_id
            for row in session.execute(
                select(packing_done_events.c.work_order_id)
                .join(WorkOrder, WorkOrder.id == packing_done_events.c.work_order_id)
                .where(
                    WorkOrder.is_correction == False,  # noqa: E712
                    func.date(packing_done_events.c.packing_done_at) >= date_from,
                    func.date(packing_done_events.c.packing_done_at) <= date_to,
                )
            ).all()
        ]

        if not cohort_ids:
            return CycleTimeStats(
                date_from=date_from,
                date_to=date_to,
                orders_count=0,
                overall_average_seconds=None,
                stages=[],
            )

        # Per-order method/coating so each stage average can be cut into the two cross-sections (NA23).
        order_meta: dict[int, tuple[ProductionType | None, CoatingType | None]] = {
            row.id: (row.production_type, row.coating_type)
            for row in session.execute(
                select(WorkOrder.id, WorkOrder.production_type, WorkOrder.coating_type).where(
                    WorkOrder.id.in_(cohort_ids)
                )
            ).all()
        }

        events = session.execute(
            select(
                StageTransitionEvent.work_order_id,
                StageTransitionEvent.stage,
                StageTransitionEvent.status,
                StageTransitionEvent.occurred_at,
            )
            .where(StageTransitionEvent.work_order_id.in_(cohort_ids))
            .order_by(StageTransitionEvent.work_order_id, StageTransitionEvent.occurred_at)
        ).all()

        # work_order_id -> stage -> {"IN_PROGRESS": [datetimes], "DONE": [datetimes]}
        per_order: dict[int, dict[ProcessStage, dict[StageStatus, list[datetime]]]] = {}
        for event in events:
            stage_map = per_order.setdefault(event.work_order_id, {})
            status_map = stage_map.setdefault(event.stage, {})
            status_map.setdefault(event.status, []).append(event.occurred_at)

        stage_total_seconds: dict[ProcessStage, float] = {}
        stage_order_counts: dict[ProcessStage, int] = {}
        stage_wait_seconds: dict[ProcessStage, float] = {}
        stage_wait_counts: dict[ProcessStage, int] = {}
        # Per-segment accumulators for the two cross-sections (keyed by (stage, segment) / segment).
        stage_seg_total: dict[tuple[ProcessStage, str], float] = {}
        stage_seg_count: dict[tuple[ProcessStage, str], int] = {}
        lead_seg_total: dict[str, float] = {}
        lead_seg_count: dict[str, int] = {}
        lead_time_seconds_total = 0.0
        lead_time_orders = 0

        for work_order_id, stage_map in per_order.items():
            production_type, coating_type = order_meta.get(work_order_id, (None, None))
            seg_keys = _order_segment_keys(production_type, coating_type)
            earliest_in_progress: datetime | None = None
            for occurrences in stage_map.values():
                for ip in occurrences.get(StageStatus.IN_PROGRESS, []):
                    if earliest_in_progress is None or ip < earliest_in_progress:
                        earliest_in_progress = ip

            # Most-recent completed pass per stage as a (start, end) interval.
            intervals: dict[ProcessStage, tuple[datetime, datetime]] = {}
            for stage, occurrences in stage_map.items():
                done_times = occurrences.get(StageStatus.DONE, [])
                in_progress_times = occurrences.get(StageStatus.IN_PROGRESS, [])
                if not done_times or not in_progress_times:
                    continue
                last_done = max(done_times)
                candidate_starts = [ip for ip in in_progress_times if ip <= last_done]
                if not candidate_starts:
                    continue
                intervals[stage] = (max(candidate_starts), last_done)

            for stage, (start, end) in intervals.items():
                duration = (end - start).total_seconds()
                if duration >= 0:
                    stage_total_seconds[stage] = stage_total_seconds.get(stage, 0.0) + duration
                    stage_order_counts[stage] = stage_order_counts.get(stage, 0) + 1
                    for seg_key in seg_keys:
                        stage_seg_total[(stage, seg_key)] = stage_seg_total.get((stage, seg_key), 0.0) + duration
                        stage_seg_count[(stage, seg_key)] = stage_seg_count.get((stage, seg_key), 0) + 1

                # Queue wait before this stage = time from the most recent stage that finished
                # before this one started, to this stage's start. Robust for automatic flows (where
                # PRODUCTION/PACKING start implicitly at hanging finish) because it keys off "the last
                # stage that actually completed before the start", not the workflow's nominal order.
                prior_ends = [
                    other_end
                    for other_stage, (_, other_end) in intervals.items()
                    if other_stage != stage and other_end <= start
                ]
                if prior_ends:
                    wait = (start - max(prior_ends)).total_seconds()
                    if wait >= 0:
                        stage_wait_seconds[stage] = stage_wait_seconds.get(stage, 0.0) + wait
                        stage_wait_counts[stage] = stage_wait_counts.get(stage, 0) + 1

            packing_done_times = stage_map.get(ProcessStage.PACKING, {}).get(StageStatus.DONE, [])
            if packing_done_times and earliest_in_progress is not None:
                lead = (max(packing_done_times) - earliest_in_progress).total_seconds()
                if lead >= 0:
                    lead_time_seconds_total += lead
                    lead_time_orders += 1
                    for seg_key in seg_keys:
                        lead_seg_total[seg_key] = lead_seg_total.get(seg_key, 0.0) + lead
                        lead_seg_count[seg_key] = lead_seg_count.get(seg_key, 0) + 1

        def _segment(total: float, count: int, key: str, label: str) -> CycleTimeSegment | None:
            if not count:
                return None
            return CycleTimeSegment(
                key=key,
                label=label,
                average_seconds=round(total / count, 1),
                total_seconds=round(total, 1),
                orders_count=count,
            )

        def _stage_breakdown(stage: ProcessStage) -> CycleTimeBreakdown:
            return CycleTimeBreakdown(
                by_method=[
                    seg
                    for key, label, _ in _METHOD_SEGMENTS
                    if (seg := _segment(stage_seg_total.get((stage, key), 0.0), stage_seg_count.get((stage, key), 0), key, label))
                ],
                by_coating=[
                    seg
                    for key, label, _ in _COATING_SEGMENTS
                    if (seg := _segment(stage_seg_total.get((stage, key), 0.0), stage_seg_count.get((stage, key), 0), key, label))
                ],
            )

        stages = [
            StageCycleTime(
                stage=stage,
                stage_label=_STAGE_LABELS_PL[stage],
                average_seconds=round(stage_total_seconds[stage] / stage_order_counts[stage], 1),
                total_seconds=round(stage_total_seconds[stage], 1),
                orders_count=stage_order_counts[stage],
                average_wait_before_seconds=(
                    round(stage_wait_seconds[stage] / stage_wait_counts[stage], 1)
                    if stage_wait_counts.get(stage)
                    else None
                ),
                wait_orders_count=stage_wait_counts.get(stage, 0),
                breakdown=_stage_breakdown(stage),
            )
            for stage in _STAGE_DISPLAY_ORDER
            if stage_order_counts.get(stage)
        ]

        overall_average = (
            round(lead_time_seconds_total / lead_time_orders, 1) if lead_time_orders else None
        )
        overall_breakdown = CycleTimeBreakdown(
            by_method=[
                seg
                for key, label, _ in _METHOD_SEGMENTS
                if (seg := _segment(lead_seg_total.get(key, 0.0), lead_seg_count.get(key, 0), key, label))
            ],
            by_coating=[
                seg
                for key, label, _ in _COATING_SEGMENTS
                if (seg := _segment(lead_seg_total.get(key, 0.0), lead_seg_count.get(key, 0), key, label))
            ],
        )

        return CycleTimeStats(
            date_from=date_from,
            date_to=date_to,
            orders_count=len(cohort_ids),
            overall_average_seconds=overall_average,
            stages=stages,
            overall_breakdown=overall_breakdown,
        )

    def get_work_in_progress_aging(
        self,
        station_context: StationContext | None = None,
        now: datetime | None = None,
    ) -> WipAgingStats:
        """Live "stuck orders" view: work currently IN_PROGRESS, by how long it has sat there.

        Cohort is taken from the **live** ``WorkOrderStageState`` rows that are actually
        ``IN_PROGRESS`` (so a correction reset can never leave a stale "stuck" row), one row per
        order at its furthest-advanced in-progress stage. The age timestamp comes from the durable
        stage-transition log (latest ``IN_PROGRESS`` event for that order+stage), falling back to the
        stage state's ``updated_at`` when no log row exists. Manager/admin only; read-only.
        """
        self._ensure_stats_viewer(station_context)
        session = self.repository.session
        reference_now = now or datetime.now(UTC)

        rows = session.execute(
            select(WorkOrderStageState, WorkOrder)
            .join(WorkOrder, WorkOrder.id == WorkOrderStageState.work_order_id)
            .where(WorkOrderStageState.status == StageStatus.IN_PROGRESS)
        ).all()

        # One entry per order: the furthest-advanced stage currently IN_PROGRESS (automatic orders
        # have PRODUCTION + PACKING both in progress; the later stage is the meaningful one).
        chosen: dict[int, tuple[WorkOrderStageState, WorkOrder]] = {}
        for stage_state, work_order in rows:
            if stage_state.stage not in _STAGE_DISPLAY_ORDER:
                continue
            existing = chosen.get(work_order.id)
            if existing is None or _STAGE_DISPLAY_ORDER.index(stage_state.stage) > _STAGE_DISPLAY_ORDER.index(
                existing[0].stage
            ):
                chosen[work_order.id] = (stage_state, work_order)

        if not chosen:
            return WipAgingStats(generated_at=reference_now, items=[])

        event_at: dict[tuple[int, ProcessStage], datetime] = {
            (row.work_order_id, row.stage): row.started_at
            for row in session.execute(
                select(
                    StageTransitionEvent.work_order_id,
                    StageTransitionEvent.stage,
                    func.max(StageTransitionEvent.occurred_at).label("started_at"),
                )
                .where(
                    StageTransitionEvent.status == StageStatus.IN_PROGRESS,
                    StageTransitionEvent.work_order_id.in_(list(chosen)),
                )
                .group_by(StageTransitionEvent.work_order_id, StageTransitionEvent.stage)
            ).all()
        }

        items: list[WipAgingItem] = []
        for work_order_id, (stage_state, work_order) in chosen.items():
            started_at = event_at.get((work_order_id, stage_state.stage), stage_state.updated_at)
            age_seconds = (_as_naive_utc(reference_now) - _as_naive_utc(started_at)).total_seconds()
            items.append(
                WipAgingItem(
                    work_order_id=work_order_id,
                    order_number=work_order.order_number,
                    customer_name=work_order.customer_name,
                    stage=stage_state.stage,
                    stage_label=_STAGE_LABELS_PL[stage_state.stage],
                    production_type=work_order.production_type,
                    coating_type=work_order.coating_type,
                    queue_position=work_order.queue_position,
                    age_seconds=round(max(age_seconds, 0.0), 1),
                )
            )

        items.sort(key=lambda item: item.age_seconds, reverse=True)

        # Live cohort cut the same two independent ways as the other production stats (NA23): how many
        # in-progress orders are manual vs automatic, and czysty RAL vs decoral — each summing to len(items).
        def _wip_segments(
            segments: tuple[tuple[str, str, object], ...], attribute: str
        ) -> list[WipAgingSegment]:
            result: list[WipAgingSegment] = []
            for key, label, value in segments:
                count = sum(1 for item in items if getattr(item, attribute) == value)
                if count:
                    result.append(WipAgingSegment(key=key, label=label, orders_count=count))
            return result

        breakdown = WipAgingBreakdown(
            by_method=_wip_segments(_METHOD_SEGMENTS, "production_type"),
            by_coating=_wip_segments(_COATING_SEGMENTS, "coating_type"),
        )
        return WipAgingStats(generated_at=reference_now, items=items, breakdown=breakdown)

    def assign_plan(
        self,
        work_order_id: int,
        payload: WorkOrderPlanAssignRequest,
        station_context: StationContext | None = None,
    ) -> WorkOrderRead:
        self._ensure_manager_station_action(station_context)
        with _QUEUE_MUTATION_LOCK:
            work_order = self._get_existing_work_order(work_order_id)
            if self._is_planned(work_order):
                raise InvalidManagerPlanningError(f"Work order {work_order_id} is already planned.")
            if self._has_incomplete_marker(work_order):
                raise InvalidManagerPlanningError("Cannot plan incomplete order. Mark as complete first.")

            production_type = payload.production_type
            # No explicit position → append to the end of this line's active queue. An explicit
            # position is still honoured (seeds/tests), validated within the line.
            if payload.queue_position is not None:
                target_position = payload.queue_position
                self._ensure_queue_position_available_or_releasable(target_position, production_type)
            else:
                target_position = self._next_active_queue_position_for_line(production_type)

            now = datetime.now(UTC)
            completed_work_orders_to_trail = self._get_completed_work_orders_requiring_trailing(
                production_type=production_type,
                reserved_queue_positions=[target_position],
            )
            self._temporarily_move_queue_rows_out_of_the_way(
                completed_work_orders_to_trail,
                production_type=production_type,
                reserved_queue_positions=[target_position],
                now=now,
            )

            work_order.production_type = production_type
            work_order.queue_position = target_position
            work_order.updated_at = now
            # Reconcile the stage-state rows to the (now-known) route FIRST, so correction replanning
            # below resets statuses on the rows the route actually has (NA42).
            self.process_service.reconcile_stage_states_to_route(work_order)
            self.process_service.prepare_correction_work_order_for_planning(work_order)
            self.repository.session.flush()
            self._trail_completed_work_orders(
                completed_work_orders_to_trail, production_type=production_type, now=now
            )
            self._record_audit_event(
                event_type="manager.plan_assigned",
                station_context=station_context,
                work_order=work_order,
                target_type="work_order",
                target_id=work_order.id,
                summary=f"Assigned plan for work order {work_order.order_number}.",
                details={
                    "production_type": production_type.value,
                    "queue_position": target_position,
                },
            )

            try:
                self.repository.commit()
            except IntegrityError as exc:
                self.repository.rollback()
                raise InvalidManagerPlanningError(
                    f"Queue position {target_position} is already taken."
                ) from exc
            except Exception:
                self.repository.rollback()
                raise

            return self._to_read_model(work_order)

    def update_queue_position(
        self,
        work_order_id: int,
        payload: WorkOrderQueuePositionUpdateRequest,
        station_context: StationContext | None = None,
    ) -> WorkOrderRead:
        self._ensure_manager_station_action(station_context)
        with _QUEUE_MUTATION_LOCK:
            work_order = self._get_existing_work_order(work_order_id)
            if not self._is_planned(work_order):
                raise InvalidManagerPlanningError(f"Work order {work_order_id} must be planned before updating queue position.")
            if self.process_service.get_display_status(work_order) == ProcessDisplayStatus.READY:
                raise InvalidManagerPlanningError("Completed work orders cannot be moved in the active queue.")
            production_type = work_order.production_type
            self._ensure_queue_position_available_or_releasable(
                payload.queue_position,
                production_type,
                exclude_work_order_id=work_order_id,
            )

            now = datetime.now(UTC)
            completed_work_orders_to_trail = self._get_completed_work_orders_requiring_trailing(
                production_type=production_type,
                reserved_queue_positions=[payload.queue_position],
                exclude_work_order_id=work_order_id,
            )
            self._temporarily_move_queue_rows_out_of_the_way(
                completed_work_orders_to_trail,
                production_type=production_type,
                reserved_queue_positions=[payload.queue_position],
                now=now,
            )

            previous_queue_position = work_order.queue_position
            work_order.queue_position = payload.queue_position
            work_order.updated_at = now
            self.repository.session.flush()
            self._trail_completed_work_orders(
                completed_work_orders_to_trail, production_type=production_type, now=now
            )
            self._record_audit_event(
                event_type="manager.queue_position_updated",
                station_context=station_context,
                work_order=work_order,
                target_type="work_order",
                target_id=work_order.id,
                summary=f"Updated queue position for work order {work_order.order_number}.",
                details={
                    "previous_queue_position": previous_queue_position,
                    "queue_position": payload.queue_position,
                },
            )

            try:
                self.repository.commit()
            except IntegrityError as exc:
                self.repository.rollback()
                raise InvalidManagerPlanningError(
                    f"Queue position {payload.queue_position} is already taken."
                ) from exc
            except Exception:
                self.repository.rollback()
                raise

            return self._to_read_model(work_order)

    def update_production_type(
        self,
        work_order_id: int,
        payload: WorkOrderProductionTypeUpdateRequest,
        station_context: StationContext | None = None,
    ) -> WorkOrderRead:
        self._ensure_manager_station_action(station_context)
        with _QUEUE_MUTATION_LOCK:
            work_order = self._get_existing_work_order(work_order_id)
            if not self._is_planned(work_order):
                raise InvalidManagerPlanningError(f"Work order {work_order_id} must be planned before changing production type.")
            if work_order.production_type == payload.production_type:
                return self._to_read_model(work_order)
            self._ensure_production_not_started(work_order)

            previous_production_type = work_order.production_type
            previous_queue_position = work_order.queue_position
            target_production_type = payload.production_type
            # Compute the append slot on the target line and resolve any trailing-completed
            # shuffle BEFORE mutating this order, so the position queries don't autoflush it
            # into the new line and collide on the per-line (production_type, queue_position)
            # unique index. The order still sits on the source line at this point.
            target_position = self._next_active_queue_position_for_line(target_production_type)
            now = datetime.now(UTC)
            completed_work_orders_to_trail = self._get_completed_work_orders_requiring_trailing(
                production_type=target_production_type,
                reserved_queue_positions=[target_position],
            )
            self._temporarily_move_queue_rows_out_of_the_way(
                completed_work_orders_to_trail,
                production_type=target_production_type,
                reserved_queue_positions=[target_position],
                now=now,
            )

            work_order.production_type = target_production_type
            work_order.queue_position = target_position
            work_order.updated_at = now
            # Reconcile the stage-state rows to the (now-known) route FIRST, so correction replanning
            # below resets statuses on the rows the route actually has (NA42).
            self.process_service.reconcile_stage_states_to_route(work_order)
            self.process_service.prepare_correction_work_order_for_planning(work_order)
            self.repository.session.flush()
            self._trail_completed_work_orders(
                completed_work_orders_to_trail, production_type=target_production_type, now=now
            )
            self._record_audit_event(
                event_type="manager.production_type_changed",
                station_context=station_context,
                work_order=work_order,
                target_type="work_order",
                target_id=work_order.id,
                summary=f"Changed production type for work order {work_order.order_number}.",
                details={
                    "previous_production_type": previous_production_type.value if previous_production_type else None,
                    "production_type": target_production_type.value,
                    "previous_queue_position": previous_queue_position,
                    "queue_position": target_position,
                },
            )

            try:
                self.repository.commit()
            except IntegrityError as exc:
                self.repository.rollback()
                raise InvalidManagerPlanningError(
                    f"Queue position {target_position} is already taken."
                ) from exc
            except Exception:
                self.repository.rollback()
                raise

            return self._to_read_model(work_order)

    def reorder_queue(
        self,
        payload: WorkOrderQueueReorderBatchRequest,
        station_context: StationContext | None = None,
    ) -> list[WorkOrderRead]:
        self._ensure_manager_station_action(station_context)
        items = payload.items
        if not items:
            return self.list_planned_work_orders()

        production_type = payload.production_type
        with _QUEUE_MUTATION_LOCK:
            # Each production line is reordered independently, so staleness is checked per line.
            current_revision = self.repository.get_planned_queue_revision(production_type)
            if current_revision is not None and payload.queue_revision != current_revision:
                raise InvalidManagerPlanningError("Queue reorder payload is stale. Refresh the manager queue and try again.")

            work_order_ids = [item.work_order_id for item in items]
            queue_positions = [item.queue_position for item in items]

            if len(set(work_order_ids)) != len(work_order_ids):
                raise InvalidManagerPlanningError("Queue reorder payload cannot contain duplicate work order IDs.")
            if len(set(queue_positions)) != len(queue_positions):
                raise InvalidManagerPlanningError("Queue reorder payload cannot contain duplicate queue positions.")

            existing_work_orders = {work_order.id: work_order for work_order in self.repository.list_by_ids(work_order_ids)}
            missing_ids = [work_order_id for work_order_id in work_order_ids if work_order_id not in existing_work_orders]
            if missing_ids:
                missing_id = missing_ids[0]
                raise ResourceNotFoundError(f"Work order {missing_id} not found.")

            off_line_work_orders = [
                work_order
                for work_order in existing_work_orders.values()
                if work_order.production_type != production_type
            ]
            if off_line_work_orders:
                raise InvalidManagerPlanningError(
                    "Queue reorder payload must only contain work orders from the reordered production line."
                )

            planned_work_orders = self._planned_work_orders_for_line(production_type)
            omitted_work_orders = [work_order for work_order in planned_work_orders if work_order.id not in existing_work_orders]
            omitted_active_work_orders = [
                work_order
                for work_order in omitted_work_orders
                if self.process_service.get_display_status(work_order) != ProcessDisplayStatus.READY
            ]
            if omitted_active_work_orders:
                raise InvalidManagerPlanningError("Queue reorder payload must include all active planned work orders.")

            omitted_completed_work_orders = [
                work_order
                for work_order in omitted_work_orders
                if self.process_service.get_display_status(work_order) == ProcessDisplayStatus.READY
            ]

            now = datetime.now(UTC)
            temporarily_repositioned_work_orders = [
                existing_work_orders[item.work_order_id]
                for item in items
            ] + omitted_completed_work_orders
            temporary_queue_position = max(
                [work_order.queue_position or 0 for work_order in planned_work_orders] + queue_positions,
                default=0,
            ) + 1

            for work_order in temporarily_repositioned_work_orders:
                if work_order.production_type is not None:
                    work_order.queue_position = temporary_queue_position
                    work_order.updated_at = now
                    temporary_queue_position += 1

            try:
                self.repository.session.flush()
            except IntegrityError:
                self.repository.rollback()
                raise InvalidManagerPlanningError("Queue reorder conflicts with current queue state.")

            for item in items:
                work_order = existing_work_orders[item.work_order_id]
                if not self._is_planned(work_order):
                    raise InvalidManagerPlanningError(
                        f"Work order {item.work_order_id} must be planned before reordering the queue."
                    )

                work_order.queue_position = item.queue_position
                work_order.updated_at = now

            next_queue_position = max(queue_positions, default=0) + 1
            for work_order in omitted_completed_work_orders:
                work_order.queue_position = next_queue_position
                work_order.updated_at = now
                next_queue_position += 1

            self._record_audit_event(
                event_type="manager.queue_reordered",
                station_context=station_context,
                work_order=None,
                target_type="manager_queue",
                target_id=None,
                summary="Reordered manager queue.",
                details={
                    "production_type": production_type.value,
                    "queue_revision": payload.queue_revision.isoformat(),
                    "items": [
                        {
                            "work_order_id": item.work_order_id,
                            "queue_position": item.queue_position,
                        }
                        for item in items
                    ],
                },
            )

            try:
                self.repository.commit()
            except IntegrityError as exc:
                self.repository.rollback()
                raise InvalidManagerPlanningError("Queue reorder conflicts with current queue state.") from exc
            except Exception:
                self.repository.rollback()
                raise

            return self.list_planned_work_orders()

    @staticmethod
    def _ensure_manager_station_action(station_context: StationContext | None) -> None:
        ensure_station_allowed(
            station_context,
            allowed_station_ids={StationId.MANAGER},
            action="manager planning actions",
        )

    @staticmethod
    def _ensure_stats_viewer(station_context: StationContext | None) -> None:
        ensure_station_allowed(
            station_context,
            allowed_station_ids={StationId.MANAGER},
            action="manager statistics access",
        )

    def _get_existing_work_order(self, work_order_id: int) -> WorkOrder:
        work_order = self.repository.get_by_id(work_order_id)
        if work_order is None:
            raise ResourceNotFoundError(f"Work order {work_order_id} not found.")
        return work_order

    def _planned_work_orders_for_line(self, production_type: ProductionType) -> list[WorkOrder]:
        """Planned work orders on a single production line (MANUAL / AUTOMATIC)."""
        return [
            work_order
            for work_order in self.repository.list_planned_work_orders()
            if work_order.production_type == production_type
        ]

    def _next_active_queue_position_for_line(self, production_type: ProductionType) -> int:
        """Position one past the last *active* order on a line — i.e. append before the trailing
        completed block so newly planned orders land at the end of the live queue."""
        active_positions = [
            work_order.queue_position or 0
            for work_order in self._planned_work_orders_for_line(production_type)
            if self.process_service.get_display_status(work_order) != ProcessDisplayStatus.READY
        ]
        return max(active_positions, default=0) + 1

    def _ensure_queue_position_available_or_releasable(
        self,
        queue_position: int,
        production_type: ProductionType,
        *,
        exclude_work_order_id: int | None = None,
    ) -> None:
        existing_work_order = self.repository.get_planned_by_queue_position(
            queue_position,
            production_type,
            exclude_work_order_id=exclude_work_order_id,
        )
        if existing_work_order is not None and self.process_service.get_display_status(existing_work_order) != ProcessDisplayStatus.READY:
            raise InvalidManagerPlanningError(f"Queue position {queue_position} is already taken.")

    def _get_completed_work_orders_requiring_trailing(
        self,
        *,
        production_type: ProductionType,
        reserved_queue_positions: list[int],
        exclude_work_order_id: int | None = None,
    ) -> list[WorkOrder]:
        planned_work_orders = self._planned_work_orders_for_line(production_type)
        completed_work_orders = [
            work_order
            for work_order in planned_work_orders
            if work_order.id != exclude_work_order_id
            and self.process_service.get_display_status(work_order) == ProcessDisplayStatus.READY
        ]
        if not completed_work_orders:
            return []

        active_queue_positions = [
            work_order.queue_position or 0
            for work_order in planned_work_orders
            if work_order.id != exclude_work_order_id
            and self.process_service.get_display_status(work_order) != ProcessDisplayStatus.READY
        ]
        next_completed_position = max(active_queue_positions + reserved_queue_positions, default=0) + 1

        ordered_completed_work_orders = self._sort_queue_rows(completed_work_orders)
        for work_order in ordered_completed_work_orders:
            if work_order.queue_position != next_completed_position:
                return ordered_completed_work_orders
            next_completed_position += 1

        return []

    def _temporarily_move_queue_rows_out_of_the_way(
        self,
        work_orders: list[WorkOrder],
        *,
        production_type: ProductionType,
        reserved_queue_positions: list[int],
        now: datetime,
    ) -> None:
        if not work_orders:
            return

        planned_work_orders = self._planned_work_orders_for_line(production_type)
        temporary_queue_position = max(
            [work_order.queue_position or 0 for work_order in planned_work_orders] + reserved_queue_positions,
            default=0,
        ) + 1
        for work_order in work_orders:
            work_order.queue_position = temporary_queue_position
            work_order.updated_at = now
            temporary_queue_position += 1

        self.repository.session.flush()

    def _trail_completed_work_orders(
        self,
        work_orders: list[WorkOrder],
        *,
        production_type: ProductionType,
        now: datetime,
    ) -> None:
        if not work_orders:
            return

        planned_work_orders = self._planned_work_orders_for_line(production_type)
        active_queue_positions = [
            work_order.queue_position or 0
            for work_order in planned_work_orders
            if self.process_service.get_display_status(work_order) != ProcessDisplayStatus.READY
        ]
        next_completed_position = max(active_queue_positions, default=0) + 1
        for work_order in self._sort_queue_rows(work_orders):
            work_order.queue_position = next_completed_position
            work_order.updated_at = now
            next_completed_position += 1

    @staticmethod
    def _sort_queue_rows(work_orders: list[WorkOrder]) -> list[WorkOrder]:
        return sorted(work_orders, key=lambda work_order: (work_order.queue_position or 0, work_order.id))

    @staticmethod
    def _ensure_production_not_started(work_order: WorkOrder) -> None:
        blocking_stages = {ProcessStage.HANGING, ProcessStage.PRODUCTION}
        blocking_statuses = {StageStatus.IN_PROGRESS, StageStatus.DONE}
        for stage_state in work_order.stage_states:
            if stage_state.stage in blocking_stages and stage_state.status in blocking_statuses:
                raise InvalidManagerPlanningError(
                    f"Cannot change production type: stage {stage_state.stage.value} has already started."
                )

    @staticmethod
    def _is_planned(work_order: WorkOrder) -> bool:
        return work_order.production_type is not None and work_order.queue_position is not None

    @staticmethod
    def _has_incomplete_marker(work_order: WorkOrder) -> bool:
        return work_order.is_incomplete_on_arrival

    def _record_audit_event(
        self,
        *,
        event_type: str,
        station_context: StationContext | None,
        work_order: WorkOrder | None,
        target_type: str,
        target_id: int | None,
        summary: str,
        details: dict[str, object],
    ) -> None:
        station_id = station_context.station_id if station_context is not None else StationId.SYSTEM
        self.audit_repository.add(
            AuditEvent(
                event_type=event_type,
                station_id=station_id,
                work_order_id=work_order.id if work_order is not None else None,
                target_type=target_type,
                target_id=target_id,
                summary=summary,
                details_json=json.dumps(details, separators=(",", ":")),
            )
        )

    def _to_read_model(self, work_order: WorkOrder) -> WorkOrderRead:
        waiting_ok_quantity = self.process_service.get_waiting_ok_quantity(work_order)
        pending_correction_quantity = self.process_service.get_pending_correction_quantity(work_order)
        total_progress_quantity = self.process_service.get_total_progress_quantity(work_order)
        queue_resource_block = self.process_service.get_queue_resource_block(work_order)
        predicted_paint_quantity_kg = calculate_predicted_paint_quantity_kg(work_order.total_area_m2)
        current_paint_stock_quantity_kg = self._get_current_paint_stock_quantity_kg(work_order)
        paint_inventory_shortage_quantity_kg = calculate_paint_shortage_quantity_kg(
            predicted_paint_quantity_kg,
            current_paint_stock_quantity_kg,
        )

        return WorkOrderRead(
            id=work_order.id,
            order_number=work_order.order_number,
            external_order_number=work_order.external_order_number,
            title=work_order.title,
            total_quantity=work_order.total_quantity,
            completed_quantity=work_order.completed_quantity,
            current_active_quantity=work_order.current_active_quantity,
            waiting_ok_quantity=waiting_ok_quantity,
            pending_correction_quantity=pending_correction_quantity,
            total_progress_quantity=total_progress_quantity,
            is_correction=work_order.is_correction,
            is_historical_correction=self.process_service.is_historical_correction(work_order),
            is_decoral_incomplete=self.process_service.is_decoral_incomplete(work_order),
            work_order_kind=build_work_order_kind_view(work_order.work_order_kind),
            is_ocynk=work_order.is_ocynk,
            correction_reason_category=work_order.correction_reason_category,
            correction_reason_note=work_order.correction_reason_note,
            parent_order=(
                self._build_relation_summary(work_order.parent_order)
                if work_order.parent_order is not None
                else None
            ),
            correction_orders=[
                self._build_relation_summary(correction_order)
                for correction_order in self._get_ordered_correction_orders(work_order)
            ],
            description=work_order.description,
            customer_name=work_order.customer_name,
            ral_code=work_order.ral_code,
            paint_code=work_order.paint_code,
            paint_producer=work_order.paint_producer,
            predicted_paint_quantity_kg=predicted_paint_quantity_kg,
            current_paint_stock_quantity_kg=current_paint_stock_quantity_kg,
            paint_inventory_insufficient_for_prediction=paint_inventory_shortage_quantity_kg is not None,
            paint_inventory_shortage_quantity_kg=paint_inventory_shortage_quantity_kg,
            paint_stock_snapshot_quantity_kg=work_order.paint_stock_snapshot_quantity_kg,
            consumed_paint_quantity_kg=self.paint_service.get_consumed_paint_kg_for_work_orders(work_order.correction_chain_ids),
            status=WorkOrderService.build_status_view(self.process_service.get_display_status(work_order)),
            process_status=build_process_status_view(self.process_service.get_display_status(work_order)),
            queue_blocked_by_resource=(queue_resource_block[0] if queue_resource_block is not None else None),
            queue_blocked_reason=(queue_resource_block[1] if queue_resource_block is not None else None),
            coating_type=build_coating_type_view(work_order.coating_type),
            production_type=(
                build_production_type_view(work_order.production_type)
                if work_order.production_type is not None
                else None
            ),
            queue_namespace=build_queue_namespace_view(work_order.queue_namespace),
            queue_position=work_order.queue_position,
            stage_states=[
                WorkOrderStageStateRead(
                    stage=build_process_stage_view(stage_state.stage),
                    status=build_stage_status_info_view(stage_state.status),
                )
                for stage_state in self._get_ordered_stage_states(work_order)
            ],
            batches=[
                WorkOrderQuantityBatchRead(
                    id=batch.id,
                    quantity=batch.quantity,
                    type=build_quantity_batch_type_view(batch.type),
                    parent_batch_id=batch.parent_batch_id,
                    is_active=batch.is_active,
                    is_finished=not batch.is_active,
                    current_stage=(build_process_stage_view(batch.current_stage) if batch.current_stage is not None else None),
                    current_stage_status=(
                        build_stage_status_info_view(batch.current_stage_status)
                        if batch.current_stage_status is not None
                        else None
                    ),
                    is_partial=batch.is_partial,
                    created_at=batch.created_at,
                )
                for batch in self._get_ordered_batches(work_order)
            ],
            received_date=work_order.received_date,
            planned_pickup_date=work_order.planned_pickup_date,
            is_released_to_client=work_order.released_to_client_at is not None,
            released_to_client_at=work_order.released_to_client_at,
            total_area_m2=work_order.total_area_m2,
            is_incomplete_on_arrival=work_order.is_incomplete_on_arrival,
            surface_preparation_counted_quantity=self.process_service.get_surface_preparation_counted_quantity(work_order),
            surface_preparation_quantity_difference=self.process_service.get_surface_preparation_quantity_difference(work_order),
            profiles_quantity=work_order.profiles_quantity,
            profiles_to_count=work_order.profiles_to_count,
            accessories_quantity=work_order.accessories_quantity,
            accessories_to_count=work_order.accessories_to_count,
            notes=work_order.notes,
            created_at=work_order.created_at,
            updated_at=work_order.updated_at,
        )

    def _get_ordered_stage_states(self, work_order: WorkOrder):  # noqa: ANN201
        stage_order = {
            stage: index
            for index, stage in enumerate(self.process_service.get_stage_sequence_for_work_order(work_order))
        }
        return sorted(
            [stage_state for stage_state in work_order.stage_states if stage_state.stage in stage_order],
            key=lambda stage_state: stage_order[stage_state.stage],
        )

    @staticmethod
    def _get_ordered_batches(work_order: WorkOrder):
        return sorted(work_order.quantity_batches, key=lambda batch: (batch.created_at, batch.id))

    @staticmethod
    def _get_ordered_correction_orders(work_order: WorkOrder) -> list[WorkOrder]:
        return sorted(work_order.correction_orders, key=lambda correction_order: (correction_order.created_at, correction_order.id))

    def _build_relation_summary(self, work_order: WorkOrder):
        summary = build_work_order_relation_summary(work_order)
        summary.process_status = build_process_status_view(self.process_service.get_display_status(work_order))
        summary.is_historical_correction = self.process_service.is_historical_correction(work_order)
        summary.is_decoral_incomplete = self.process_service.is_decoral_incomplete(work_order)
        return summary


def _parse_period_start(period_key: str, group_by: str) -> date:
    if group_by == "day":
        return date.fromisoformat(period_key)
    if group_by == "month":
        year, month = period_key.split("-")
        return date(int(year), int(month), 1)
    # week: "GGGG-VV" (ISO year + ISO week from strftime %G-%V)
    year, week = period_key.split("-")
    # ISO Monday of that week
    return date.fromisocalendar(int(year), int(week), 1)


def _format_period_label(period_key: str, group_by: str) -> str:
    if group_by == "day":
        d = date.fromisoformat(period_key)
        return d.strftime("%d.%m.%Y")
    if group_by == "month":
        year, month = period_key.split("-")
        month_names = ["Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec",
                       "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień"]
        return f"{month_names[int(month) - 1]} {year}"
    # week
    year, week = period_key.split("-")
    return f"Tydzień {int(week)}, {year}"
