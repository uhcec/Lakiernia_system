"""Service-level tests for the deadline-feasible multi-day placement (N49-4 under NA49).

Verifies ``ManagerService.get_multi_day_plan`` lays a line's active planned orders across working days
EDF, advises the shift length, splits overflow onto a second day, flags orders that miss their hard
pickup deadline, and is gated to managers. Deadlines are computed relative to the real "today" so the
placement (which starts from the current working day) is deterministic regardless of the wall clock.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.audit.context import StationContext
from app.manager.capacity import ShiftLength
from app.manager.repository import ManagerRepository
from app.manager.schemas import WorkOrderPlanAssignRequest
from app.manager.service import ManagerService
from app.process.enums import CoatingType, ProductionType
from app.shared.enums import StationId
from app.shared.exceptions import StationActionForbiddenError
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import WorkOrderCreate
from app.work_orders.service import WorkOrderService

MANAGER = StationContext(station_id=StationId.MANAGER)
_TODAY = datetime.now(UTC).date()
_COMFORTABLE = _TODAY + timedelta(days=60)  # safely beyond any near-term working day
# A pre-shift "now" so day 0 is a full day (NA56 proration off) — keeps placement asserts deterministic.
_MORNING = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 6, 0)


def _build(db_session: Session) -> tuple[WorkOrderService, ManagerService]:
    return (
        WorkOrderService(WorkOrderRepository(db_session)),
        ManagerService(ManagerRepository(db_session)),
    )


def _payload(title: str, ral_code: str, m2: float, pickup: date) -> WorkOrderCreate:
    return WorkOrderCreate(
        title=title,
        coating_type=CoatingType.RAL,
        total_quantity=10,
        customer_name="ACME",
        ral_code=ral_code,
        paint_code="P-1",
        paint_producer="AkzoNobel",
        received_date=_TODAY - timedelta(days=2),
        planned_pickup_date=pickup,
        total_area_m2=m2,
        profiles_quantity=10,
        accessories_quantity=0,
    )


def _plan_automatic(
    work_order_service: WorkOrderService,
    manager_service: ManagerService,
    title: str,
    ral: str,
    m2: float,
    pickup: date,
) -> int:
    created = work_order_service.create_work_order(_payload(title, ral, m2, pickup))
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC),
        station_context=MANAGER,
    )
    return created.id


def test_empty_line_yields_no_days(db_session: Session) -> None:
    _, manager_service = _build(db_session)
    plan = manager_service.get_multi_day_plan(station_context=MANAGER, now=_MORNING)
    assert plan.production_type == ProductionType.AUTOMATIC
    assert plan.shift_advised is True
    assert plan.shift_length is ShiftLength.SHORT
    assert plan.days == []
    assert plan.infeasible_order_ids == []


def test_places_orders_on_one_day_and_advises_long(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    _plan_automatic(work_order_service, manager_service, "A1", "RAL 9010", 500.0, _COMFORTABLE)
    _plan_automatic(work_order_service, manager_service, "A2", "RAL 9010", 400.0, _COMFORTABLE)

    plan = manager_service.get_multi_day_plan(station_context=MANAGER, now=_MORNING)

    assert plan.shift_length is ShiftLength.LONG  # 900 ≥ 800 long-day floor
    assert len(plan.days) == 1
    assert plan.days[0].placed_m2 == 900.0
    assert plan.days[0].placed_order_count == 2
    assert plan.days[0].changeover_count == 0
    assert plan.infeasible_order_ids == []
    assert all(p.meets_deadline for p in plan.days[0].placements)


def test_overflow_spills_to_second_day(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    # 3 × 500 m² = 1500 > the 1120 long-day gross ceiling → splits onto a second working day.
    for i in range(3):
        _plan_automatic(work_order_service, manager_service, f"A{i}", "RAL 9010", 500.0, _COMFORTABLE)

    plan = manager_service.get_multi_day_plan(
        shift_length=ShiftLength.LONG, station_context=MANAGER, now=_MORNING
    )

    assert len(plan.days) == 2
    assert plan.days[0].placed_m2 == 1000.0
    assert plan.days[1].placed_m2 == 500.0
    # Comfortable deadlines → nothing slips even when spread across two days.
    assert plan.infeasible_order_ids == []


def test_past_deadline_order_is_infeasible(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    overdue_id = _plan_automatic(
        work_order_service, manager_service, "Late", "RAL 9010", 100.0, date(2020, 1, 1)
    )

    plan = manager_service.get_multi_day_plan(station_context=MANAGER, now=_MORNING)

    assert overdue_id in plan.infeasible_order_ids
    late = next(p for day in plan.days for p in day.placements if p.work_order_id == overdue_id)
    assert late.meets_deadline is False
    assert late.days_late > 0


def test_day_zero_is_prorated_when_planned_mid_shift(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    # Two 400 m² same-colour orders would fit one full long day (gross 1120), but planned at 16:00 today
    # has only ~5 h of day-0 capacity (80 × 5 = 400 m²), so the second spills to a full day 1 (NA56).
    _plan_automatic(work_order_service, manager_service, "A1", "RAL 9010", 400.0, _COMFORTABLE)
    _plan_automatic(work_order_service, manager_service, "A2", "RAL 9010", 400.0, _COMFORTABLE)
    afternoon = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 16, 0)

    plan = manager_service.get_multi_day_plan(
        shift_length=ShiftLength.LONG, station_context=MANAGER, now=afternoon
    )

    assert len(plan.days) == 2
    assert plan.days[0].gross_ceiling_m2 == 400.0
    assert plan.days[0].placed_m2 == 400.0
    assert plan.days[1].gross_ceiling_m2 == 1120.0


def test_multi_day_plan_requires_manager(db_session: Session) -> None:
    _, manager_service = _build(db_session)
    with pytest.raises(StationActionForbiddenError):
        manager_service.get_multi_day_plan(
            station_context=StationContext(station_id=StationId.OFFICE)
        )
