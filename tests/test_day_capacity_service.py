"""Service-level tests for the day-capacity model (N49-3 under NA49).

Verifies ``ManagerService.get_day_capacity`` buckets a line's active planned orders against the
floor/ceiling, advises the shift length from the available work, counts colour changeovers from the
queue order, and is gated to managers.
"""

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.audit.context import StationContext
from app.manager.capacity import FLOOR_LONG_M2, ShiftLength
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


def _build(db_session: Session) -> tuple[WorkOrderService, ManagerService]:
    return (
        WorkOrderService(WorkOrderRepository(db_session)),
        ManagerService(ManagerRepository(db_session)),
    )


def _payload(title: str, ral_code: str, m2: float) -> WorkOrderCreate:
    return WorkOrderCreate(
        title=title,
        coating_type=CoatingType.RAL,
        total_quantity=10,
        customer_name="ACME",
        ral_code=ral_code,
        paint_code="P-1",
        paint_producer="AkzoNobel",
        received_date=date(2026, 5, 27),
        planned_pickup_date=date(2026, 6, 12),
        total_area_m2=m2,
        profiles_quantity=10,
        accessories_quantity=0,
    )


def _plan_automatic(
    work_order_service: WorkOrderService, manager_service: ManagerService, title: str, ral: str, m2: float
) -> int:
    created = work_order_service.create_work_order(_payload(title, ral, m2))
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC),
        station_context=MANAGER,
    )
    return created.id


def test_empty_line_advises_short_day_below_floor(db_session: Session) -> None:
    _, manager_service = _build(db_session)
    day = manager_service.get_day_capacity(station_context=MANAGER)
    assert day.production_type == ProductionType.AUTOMATIC
    assert day.shift_advised is True
    assert day.shift_length is ShiftLength.SHORT  # no ready work → short day
    assert day.placed_m2 == 0.0
    assert day.below_floor is True


def test_advises_long_day_and_sums_placed_m2(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    # 900 m² of ready work (≥ 800 long-day floor) → advise a long day; same colour → no changeovers.
    _plan_automatic(work_order_service, manager_service, "A1", "RAL 9010", 500.0)
    _plan_automatic(work_order_service, manager_service, "A2", "RAL 9010", 400.0)

    day = manager_service.get_day_capacity(station_context=MANAGER)

    assert day.shift_length is ShiftLength.LONG
    assert day.placed_m2 == 900.0
    assert day.placed_order_count == 2
    assert day.below_floor is False  # 900 ≥ 800
    assert day.changeover_count == 0
    assert day.over_ceiling is False


def test_light_to_dark_sweep_groups_colours_and_costs_by_size(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    # Interleaved input A,B,A — but the day is reordered into a light→dark sweep (N49-5) that GROUPS the
    # two A orders, so only ONE colour change remains (down from the 2 the raw queue order had).
    _plan_automatic(work_order_service, manager_service, "A1", "RAL 1000", 100.0)
    _plan_automatic(work_order_service, manager_service, "B1", "RAL 2000", 100.0)
    _plan_automatic(work_order_service, manager_service, "A2", "RAL 1000", 100.0)

    day = manager_service.get_day_capacity(station_context=MANAGER)

    assert day.changeover_count == 1  # grouped sweep, not the 2 of the interleaved queue order
    # Size+direction-aware cost (N49-6): all orders ≤ 100 m² → small "bez odzysku" band (≤ 15 min),
    # not a flat 20-min seed. The single change costs at most the small band.
    assert day.changeover_minutes <= 15.0
    assert day.changeover_minutes_total == round(day.changeover_minutes, 1)
    assert day.changeover_loss_m2 > 0.0
    assert day.net_ceiling_m2 < day.gross_ceiling_m2


def test_caller_can_force_shift_length(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    _plan_automatic(work_order_service, manager_service, "A1", "RAL 9010", 100.0)

    day = manager_service.get_day_capacity(
        shift_length=ShiftLength.LONG, station_context=MANAGER
    )
    assert day.shift_advised is False
    assert day.shift_length is ShiftLength.LONG
    assert day.floor_m2 == FLOOR_LONG_M2


def test_manual_line_is_separate_bucket(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    _plan_automatic(work_order_service, manager_service, "Auto", "RAL 9010", 500.0)
    manual = work_order_service.create_work_order(_payload("Manual", "RAL 3000", 300.0))
    manager_service.assign_plan(
        manual.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL),
        station_context=MANAGER,
    )

    auto_day = manager_service.get_day_capacity(ProductionType.AUTOMATIC, station_context=MANAGER)
    manual_day = manager_service.get_day_capacity(ProductionType.MANUAL, station_context=MANAGER)

    assert auto_day.placed_m2 == 500.0
    assert manual_day.placed_m2 == 300.0


def test_day_capacity_requires_manager(db_session: Session) -> None:
    _, manager_service = _build(db_session)
    with pytest.raises(StationActionForbiddenError):
        manager_service.get_day_capacity(
            station_context=StationContext(station_id=StationId.OFFICE)
        )
