"""Service-level tests for the within-day light→dark sweep + line lever (N49-5 / N49-6 / N49-8).

Verifies ``ManagerService.get_multi_day_plan`` reorders each placed day into a light→dark colour
sweep (identical colours grouped), reports a size + direction-aware per-day changeover cost, and
attaches a manager-overridable suggested line per order. Deadlines are relative to the real "today" so
placement (which starts from the current working day) is deterministic.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.audit.context import StationContext
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
_COMFORTABLE = _TODAY + timedelta(days=60)
# Pre-shift "now" so day 0 is a full day (NA56 proration off) — keeps single-day placement deterministic.
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


def _plan(
    work_order_service: WorkOrderService,
    manager_service: ManagerService,
    title: str,
    ral: str,
    m2: float,
    pickup: date = _COMFORTABLE,
) -> int:
    created = work_order_service.create_work_order(_payload(title, ral, m2, pickup))
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC),
        station_context=MANAGER,
    )
    return created.id


def test_day_groups_identical_colours(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    # Insert interleaved; the day must group identical colours adjacent (CHANGES #7: no light→dark
    # sweep — groups are ordered alphabetically by colour identity, the two whites grouped together).
    black = _plan(work_order_service, manager_service, "Black", "RAL 9005", 100.0)
    white1 = _plan(work_order_service, manager_service, "White1", "RAL 9010", 100.0)
    grey = _plan(work_order_service, manager_service, "Grey", "RAL 7035", 100.0)
    white2 = _plan(work_order_service, manager_service, "White2", "RAL 9010", 100.0)

    plan = manager_service.get_multi_day_plan(station_context=MANAGER, now=_MORNING)
    placements = [p for day in plan.days for p in day.placements]
    by_position = sorted(placements, key=lambda p: (p.day_index, p.sequence_position))
    ordered_ids = [p.work_order_id for p in by_position]

    # Alphabetical by colour identity: RAL 7035 (grey) → RAL 9005 (black) → RAL 9010 (white, grouped).
    assert ordered_ids == [grey, black, white1, white2]
    # sequence_position is a clean 0..n-1 within the (single) day.
    assert [p.sequence_position for p in by_position] == [0, 1, 2, 3]


def test_grouping_lowers_day_changeover_count(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    # A,B,A,B interleaved input → grouped to A,A,B,B → exactly ONE colour change in the day.
    _plan(work_order_service, manager_service, "A1", "RAL 1000", 100.0)
    _plan(work_order_service, manager_service, "B1", "RAL 5005", 100.0)
    _plan(work_order_service, manager_service, "A2", "RAL 1000", 100.0)
    _plan(work_order_service, manager_service, "B2", "RAL 5005", 100.0)

    plan = manager_service.get_multi_day_plan(station_context=MANAGER, now=_MORNING)
    assert len(plan.days) == 1
    assert plan.days[0].changeover_count == 1
    # Size-band cost (N49-6): one change, next order small (≤100 m²) → the 15-min band.
    assert plan.days[0].changeover_minutes == 15.0


def test_large_orders_incur_changeover_cost(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    # Two distinct colours, both LARGE (>100 m²): the change uses the large (30-min) band regardless of
    # direction (CHANGES #5), so the day carries a real changeover cost (not zero).
    _plan(work_order_service, manager_service, "BigWhite", "RAL 9010", 300.0)
    _plan(work_order_service, manager_service, "BigBlack", "RAL 9005", 300.0)

    plan = manager_service.get_multi_day_plan(station_context=MANAGER, now=_MORNING)
    day = next(d for d in plan.days if d.changeover_count == 1)
    # Large band = 30 min, no direction discount.
    assert day.changeover_minutes == 30.0


def test_small_colour_orphan_is_suggested_manual(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    # One small unique colour (orphan) + two of another colour (a group).
    orphan = _plan(work_order_service, manager_service, "Orphan", "RAL 3000", 40.0)
    _plan(work_order_service, manager_service, "Grp1", "RAL 9010", 40.0)
    _plan(work_order_service, manager_service, "Grp2", "RAL 9010", 40.0)

    plan = manager_service.get_multi_day_plan(station_context=MANAGER, now=_MORNING)
    by_id = {p.work_order_id: p for day in plan.days for p in day.placements}

    assert by_id[orphan].suggested_production_type is ProductionType.MANUAL
    assert by_id[orphan].suggested_line_is_colour_orphan is True
    assert by_id[orphan].suggested_line_is_small is True
    # The grouped colour stays automatic (it can join a colour run).
    grouped = [p for wid, p in by_id.items() if wid != orphan]
    assert all(p.suggested_production_type is ProductionType.AUTOMATIC for p in grouped)


def test_large_colour_orphan_stays_automatic(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    big = _plan(work_order_service, manager_service, "BigOrphan", "RAL 3000", 500.0)

    plan = manager_service.get_multi_day_plan(station_context=MANAGER, now=_MORNING)
    by_id = {p.work_order_id: p for day in plan.days for p in day.placements}
    assert by_id[big].suggested_production_type is ProductionType.AUTOMATIC
    assert by_id[big].suggested_line_is_small is False


def test_within_day_plan_requires_manager(db_session: Session) -> None:
    _, manager_service = _build(db_session)
    with pytest.raises(StationActionForbiddenError):
        manager_service.get_multi_day_plan(
            station_context=StationContext(station_id=StationId.OFFICE)
        )
