"""Service/DB-level tests for the measurement engine (N49-2).

Verifies ``ManagerService.get_line_measurements`` reads the durable ``StageTransitionEvent`` brackets
(HANGING start → PACKING done) for automatic orders, derives the effective rate + changeover estimate,
falls back to the seed for the unmeasured manual line, and is gated to managers.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.audit.context import StationContext
from app.manager.measurement import SEED_AUTOMATIC_RATE_M2_PER_H
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

MANAGER = StationContext(station_id=StationId.MANAGER)
PACKING_STATION = StationContext(station_id=StationId.PACKING)


def _build_services(db_session: Session):
    return (
        WorkOrderService(WorkOrderRepository(db_session)),
        ManagerService(ManagerRepository(db_session)),
    )


def _create_order(
    work_order_service: WorkOrderService,
    title: str,
    *,
    ral_code: str = "RAL 9010",
    m2: float = 100.0,
):
    return work_order_service.create_work_order(
        WorkOrderCreate(
            title=title,
            coating_type=CoatingType.RAL,
            total_quantity=10,
            customer_name="ACME",
            ral_code=ral_code,
            paint_code=f"P-{ral_code[-4:]}",
            paint_producer="AkzoNobel",
            received_date=date(2026, 5, 27),
            planned_pickup_date=date(2026, 6, 12),
            total_area_m2=m2,
            profiles_quantity=10,
            accessories_quantity=0,
        )
    )


def _set_line(db_session: Session, work_order_id: int, production_type: ProductionType) -> None:
    work_order = db_session.get(WorkOrder, work_order_id)
    work_order.production_type = production_type
    work_order.queue_position = work_order_id
    db_session.flush()


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


def _bracket(db_session: Session, work_order_id: int, hang_at: datetime, pack_at: datetime) -> None:
    _log(db_session, work_order_id, ProcessStage.HANGING, StageStatus.IN_PROGRESS, hang_at)
    _log(db_session, work_order_id, ProcessStage.PACKING, StageStatus.DONE, pack_at)


def test_measures_automatic_rate_from_bracketed_passes(db_session: Session) -> None:
    work_order_service, manager_service = _build_services(db_session)
    t0 = datetime(2026, 6, 11, 7, 0, tzinfo=UTC)
    # Three overlapping 1 h passes of 100 m² each (same colour) → union 1 h, 300 m² → 300 m²/h.
    for i in range(3):
        order = _create_order(work_order_service, f"Auto {i}", m2=100.0)
        _set_line(db_session, order.id, ProductionType.AUTOMATIC)
        _bracket(db_session, order.id, t0, t0 + timedelta(hours=1))
    db_session.flush()

    stats = manager_service.get_line_measurements(
        date(2026, 6, 11), date(2026, 6, 11), station_context=MANAGER
    )

    assert stats.production_type == ProductionType.AUTOMATIC
    assert stats.rate.is_measured is True
    assert stats.rate.sample_order_count == 3
    assert stats.rate.observed_m2 == 300.0
    assert stats.rate.active_hours == 1.0
    assert stats.rate.measured_rate_m2_per_h == 300.0
    assert stats.rate.effective_rate_m2_per_h == 300.0


def test_manual_line_has_no_brackets_and_reports_seed(db_session: Session) -> None:
    work_order_service, manager_service = _build_services(db_session)
    t0 = datetime(2026, 6, 11, 7, 0, tzinfo=UTC)
    # A manual order packed in-window but with no HANGING stage → no bracket → seed-only.
    order = _create_order(work_order_service, "Manual", m2=100.0)
    _set_line(db_session, order.id, ProductionType.MANUAL)
    _log(db_session, order.id, ProcessStage.PACKING, StageStatus.DONE, t0 + timedelta(hours=1))
    db_session.flush()

    stats = manager_service.get_line_measurements(
        date(2026, 6, 11), date(2026, 6, 11), ProductionType.MANUAL, station_context=MANAGER
    )

    assert stats.rate.is_measured is False
    assert stats.rate.sample_order_count == 0
    assert stats.rate.effective_rate_m2_per_h == SEED_AUTOMATIC_RATE_M2_PER_H


def test_learns_colour_changeover_residual(db_session: Session) -> None:
    work_order_service, manager_service = _build_services(db_session)
    t0 = datetime(2026, 6, 11, 7, 0, tzinfo=UTC)
    # Starts spaced 60 min within a colour and 80 min across a colour change → 20 min learned cost.
    plan = [
        ("RAL 9010", 0),
        ("RAL 9010", 60),
        ("RAL 9010", 120),
        ("RAL 7016", 200),
        ("RAL 7016", 260),
        ("RAL 5010", 340),
        ("RAL 5010", 400),
        ("RAL 3000", 480),
    ]
    for i, (ral, offset) in enumerate(plan):
        order = _create_order(work_order_service, f"Auto {i}", ral_code=ral, m2=100.0)
        _set_line(db_session, order.id, ProductionType.AUTOMATIC)
        hang = t0 + timedelta(minutes=offset)
        _bracket(db_session, order.id, hang, hang + timedelta(minutes=30))
    db_session.flush()

    stats = manager_service.get_line_measurements(
        date(2026, 6, 11), date(2026, 6, 11), station_context=MANAGER
    )

    assert stats.changeover.is_measured is True
    assert stats.changeover.same_colour_pair_count == 4
    assert stats.changeover.changed_colour_pair_count == 3
    assert stats.changeover.measured_changeover_minutes == 20.0


def test_line_measurements_requires_manager(db_session: Session) -> None:
    _, manager_service = _build_services(db_session)
    with pytest.raises(StationActionForbiddenError):
        manager_service.get_line_measurements(
            date(2026, 6, 11), date(2026, 6, 11), station_context=PACKING_STATION
        )
