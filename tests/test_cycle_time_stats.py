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
from app.process.enums import ProcessStage, StageStatus
from app.process.models import StageTransitionEvent
from app.shared.enums import StationId
from app.shared.exceptions import StationActionForbiddenError
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import WorkOrderCreate
from app.work_orders.service import WorkOrderService

from app.process.enums import CoatingType


MANAGER = StationContext(station_id=StationId.MANAGER)


def _build_services(db_session: Session):
    return (
        WorkOrderService(WorkOrderRepository(db_session)),
        ManagerService(ManagerRepository(db_session)),
    )


def _create_order(work_order_service: WorkOrderService, title: str):
    return work_order_service.create_work_order(
        WorkOrderCreate(
            title=title,
            coating_type=CoatingType.RAL,
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
    # Stages are reported in canonical workflow order.
    assert [item.stage for item in stats.stages] == [
        ProcessStage.SURFACE_PREPARATION,
        ProcessStage.PRODUCTION,
        ProcessStage.PACKING,
    ]


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
