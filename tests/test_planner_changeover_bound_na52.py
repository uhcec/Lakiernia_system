"""Regression: the capacity model is driven by the bounded N49-6 changeover cost, not N49-2 (NA52).

The N49-2 statistical changeover estimate (``estimate_colour_changeover``) is the *extra* average gap
between consecutive automatic starts when the colour changes. When real passes are spread across days,
that gap is dominated by overnight/idle time, so the estimate learns idle time as "changeover" and
inflates to hundreds of minutes. Feeding that into the capacity model collapsed every day's net ceiling
(NA52). These tests pin the fix: regardless of how contaminated the learned estimate is, both the
multi-day board and the good-day loss use the bounded **size + direction** cost (≤ the 30-min band).
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.audit.context import StationContext
from app.manager.capacity import CHANGEOVER_BAND_LARGE_MINUTES
from app.manager.repository import ManagerRepository
from app.manager.schemas import WorkOrderPlanAssignRequest
from app.manager.service import ManagerService
from app.process.enums import CoatingType, ProcessStage, ProductionType, StageStatus
from app.process.models import StageTransitionEvent
from app.shared.enums import StationId
from app.work_orders.models import WorkOrder
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import WorkOrderCreate
from app.work_orders.service import WorkOrderService

MANAGER = StationContext(station_id=StationId.MANAGER)
_TODAY = datetime.now(UTC).date()
_COMFORTABLE = _TODAY + timedelta(days=60)
# Pre-shift "now" so day 0 is a full day (NA56 proration off), keeping the placement assertion stable.
_MORNING = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 6, 0)


def _build(db_session: Session) -> tuple[WorkOrderService, ManagerService]:
    return (
        WorkOrderService(WorkOrderRepository(db_session)),
        ManagerService(ManagerRepository(db_session)),
    )


def _create(work_order_service: WorkOrderService, title: str, *, ral: str, m2: float, pickup: date):
    return work_order_service.create_work_order(
        WorkOrderCreate(
            title=title,
            coating_type=CoatingType.RAL,
            total_quantity=10,
            customer_name="ACME",
            ral_code=ral,
            paint_code=f"P-{ral[-4:]}",
            paint_producer="AkzoNobel",
            received_date=_TODAY - timedelta(days=2),
            planned_pickup_date=pickup,
            total_area_m2=m2,
            profiles_quantity=10,
            accessories_quantity=0,
        )
    )


def _packed_pass(
    db_session: Session,
    work_order_id: int,
    *,
    hang_at: datetime,
    pack_at: datetime,
) -> None:
    """A completed automatic pass: PACKING DONE + the HANGING→PACKING bracket the engine reads from."""
    work_order = db_session.get(WorkOrder, work_order_id)
    work_order.production_type = ProductionType.AUTOMATIC
    # CHANGES #3: a completed order has LEFT the queue (no position) but keeps its line, so it still
    # contributes its HANGING→PACKING bracket + packed output to the measurement/good-day reads (which
    # read the stage-transition log + line, not the queue position).
    work_order.queue_position = None
    work_order.completed_quantity = work_order.total_quantity
    for batch in work_order.quantity_batches:
        batch.is_active = False
    packing = next(state for state in work_order.stage_states if state.stage == ProcessStage.PACKING)
    packing.status = StageStatus.DONE
    packing.updated_at = pack_at
    db_session.add_all(
        [
            StageTransitionEvent(
                work_order_id=work_order_id, batch_id=None, stage=ProcessStage.HANGING,
                status=StageStatus.IN_PROGRESS, station_id=StationId.SYSTEM, occurred_at=hang_at,
            ),
            StageTransitionEvent(
                work_order_id=work_order_id, batch_id=None, stage=ProcessStage.PACKING,
                status=StageStatus.DONE, station_id=StationId.SYSTEM, occurred_at=pack_at,
            ),
        ]
    )
    db_session.flush()


def _seed_contaminated_log(work_order_service: WorkOrderService, db_session: Session) -> None:
    """Alternating-colour passes whose starts are spread ~1 day apart → a hugely inflated N49-2 estimate.

    Same-colour pairs are 60 min apart; every colour change crosses a full day, so the learned
    changeover cost is dominated by overnight idle (hundreds of minutes), not the real booth wash.
    """
    base = datetime(2026, 6, 11, 7, 0, tzinfo=UTC)
    plan = [
        ("RAL 9010", base),
        ("RAL 9010", base + timedelta(minutes=60)),
        ("RAL 7016", base + timedelta(days=1)),
        ("RAL 9010", base + timedelta(days=2)),
        ("RAL 7016", base + timedelta(days=3)),
    ]
    for i, (ral, hang) in enumerate(plan):
        order = _create(work_order_service, f"Hist {i}", ral=ral, m2=200.0, pickup=date(2026, 6, 12))
        _packed_pass(db_session, order.id, hang_at=hang, pack_at=hang + timedelta(minutes=30))


def test_learned_estimate_is_inflated_but_plan_uses_the_bounded_cost(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    _seed_contaminated_log(work_order_service, db_session)

    # Sanity: the N49-2 estimate is indeed contaminated (well above the confirmed 15/30-min bands).
    measurements = manager_service.get_line_measurements(
        date(2026, 6, 1), _TODAY, station_context=MANAGER
    )
    assert measurements.changeover.is_measured is True
    assert measurements.changeover.estimated_changeover_minutes > 100.0

    # Two comfortably-deadlined automatic orders, one colour change between them.
    light = _create(work_order_service, "Plan-light", ral="RAL 9010", m2=400.0, pickup=_COMFORTABLE)
    dark = _create(work_order_service, "Plan-dark", ral="RAL 7016", m2=400.0, pickup=_COMFORTABLE)
    for order in (light, dark):
        manager_service.assign_plan(
            order.id,
            WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC),
            station_context=MANAGER,
        )

    plan = manager_service.get_multi_day_plan(station_context=MANAGER, now=_MORNING)

    # The headline + the cost that sized the plan stays within the bounded band, NOT the ≈inflated value.
    assert plan.changeover_minutes <= CHANGEOVER_BAND_LARGE_MINUTES
    # 800 m² of work + one cheap colour change fits one long day — the net ceiling is not collapsed.
    assert len(plan.days) == 1
    assert plan.days[0].placed_order_count == 2
    assert plan.days[0].over_ceiling is False
    assert {order.id for order in (light, dark)}.isdisjoint(set(plan.infeasible_order_ids))


def test_good_day_changeover_loss_stays_bounded_despite_inflated_estimate(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    _seed_contaminated_log(work_order_service, db_session)

    # A "good day" of its own: two large orders, one colour change, all packed on 2026-06-20.
    target = datetime(2026, 6, 20, 7, 0, tzinfo=UTC)
    first = _create(work_order_service, "Good-A", ral="RAL 9010", m2=250.0, pickup=date(2026, 6, 21))
    second = _create(work_order_service, "Good-B", ral="RAL 7016", m2=250.0, pickup=date(2026, 6, 21))
    _packed_pass(db_session, first.id, hang_at=target, pack_at=target + timedelta(minutes=30))
    _packed_pass(
        db_session, second.id, hang_at=target + timedelta(minutes=60), pack_at=target + timedelta(minutes=90)
    )

    stats = manager_service.get_good_day_stats(
        date(2026, 6, 20), date(2026, 6, 20), station_context=MANAGER
    )

    day = stats.days[0]
    assert day.changeover_count == 1
    # One colour change can never cost more than the 30-min band → ≤ 40 m² of ceiling, far below the
    # day's 500 m² output (with the inflated estimate this exceeded the output entirely — NA52).
    max_loss = CHANGEOVER_BAND_LARGE_MINUTES / 60.0 * 80.0
    assert 0.0 < day.changeover_loss_m2 <= max_loss
    assert day.changeover_loss_m2 < day.output_m2
