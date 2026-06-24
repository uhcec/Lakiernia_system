"""Service/API tests for the manager planning lock (pin/urgent) — NA49.K.

Covers that the painting auto-scheduler respects the locks (a pinned order keeps its queue slot, an
urgent order jumps to the front), that the mutate sets/clears the lock and is manager-gated, and that
leaving the queue (line move) clears the lock.
"""

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.context import StationContext
from app.audit.models import AuditEvent
from app.manager.repository import ManagerRepository
from app.manager.schemas import (
    WorkOrderPlanAssignRequest,
    WorkOrderPlanningPriorityUpdateRequest,
    WorkOrderProductionTypeUpdateRequest,
)
from app.manager.service import ManagerService
from app.process.enums import CoatingType, ProductionType
from app.shared.enums import PlanningPriority, StationId
from app.shared.exceptions import InvalidManagerPlanningError, StationActionForbiddenError
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import WorkOrderCreate
from app.work_orders.service import WorkOrderService

MANAGER = StationContext(station_id=StationId.MANAGER)


def _payload(title: str, ral_code: str) -> WorkOrderCreate:
    return WorkOrderCreate(
        title=title,
        coating_type=CoatingType.RAL,
        total_quantity=10,
        customer_name="ACME",
        ral_code=ral_code,
        paint_code="P-1",
        paint_producer="AkzoNobel",
        received_date=date(2026, 5, 27),
        planned_pickup_date=date(2026, 6, 3),
        total_area_m2=24.0,
        profiles_quantity=10,
        accessories_quantity=0,
    )


def _build(db_session: Session) -> tuple[WorkOrderService, ManagerService]:
    return (
        WorkOrderService(WorkOrderRepository(db_session)),
        ManagerService(ManagerRepository(db_session)),
    )


def _plan_automatic(
    work_order_service: WorkOrderService, manager_service: ManagerService, payload: WorkOrderCreate
) -> int:
    created = work_order_service.create_work_order(payload)
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC),
        station_context=MANAGER,
    )
    return created.id


def _interleaved_line(
    work_order_service: WorkOrderService, manager_service: ManagerService
) -> tuple[int, int, int, int]:
    """Plan A,B,A,B → an interleaved queue the colour rule would regroup to A,A,B,B."""
    a1 = _plan_automatic(work_order_service, manager_service, _payload("A1", "RAL 1000"))
    b1 = _plan_automatic(work_order_service, manager_service, _payload("B1", "RAL 2000"))
    a2 = _plan_automatic(work_order_service, manager_service, _payload("A2", "RAL 1000"))
    b2 = _plan_automatic(work_order_service, manager_service, _payload("B2", "RAL 2000"))
    return a1, b1, a2, b2


def _set_priority(
    manager_service: ManagerService, work_order_id: int, priority: PlanningPriority | None
) -> None:
    manager_service.set_planning_priority(
        work_order_id,
        WorkOrderPlanningPriorityUpdateRequest(planning_priority=priority),
        station_context=MANAGER,
    )


def test_pinned_order_keeps_its_queue_slot_in_the_proposal(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    a1, b1, a2, b2 = _interleaved_line(work_order_service, manager_service)

    # Without a pin the colour rule would regroup to A1,A2,B1,B2. Pin B1 at its current slot (position 2).
    _set_priority(manager_service, b1, PlanningPriority.PINNED)
    proposal = manager_service.propose_auto_schedule(ProductionType.AUTOMATIC, station_context=MANAGER)

    proposed_ids = [order.id for order in proposal.proposed_order]
    assert proposed_ids.index(b1) == 1  # the pin held B1 in slot 2 (index 1), not regrouped down
    assert proposed_ids == [a1, b1, a2, b2]


def test_urgent_order_jumps_to_the_front_of_the_proposal(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    a1, b1, a2, b2 = _interleaved_line(work_order_service, manager_service)

    _set_priority(manager_service, b2, PlanningPriority.URGENT)
    proposal = manager_service.propose_auto_schedule(ProductionType.AUTOMATIC, station_context=MANAGER)

    proposed_ids = [order.id for order in proposal.proposed_order]
    assert proposed_ids[0] == b2  # urgent forced to the very front
    assert set(proposed_ids) == {a1, b1, a2, b2}


def test_set_and_clear_planning_priority_persists_and_audits(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    order_id = _plan_automatic(work_order_service, manager_service, _payload("A1", "RAL 1000"))

    read = manager_service.set_planning_priority(
        order_id,
        WorkOrderPlanningPriorityUpdateRequest(planning_priority=PlanningPriority.PINNED),
        station_context=MANAGER,
    )
    assert read.planning_priority is PlanningPriority.PINNED

    cleared = manager_service.set_planning_priority(
        order_id,
        WorkOrderPlanningPriorityUpdateRequest(planning_priority=None),
        station_context=MANAGER,
    )
    assert cleared.planning_priority is None

    event = db_session.scalar(
        select(AuditEvent).where(AuditEvent.event_type == "manager.planning_priority_set")
    )
    assert event is not None and event.station_id == StationId.MANAGER


def test_set_planning_priority_requires_planned_order(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    created = work_order_service.create_work_order(_payload("Unplanned", "RAL 1000"))
    with pytest.raises(InvalidManagerPlanningError):
        _set_priority(manager_service, created.id, PlanningPriority.PINNED)


def test_set_planning_priority_is_manager_gated(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    order_id = _plan_automatic(work_order_service, manager_service, _payload("A1", "RAL 1000"))
    with pytest.raises(StationActionForbiddenError):
        manager_service.set_planning_priority(
            order_id,
            WorkOrderPlanningPriorityUpdateRequest(planning_priority=PlanningPriority.PINNED),
            station_context=StationContext(station_id=StationId.OFFICE),
        )


def test_changing_production_line_clears_the_lock(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    order_id = _plan_automatic(work_order_service, manager_service, _payload("A1", "RAL 1000"))
    _set_priority(manager_service, order_id, PlanningPriority.PINNED)

    moved = manager_service.update_production_type(
        order_id,
        WorkOrderProductionTypeUpdateRequest(production_type=ProductionType.MANUAL),
        station_context=MANAGER,
    )
    assert moved.planning_priority is None
