"""Service-level tests for the paint-stock hard block + forward view (N49-7).

Verifies ``ManagerService`` refuses to plan an out-of-stock metered colour on the automatic line,
allows in-stock / untracked / manual-used colours, exposes the forward "runs out at order X" view, and
marks an already-planned order BLOCKED in the multi-day plan once its colour depletes — all manager-gated.
"""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session

from app.audit.context import StationContext
from app.manager.paint_feasibility import PaintFeasibilityStatus
from app.manager.repository import ManagerRepository
from app.manager.schemas import WorkOrderPlanAssignRequest
from app.manager.service import ManagerService
from app.paints.schemas import PaintDeliveryCreate, PaintManualAdjustmentCreate
from app.process.enums import CoatingType, ProductionType
from app.shared.enums import StationId
from app.shared.exceptions import InvalidManagerPlanningError, StationActionForbiddenError
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import WorkOrderCreate
from app.work_orders.service import WorkOrderService

MANAGER = StationContext(station_id=StationId.MANAGER)
PRODUCER = "AkzoNobel"
# Pre-shift "now" so today is a full day-0 (NA56) and the single planned order lands on day 0 regardless
# of the wall-clock the suite runs at.
_TODAY = datetime.now(UTC).date()
_MORNING = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 6, 0)


def _build(db_session: Session) -> tuple[WorkOrderService, ManagerService]:
    return (
        WorkOrderService(WorkOrderRepository(db_session)),
        ManagerService(ManagerRepository(db_session)),
    )


def _payload(title: str, ral_code: str, m2: float, *, paint_code: str = "P-1") -> WorkOrderCreate:
    return WorkOrderCreate(
        title=title,
        coating_type=CoatingType.RAL,
        total_quantity=10,
        customer_name="ACME",
        ral_code=ral_code,
        paint_code=paint_code,
        paint_producer=PRODUCER,
        received_date=date(2026, 5, 27),
        planned_pickup_date=date(2026, 6, 12),
        total_area_m2=m2,
        profiles_quantity=10,
        accessories_quantity=0,
    )


def _deliver(manager_service: ManagerService, ral_code: str, qty: float, *, paint_code: str = "P-1") -> None:
    manager_service.paint_service.record_delivery(
        PaintDeliveryCreate(ral_code=ral_code, paint_producer=PRODUCER, paint_code=paint_code, quantity_kg=qty)
    )


def _deplete_to_zero(manager_service: ManagerService, ral_code: str, *, paint_code: str = "P-1") -> None:
    """Make a *tracked* paint sit at exactly 0 kg (deliver a little, then adjust it back down)."""
    _deliver(manager_service, ral_code, 5.0, paint_code=paint_code)
    manager_service.paint_service.record_manual_adjustment(
        PaintManualAdjustmentCreate(
            ral_code=ral_code,
            paint_producer=PRODUCER,
            paint_code=paint_code,
            quantity_delta_kg=-5.0,
            note="recount",
        )
    )


def _create(work_order_service: WorkOrderService, title: str, ral: str, m2: float) -> int:
    return work_order_service.create_work_order(_payload(title, ral, m2)).id


def _assign(manager_service: ManagerService, work_order_id: int, production_type: ProductionType) -> None:
    manager_service.assign_plan(
        work_order_id,
        WorkOrderPlanAssignRequest(production_type=production_type),
        station_context=MANAGER,
    )


def test_plan_blocked_when_automatic_colour_out_of_stock(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    _deplete_to_zero(manager_service, "RAL 9005")  # tracked, depleted
    order_id = _create(work_order_service, "A1", "RAL 9005", 100.0)

    with pytest.raises(InvalidManagerPlanningError):
        _assign(manager_service, order_id, ProductionType.AUTOMATIC)


def test_plan_blocked_when_first_order_demand_exceeds_stock(db_session: Session) -> None:
    # Some stock (5 kg) but the first order plainly needs more than that → demand-aware hard block (NA54).
    work_order_service, manager_service = _build(db_session)
    _deliver(manager_service, "RAL 9005", 5.0)  # tracked, but only 5 kg
    order_id = _create(work_order_service, "A1", "RAL 9005", 100.0)  # demand ≫ 5 kg

    with pytest.raises(InvalidManagerPlanningError):
        _assign(manager_service, order_id, ProductionType.AUTOMATIC)


def test_plan_allowed_when_paint_in_stock(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    _deliver(manager_service, "RAL 9005", 100.0)
    order_id = _create(work_order_service, "A1", "RAL 9005", 100.0)

    _assign(manager_service, order_id, ProductionType.AUTOMATIC)  # no raise
    plan = manager_service.get_multi_day_plan(station_context=MANAGER, now=_MORNING)
    assert plan.days[0].placements[0].paint_status is PaintFeasibilityStatus.OK


def test_plan_allowed_when_colour_untracked(db_session: Session) -> None:
    # Colour never entered into inventory → no hard claim that it is out of stock → planning allowed.
    work_order_service, manager_service = _build(db_session)
    order_id = _create(work_order_service, "A1", "RAL 7016", 100.0)
    _assign(manager_service, order_id, ProductionType.AUTOMATIC)  # no raise


def test_manual_used_colour_warns_not_blocks(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    _deplete_to_zero(manager_service, "RAL 3000")  # tracked, depleted
    # The same colour is planned on the (unmetered) MANUAL line → low-confidence balance → warn, never block.
    manual_id = _create(work_order_service, "M1", "RAL 3000", 50.0)
    _assign(manager_service, manual_id, ProductionType.MANUAL)

    auto_id = _create(work_order_service, "A1", "RAL 3000", 100.0)
    _assign(manager_service, auto_id, ProductionType.AUTOMATIC)  # no raise (manual-used)

    view = manager_service.get_paint_forward_view(station_context=MANAGER)
    feasibility = next(o for o in view.orders if o.work_order_id == auto_id)
    assert feasibility.status is PaintFeasibilityStatus.WARNING
    assert auto_id not in view.blocked_order_ids


def test_forward_view_runs_out_at_second_order(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    _deliver(manager_service, "RAL 9010", 20.0)  # enough for the first order, not both
    first = _create(work_order_service, "A1", "RAL 9010", 60.0)  # 60/4 = 15 kg
    second = _create(work_order_service, "A2", "RAL 9010", 60.0)  # cumulative 30 kg > 20
    _assign(manager_service, first, ProductionType.AUTOMATIC)
    _assign(manager_service, second, ProductionType.AUTOMATIC)

    view = manager_service.get_paint_forward_view(station_context=MANAGER)
    by_id = {o.work_order_id: o for o in view.orders}
    assert by_id[first].status is PaintFeasibilityStatus.OK
    assert by_id[second].status is PaintFeasibilityStatus.WARNING
    assert view.blocked_order_ids == []
    assert second in view.warning_order_ids


def test_multi_day_plan_marks_blocked_when_colour_depletes_after_planning(db_session: Session) -> None:
    # Realistic path to a BLOCKED marker: planned while in stock, the colour later depletes to zero.
    work_order_service, manager_service = _build(db_session)
    _deliver(manager_service, "RAL 5005", 100.0)
    order_id = _create(work_order_service, "A1", "RAL 5005", 100.0)
    _assign(manager_service, order_id, ProductionType.AUTOMATIC)

    manager_service.paint_service.record_manual_adjustment(
        PaintManualAdjustmentCreate(
            ral_code="RAL 5005", paint_producer=PRODUCER, paint_code="P-1",
            quantity_delta_kg=-100.0, note="depleted",
        )
    )

    plan = manager_service.get_multi_day_plan(station_context=MANAGER, now=_MORNING)
    placement = plan.days[0].placements[0]
    assert placement.paint_status is PaintFeasibilityStatus.BLOCKED


def test_paint_forward_view_requires_manager(db_session: Session) -> None:
    _, manager_service = _build(db_session)
    with pytest.raises(StationActionForbiddenError):
        manager_service.get_paint_forward_view(
            station_context=StationContext(station_id=StationId.OFFICE)
        )
