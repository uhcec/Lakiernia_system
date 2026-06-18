"""Per-stage cycle-time / bottleneck stats derived from the stage-transition log.

Verifies the manager `get_cycle_time_stats` reads durable `StageTransitionEvent` rows and reports
the most-recent-pass active time per stage plus the overall production lead time, gated to managers.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

import pytest

from app.audit.context import StationContext
from app.manager.repository import ManagerRepository
from app.manager.service import ManagerService
from app.process.enums import ProcessStage, ProductionType, StageStatus
from app.process.models import StageTransitionEvent
from app.shared.enums import StationId
from app.shared.exceptions import StationActionForbiddenError
from app.work_orders.models import WorkOrder
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import WorkOrderCreate
from app.work_orders.service import WorkOrderService

from app.process.enums import CoatingType


def _set_production_type(db_session: Session, work_order_id: int, production_type: ProductionType) -> None:
    work_order = db_session.get(WorkOrder, work_order_id)
    work_order.production_type = production_type
    # The planned-requires-both CHECK constraint needs a queue position alongside the production type.
    work_order.queue_position = work_order_id
    db_session.flush()


MANAGER = StationContext(station_id=StationId.MANAGER)


def _build_services(db_session: Session):
    return (
        WorkOrderService(WorkOrderRepository(db_session)),
        ManagerService(ManagerRepository(db_session)),
    )


def _create_order(work_order_service: WorkOrderService, title: str, coating_type: CoatingType = CoatingType.RAL):
    return work_order_service.create_work_order(
        WorkOrderCreate(
            title=title,
            coating_type=coating_type,
            total_quantity=10,
            customer_name="ACME",
            ral_code="RAL 7016",
            paint_code="P-7016",
            paint_producer="AkzoNobel",
            received_date=date(2026, 5, 27),
            total_area_m2=24.0,
            profiles_quantity=10,
            accessories_quantity=0,
        )
    )


def _log(db_session: Session, work_order_id: int, stage: ProcessStage, status: StageStatus, occurred_at: datetime) -> None:
    db_session.add(
        StageTransitionEvent(
            work_order_id=work_order_id,
            batch_id=None,
            stage=stage,
            status=status,
            station_id=StationId.SYSTEM,
            occurred_at=occurred_at,
        )
    )


def test_cycle_time_reports_average_per_stage_and_lead_time(db_session: Session) -> None:
    work_order_service, manager_service = _build_services(db_session)
    order = _create_order(work_order_service, "Cycle order")

    t0 = datetime(2026, 6, 10, 8, 0, tzinfo=UTC)
    _log(db_session, order.id, ProcessStage.SURFACE_PREPARATION, StageStatus.IN_PROGRESS, t0)
    _log(db_session, order.id, ProcessStage.SURFACE_PREPARATION, StageStatus.DONE, t0 + timedelta(minutes=10))
    _log(db_session, order.id, ProcessStage.PRODUCTION, StageStatus.IN_PROGRESS, t0 + timedelta(minutes=15))
    _log(db_session, order.id, ProcessStage.PRODUCTION, StageStatus.DONE, t0 + timedelta(minutes=45))
    _log(db_session, order.id, ProcessStage.PACKING, StageStatus.IN_PROGRESS, t0 + timedelta(minutes=50))
    _log(db_session, order.id, ProcessStage.PACKING, StageStatus.DONE, t0 + timedelta(minutes=60))
    db_session.flush()

    stats = manager_service.get_cycle_time_stats(date(2026, 6, 10), date(2026, 6, 10), station_context=MANAGER)

    assert stats.orders_count == 1
    by_stage = {item.stage: item for item in stats.stages}
    assert by_stage[ProcessStage.SURFACE_PREPARATION].average_seconds == 600.0
    assert by_stage[ProcessStage.PRODUCTION].average_seconds == 1800.0
    assert by_stage[ProcessStage.PACKING].average_seconds == 600.0
    assert by_stage[ProcessStage.PRODUCTION].stage_label == "Produkcja"
    # Lead time = first IN_PROGRESS (t0) to packing DONE (t0 + 60 min).
    assert stats.overall_average_seconds == 3600.0
    # Queue wait before a stage = gap from the previous stage's DONE to this stage's start.
    assert by_stage[ProcessStage.SURFACE_PREPARATION].average_wait_before_seconds is None  # first stage
    assert by_stage[ProcessStage.PRODUCTION].average_wait_before_seconds == 300.0  # min 10 DONE -> min 15 start
    assert by_stage[ProcessStage.PACKING].average_wait_before_seconds == 300.0  # min 45 DONE -> min 50 start
    assert by_stage[ProcessStage.PRODUCTION].wait_orders_count == 1
    # Stages are reported in canonical workflow order.
    assert [item.stage for item in stats.stages] == [
        ProcessStage.SURFACE_PREPARATION,
        ProcessStage.PRODUCTION,
        ProcessStage.PACKING,
    ]


def test_cycle_time_breakdown_splits_each_stage_by_method_and_coating(db_session: Session) -> None:
    # NA23: every production stat is also cut two independent ways. Two orders share the PRODUCTION
    # stage — one manual/RAL (20 min) and one automatic/decoral (40 min) — so the overall average is
    # 30 min and each cross-section's weighted mean reconciles to it.
    work_order_service, manager_service = _build_services(db_session)
    manual = _create_order(work_order_service, "Manual RAL", coating_type=CoatingType.RAL)
    automatic = _create_order(work_order_service, "Automatic decoral", coating_type=CoatingType.DECORAL)
    _set_production_type(db_session, manual.id, ProductionType.MANUAL)
    _set_production_type(db_session, automatic.id, ProductionType.AUTOMATIC)

    t0 = datetime(2026, 6, 13, 8, 0, tzinfo=UTC)
    for order_id, minutes in ((manual.id, 20), (automatic.id, 40)):
        _log(db_session, order_id, ProcessStage.PRODUCTION, StageStatus.IN_PROGRESS, t0)
        _log(db_session, order_id, ProcessStage.PRODUCTION, StageStatus.DONE, t0 + timedelta(minutes=minutes))
        _log(db_session, order_id, ProcessStage.PACKING, StageStatus.IN_PROGRESS, t0 + timedelta(minutes=minutes + 5))
        _log(db_session, order_id, ProcessStage.PACKING, StageStatus.DONE, t0 + timedelta(minutes=minutes + 10))
    db_session.flush()

    stats = manager_service.get_cycle_time_stats(date(2026, 6, 13), date(2026, 6, 13), station_context=MANAGER)

    production = next(item for item in stats.stages if item.stage == ProcessStage.PRODUCTION)
    assert production.average_seconds == 1800.0  # (20 + 40) / 2 min
    method = {seg.key: seg for seg in production.breakdown.by_method}
    coating = {seg.key: seg for seg in production.breakdown.by_coating}
    assert method["manual"].average_seconds == 1200.0 and method["manual"].orders_count == 1
    assert method["automatic"].average_seconds == 2400.0 and method["automatic"].orders_count == 1
    assert coating["ral_only"].average_seconds == 1200.0
    assert coating["decoral"].average_seconds == 2400.0
    # Totals (unlike averages) sum across the partition to the stage total — the "suma czasu" view.
    assert production.total_seconds == 3600.0
    assert method["manual"].total_seconds + method["automatic"].total_seconds == production.total_seconds
    assert coating["ral_only"].total_seconds + coating["decoral"].total_seconds == production.total_seconds
    # Both cross-sections partition the same cohort: counts sum to the stage total.
    assert sum(seg.orders_count for seg in production.breakdown.by_method) == production.orders_count
    assert sum(seg.orders_count for seg in production.breakdown.by_coating) == production.orders_count
    # Overall lead-time breakdown is present and cut the same two ways.
    assert {seg.key for seg in stats.overall_breakdown.by_method} == {"manual", "automatic"}
    assert {seg.key for seg in stats.overall_breakdown.by_coating} == {"ral_only", "decoral"}


def test_cycle_time_uses_only_most_recent_pass_per_stage(db_session: Session) -> None:
    # A correction re-runs production; the report measures the final pass, not the sum of passes.
    work_order_service, manager_service = _build_services(db_session)
    order = _create_order(work_order_service, "Correction cycle")

    t0 = datetime(2026, 6, 11, 8, 0, tzinfo=UTC)
    _log(db_session, order.id, ProcessStage.PRODUCTION, StageStatus.IN_PROGRESS, t0)
    _log(db_session, order.id, ProcessStage.PRODUCTION, StageStatus.DONE, t0 + timedelta(minutes=20))
    # Second (correction) pass through production, lasting 5 minutes.
    _log(db_session, order.id, ProcessStage.PRODUCTION, StageStatus.IN_PROGRESS, t0 + timedelta(hours=2))
    _log(db_session, order.id, ProcessStage.PRODUCTION, StageStatus.DONE, t0 + timedelta(hours=2, minutes=5))
    _log(db_session, order.id, ProcessStage.PACKING, StageStatus.IN_PROGRESS, t0 + timedelta(hours=2, minutes=10))
    _log(db_session, order.id, ProcessStage.PACKING, StageStatus.DONE, t0 + timedelta(hours=2, minutes=20))
    db_session.flush()

    stats = manager_service.get_cycle_time_stats(date(2026, 6, 11), date(2026, 6, 11), station_context=MANAGER)

    by_stage = {item.stage: item for item in stats.stages}
    assert by_stage[ProcessStage.PRODUCTION].average_seconds == 300.0  # final pass only


def test_cycle_time_excludes_orders_packed_outside_window(db_session: Session) -> None:
    work_order_service, manager_service = _build_services(db_session)
    order = _create_order(work_order_service, "Out of window")

    t0 = datetime(2026, 5, 1, 8, 0, tzinfo=UTC)
    _log(db_session, order.id, ProcessStage.PACKING, StageStatus.IN_PROGRESS, t0)
    _log(db_session, order.id, ProcessStage.PACKING, StageStatus.DONE, t0 + timedelta(minutes=10))
    db_session.flush()

    stats = manager_service.get_cycle_time_stats(date(2026, 6, 1), date(2026, 6, 30), station_context=MANAGER)

    assert stats.orders_count == 0
    assert stats.stages == []
    assert stats.overall_average_seconds is None


def test_cycle_time_requires_manager(db_session: Session) -> None:
    _, manager_service = _build_services(db_session)
    with pytest.raises(StationActionForbiddenError):
        manager_service.get_cycle_time_stats(
            date(2026, 6, 1),
            date(2026, 6, 30),
            station_context=StationContext(station_id=StationId.PACKING),
        )
