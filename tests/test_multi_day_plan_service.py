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
from app.manager.schemas import (
    WorkOrderPlanAssignRequest,
    WorkOrderQueueReorderBatchRequest,
    WorkOrderQueueReorderRequest,
)
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
    # CHANGES #4: no advising — an unset shift defaults to LONG.
    assert plan.shift_length is ShiftLength.LONG
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
    # Planned at 16:00 today → only ~5 h of day-0 capacity (80 × 5 = 400 m²), so the 700 m² order spills
    # to a full day 1 (NA56). Day 1 holds 700 m² (> a short day), so it stays LONG (NA57).
    _plan_automatic(work_order_service, manager_service, "A1", "RAL 9010", 400.0, _COMFORTABLE)
    _plan_automatic(work_order_service, manager_service, "A2", "RAL 9010", 700.0, _COMFORTABLE)
    afternoon = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 16, 0)

    plan = manager_service.get_multi_day_plan(
        shift_length=ShiftLength.LONG, station_context=MANAGER, now=afternoon
    )

    assert len(plan.days) == 2
    assert plan.days[0].gross_ceiling_m2 == 400.0
    assert plan.days[0].placed_m2 == 400.0
    assert plan.days[1].gross_ceiling_m2 == 1120.0
    assert plan.days[1].placed_m2 == 700.0


def test_underfilled_later_day_reads_as_a_short_day(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    # 3 × 550 m² (same colour): day 0 = 1100 (LONG), the trailing 550 spills to day 1 — judged as a SHORT
    # day (fits ≤ 640, below the long floor) so it clears the short floor and isn't flagged below (NA57).
    for i in range(3):
        _plan_automatic(work_order_service, manager_service, f"A{i}", "RAL 9010", 550.0, _COMFORTABLE)

    plan = manager_service.get_multi_day_plan(
        shift_length=ShiftLength.LONG, station_context=MANAGER, now=_MORNING
    )

    assert len(plan.days) == 2
    assert plan.days[0].shift_length is ShiftLength.LONG
    assert plan.days[1].placed_m2 == 550.0
    assert plan.days[1].shift_length is ShiftLength.SHORT
    assert plan.days[1].below_floor is False
    assert plan.days[1].over_ceiling is False


def test_plan_carries_queue_position_and_revision_for_the_blend(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    _plan_automatic(work_order_service, manager_service, "A1", "RAL 9010", 200.0, _COMFORTABLE)
    _plan_automatic(work_order_service, manager_service, "A2", "RAL 9010", 200.0, _COMFORTABLE)

    plan = manager_service.get_multi_day_plan(station_context=MANAGER, now=_MORNING)

    # NA51: the board needs each order's live queue position + the line's revision to show "your order"
    # vs the suggestion and apply it back to the queue.
    assert plan.queue_revision is not None
    placements = [p for day in plan.days for p in day.placements]
    assert all(p.queue_position is not None for p in placements)


def test_suggested_order_applies_back_via_reorder_queue(db_session: Session) -> None:
    # Plan queue order A,B,C; the suggestion groups identical colours, ordered alphabetically by colour
    # identity (CHANGES #7: no light→dark sweep). Applying that order through the existing reorder
    # endpoint (the board's "Zastosuj plan") must rewrite the queue.
    work_order_service, manager_service = _build(db_session)
    a = _plan_automatic(work_order_service, manager_service, "A", "RAL 9005", 100.0, _COMFORTABLE)
    b = _plan_automatic(work_order_service, manager_service, "B", "RAL 9010", 100.0, _COMFORTABLE)
    c = _plan_automatic(work_order_service, manager_service, "C", "RAL 7035", 100.0, _COMFORTABLE)

    plan = manager_service.get_multi_day_plan(station_context=MANAGER, now=_MORNING)
    suggested = sorted(
        (p for day in plan.days for p in day.placements),
        key=lambda p: (p.day_index, p.sequence_position),
    )
    # Alphabetical by colour identity: RAL 7035 (c) → RAL 9005 (a) → RAL 9010 (b).
    assert [p.work_order_id for p in suggested] == [c, a, b]

    manager_service.reorder_queue(
        WorkOrderQueueReorderBatchRequest(
            production_type=ProductionType.AUTOMATIC,
            queue_revision=plan.queue_revision,
            items=[
                WorkOrderQueueReorderRequest(work_order_id=p.work_order_id, queue_position=index + 1)
                for index, p in enumerate(suggested)
            ],
        ),
        station_context=MANAGER,
    )

    # After applying, the live queue order matches the suggestion (current == suggested).
    after = manager_service.get_multi_day_plan(station_context=MANAGER, now=_MORNING)
    by_queue = sorted(
        (p for day in after.days for p in day.placements),
        key=lambda p: p.queue_position,
    )
    assert [p.work_order_id for p in by_queue] == [c, a, b]


def test_multi_day_plan_requires_manager(db_session: Session) -> None:
    _, manager_service = _build(db_session)
    with pytest.raises(StationActionForbiddenError):
        manager_service.get_multi_day_plan(
            station_context=StationContext(station_id=StationId.OFFICE)
        )
