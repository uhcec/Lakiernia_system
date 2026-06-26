"""Service/DB-level tests for the good-day stats (NA50).

Verifies ``ManagerService.get_good_day_stats`` reads per-day output m² + on-time completions from the
PACKING-done state and the colour-change / booth-active metrics from the stage-transition brackets,
flags below-floor days, and is gated to managers.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.audit.context import StationContext
from app.manager.capacity import FLOOR_LONG_M2, FLOOR_SHORT_M2, ShiftLength
from app.manager.measurement import SEED_AUTOMATIC_RATE_M2_PER_H
from app.manager.repository import ManagerRepository
from app.manager.service import ManagerService
from app.process.enums import CoatingType, ProcessStage, ProductionType, StageStatus
from app.process.models import StageTransitionEvent
from app.shared.enums import StationId
from app.shared.exceptions import StationActionForbiddenError
from app.work_orders.models import WorkOrder
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import WorkOrderCreate
from app.work_orders.service import WorkOrderService

MANAGER = StationContext(station_id=StationId.MANAGER)
PACKING_STATION = StationContext(station_id=StationId.PACKING)


def _build(db_session: Session):
    return (
        WorkOrderService(WorkOrderRepository(db_session)),
        ManagerService(ManagerRepository(db_session)),
    )


def _create(work_order_service: WorkOrderService, title: str, *, ral="RAL 9010", m2=100.0, pickup=date(2026, 6, 12)):
    return work_order_service.create_work_order(
        WorkOrderCreate(
            title=title,
            coating_type=CoatingType.RAL,
            total_quantity=10,
            customer_name="ACME",
            ral_code=ral,
            paint_code=f"P-{ral[-4:]}",
            paint_producer="AkzoNobel",
            received_date=date(2026, 5, 27),
            planned_pickup_date=pickup,
            total_area_m2=m2,
            profiles_quantity=10,
            accessories_quantity=0,
        )
    )


def _complete_pass(
    db_session: Session,
    work_order_id: int,
    *,
    hang_at: datetime,
    pack_at: datetime,
    production_type: ProductionType = ProductionType.AUTOMATIC,
) -> None:
    """Mark the order packed (output query) and log its HANGING→PACKING bracket (passes)."""
    work_order = db_session.get(WorkOrder, work_order_id)
    work_order.production_type = production_type
    work_order.queue_position = work_order_id
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


def test_reports_floor_and_on_time(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    t0 = datetime(2026, 6, 11, 7, 0, tzinfo=UTC)
    # 900 m² packed on 2026-06-11 (≥ 800 floor); one on time (pickup 06-12), one late (pickup 06-10).
    on_time = _create(work_order_service, "A1", m2=500.0, pickup=date(2026, 6, 12))
    late = _create(work_order_service, "A2", m2=400.0, pickup=date(2026, 6, 10))
    _complete_pass(db_session, on_time.id, hang_at=t0, pack_at=t0 + timedelta(hours=1))
    _complete_pass(db_session, late.id, hang_at=t0 + timedelta(hours=2), pack_at=t0 + timedelta(hours=3))

    stats = manager_service.get_good_day_stats(date(2026, 6, 11), date(2026, 6, 11), station_context=MANAGER)

    assert len(stats.days) == 1
    day = stats.days[0]
    assert day.day == date(2026, 6, 11)
    assert day.output_m2 == 900.0
    assert day.floor_m2 == FLOOR_LONG_M2
    assert day.met_floor is True
    assert day.orders_completed == 2
    assert day.orders_on_time == 1
    assert day.on_time_pct == 50.0
    assert stats.totals.days_met_floor == 1
    assert stats.totals.on_time_pct == 50.0


def test_below_floor_day_is_flagged(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    t0 = datetime(2026, 6, 11, 7, 0, tzinfo=UTC)
    order = _create(work_order_service, "A1", m2=200.0)
    _complete_pass(db_session, order.id, hang_at=t0, pack_at=t0 + timedelta(hours=1))

    stats = manager_service.get_good_day_stats(date(2026, 6, 11), date(2026, 6, 11), station_context=MANAGER)

    assert stats.days[0].met_floor is False
    assert stats.days[0].floor_shortfall_m2 == FLOOR_LONG_M2 - 200.0
    assert stats.totals.days_met_floor == 0


def test_changeover_loss_counts_colour_changes(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    t0 = datetime(2026, 6, 11, 7, 0, tzinfo=UTC)
    # Two colours in one day → at least one colour change → non-zero changeover loss.
    plan = [("RAL 9010", 0), ("RAL 9010", 60), ("RAL 7016", 120), ("RAL 7016", 180)]
    for i, (ral, offset) in enumerate(plan):
        order = _create(work_order_service, f"A{i}", ral=ral, m2=250.0)
        hang = t0 + timedelta(minutes=offset)
        _complete_pass(db_session, order.id, hang_at=hang, pack_at=hang + timedelta(minutes=30))

    stats = manager_service.get_good_day_stats(date(2026, 6, 11), date(2026, 6, 11), station_context=MANAGER)

    day = stats.days[0]
    assert day.changeover_count == 1
    assert day.changeover_minutes_total > 0.0
    assert day.changeover_loss_m2 > 0.0
    assert day.active_hours > 0.0


def test_period_booth_rate_is_measured_with_enough_passes(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    t0 = datetime(2026, 6, 11, 7, 0, tzinfo=UTC)
    # Three overlapping 1 h passes of 200 m² each (same colour) → union 1 h, 600 m² → 600 m²/h period rate.
    for i in range(3):
        order = _create(work_order_service, f"A{i}", m2=200.0)
        _complete_pass(db_session, order.id, hang_at=t0, pack_at=t0 + timedelta(hours=1))

    stats = manager_service.get_good_day_stats(date(2026, 6, 11), date(2026, 6, 11), station_context=MANAGER)

    # The booth rate is a PERIOD figure on the totals, not per-day (NA53); with ≥ 3 passes it's measured.
    assert stats.totals.rate_is_measured is True
    assert stats.totals.rate_m2_per_h == 600.0


def test_period_booth_rate_falls_back_to_seed_when_sparse(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    t0 = datetime(2026, 6, 11, 7, 0, tzinfo=UTC)
    # A single pass → below the 3-pass floor → the period rate reports the seed, flagged unmeasured.
    order = _create(work_order_service, "A1", m2=200.0)
    _complete_pass(db_session, order.id, hang_at=t0, pack_at=t0 + timedelta(hours=1))

    stats = manager_service.get_good_day_stats(date(2026, 6, 11), date(2026, 6, 11), station_context=MANAGER)

    assert stats.totals.rate_is_measured is False
    assert stats.totals.rate_m2_per_h == SEED_AUTOMATIC_RATE_M2_PER_H


def test_good_day_measures_against_persisted_shift_length_NA_CHANGES9(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    t0 = datetime(2026, 6, 11, 7, 0, tzinfo=UTC)
    order = _create(work_order_service, "A1", m2=600.0)  # 600 m² packed that day
    _complete_pass(db_session, order.id, hang_at=t0, pack_at=t0 + timedelta(hours=1))

    # No persisted shift length → measured against the LONG bar (800 m²) → below floor.
    default_stats = manager_service.get_good_day_stats(
        date(2026, 6, 11), date(2026, 6, 11), station_context=MANAGER
    )
    assert default_stats.days[0].floor_m2 == FLOOR_LONG_M2
    assert default_stats.days[0].met_floor is False

    # The manager records that 06-11 was actually a SHORT day → measured against 500 m² → now a good day.
    manager_service.set_day_shift_length(date(2026, 6, 11), ShiftLength.SHORT, station_context=MANAGER)
    short_stats = manager_service.get_good_day_stats(
        date(2026, 6, 11), date(2026, 6, 11), station_context=MANAGER
    )
    assert short_stats.days[0].floor_m2 == FLOOR_SHORT_M2
    assert short_stats.days[0].met_floor is True


def test_set_day_shift_length_upserts_and_is_manager_gated(db_session: Session) -> None:
    _, manager_service = _build(db_session)
    manager_service.set_day_shift_length(date(2026, 6, 11), ShiftLength.SHORT, station_context=MANAGER)
    assert manager_service.get_day_shift_length(date(2026, 6, 11), station_context=MANAGER).shift_length is ShiftLength.SHORT
    # Upsert: setting it again overwrites in place.
    manager_service.set_day_shift_length(date(2026, 6, 11), ShiftLength.LONG, station_context=MANAGER)
    assert manager_service.get_day_shift_length(date(2026, 6, 11), station_context=MANAGER).shift_length is ShiftLength.LONG
    # Unset day defaults to LONG.
    assert manager_service.get_day_shift_length(date(2026, 7, 1), station_context=MANAGER).shift_length is ShiftLength.LONG
    with pytest.raises(StationActionForbiddenError):
        manager_service.set_day_shift_length(date(2026, 6, 11), ShiftLength.SHORT, station_context=PACKING_STATION)


def test_good_day_stats_requires_manager(db_session: Session) -> None:
    _, manager_service = _build(db_session)
    with pytest.raises(StationActionForbiddenError):
        manager_service.get_good_day_stats(
            date(2026, 6, 11), date(2026, 6, 11), station_context=PACKING_STATION
        )
