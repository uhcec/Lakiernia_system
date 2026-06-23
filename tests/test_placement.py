"""Pure unit tests for the deadline-feasible multi-day placement (N49-4 under NA49).

Covers the DB-free arithmetic in ``app/manager/placement.py``: EDF day-bucket packing against the net
ceiling, the "won't make it" (late / beyond-horizon) verdict, colour-change capacity loss per day, the
oversized-order edge, and the working-day calendar.
"""

from datetime import date

from app.manager.capacity import ShiftLength
from app.manager.placement import (
    PlaceableOrder,
    place_orders,
    working_days_from,
)


def _order(
    order_id: int, m2: float, pickup: date, colour: str | None = "RAL 9010"
) -> PlaceableOrder:
    return PlaceableOrder(
        work_order_id=order_id,
        total_area_m2=m2,
        planned_pickup_date=pickup,
        colour_key=colour,
    )


# A long Mon–Fri week of working days, generous enough that the horizon never bites unless intended.
_MON = date(2026, 6, 22)  # Monday
_WORKING_WEEK = working_days_from(_MON, 10)


def test_single_day_holds_orders_within_net_ceiling() -> None:
    # 800 m² same colour fits in a long day (gross 1120, no changeover loss) → one day, on time.
    plan = place_orders(
        [_order(1, 400.0, date(2026, 6, 30)), _order(2, 400.0, date(2026, 6, 30))],
        working_days=_WORKING_WEEK,
        shift_length=ShiftLength.LONG,
        changeover_minutes=20.0,
    )
    assert len(plan.days) == 1
    assert plan.days[0].scheduled_date == _MON
    assert plan.days[0].placed_m2 == 800.0
    assert plan.days[0].changeover_count == 0
    assert plan.days[0].over_ceiling is False
    assert plan.infeasible_order_ids == []
    assert all(p.meets_deadline for p in plan.placements)


def test_overflow_spills_to_next_working_day() -> None:
    # 3 × 500 m² = 1500 > the 1120 gross ceiling → must split across two days.
    plan = place_orders(
        [
            _order(1, 500.0, date(2026, 7, 10)),
            _order(2, 500.0, date(2026, 7, 10)),
            _order(3, 500.0, date(2026, 7, 10)),
        ],
        working_days=_WORKING_WEEK,
        shift_length=ShiftLength.LONG,
        changeover_minutes=20.0,
    )
    assert len(plan.days) == 2
    assert plan.days[0].scheduled_date == _MON
    assert plan.days[1].scheduled_date == date(2026, 6, 23)  # Tuesday
    assert plan.days[0].placed_m2 == 1000.0
    assert plan.days[1].placed_m2 == 500.0


def test_earliest_deadline_first_ordering() -> None:
    # Given out of order, the earliest deadline must land on the earliest day.
    plan = place_orders(
        [
            _order(1, 700.0, date(2026, 7, 1), colour="RAL 1000"),
            _order(2, 700.0, date(2026, 6, 25), colour="RAL 2000"),
        ],
        working_days=_WORKING_WEEK,
        shift_length=ShiftLength.LONG,
        changeover_minutes=20.0,
    )
    # Order 2 (earlier deadline) is on day 0; order 1 on day 1.
    by_id = {p.work_order_id: p for p in plan.placements}
    assert by_id[2].day_index == 0
    assert by_id[1].day_index == 1


def test_missed_deadline_is_infeasible() -> None:
    # Two full days of work but the second order is due before its day → won't make it.
    plan = place_orders(
        [
            _order(1, 1000.0, date(2026, 6, 22), colour="RAL 1000"),
            _order(2, 1000.0, date(2026, 6, 22), colour="RAL 2000"),
        ],
        working_days=_WORKING_WEEK,
        shift_length=ShiftLength.LONG,
        changeover_minutes=20.0,
    )
    by_id = {p.work_order_id: p for p in plan.placements}
    # Order placed on day 1 (Tuesday 06-23) but due Monday 06-22 → late by one calendar day.
    late = by_id[2]
    assert late.day_index == 1
    assert late.scheduled_date == date(2026, 6, 23)
    assert late.meets_deadline is False
    assert late.days_late == 1
    assert plan.infeasible_order_ids == [2]


def test_colour_changes_consume_capacity_and_split_days() -> None:
    # Alternating colours add changeover loss, shrinking the net ceiling so less fits per day than the
    # same total would in one colour. Two 500 m² orders of different colours: net = 1120 − loss.
    plan = place_orders(
        [
            _order(1, 560.0, date(2026, 7, 10), colour="RAL 1000"),
            _order(2, 560.0, date(2026, 7, 10), colour="RAL 2000"),
        ],
        working_days=_WORKING_WEEK,
        shift_length=ShiftLength.LONG,
        changeover_minutes=30.0,
    )
    # 1120 gross; one colour change costs 30 min = 40 m² → net 1080 < 1120, so 1120 placed would spill.
    assert len(plan.days) == 2
    assert plan.days[0].changeover_count == 0
    assert plan.days[0].net_ceiling_m2 == 1120.0


def test_oversized_order_placed_alone_and_flagged_over_ceiling() -> None:
    # A single order larger than a whole day must still be placed (on its own day), flagged over.
    plan = place_orders(
        [_order(1, 1300.0, date(2026, 7, 10))],
        working_days=_WORKING_WEEK,
        shift_length=ShiftLength.LONG,
        changeover_minutes=20.0,
    )
    assert len(plan.days) == 1
    assert plan.days[0].over_ceiling is True
    assert plan.days[0].placed_m2 == 1300.0


def test_beyond_horizon_orders_are_infeasible_with_no_date() -> None:
    # Horizon of one working day, two full days of work → the 2nd day has no date and is infeasible.
    one_day = working_days_from(_MON, 1)
    plan = place_orders(
        [
            _order(1, 1100.0, date(2026, 12, 31), colour="RAL 1000"),
            _order(2, 1100.0, date(2026, 12, 31), colour="RAL 2000"),
        ],
        working_days=one_day,
        shift_length=ShiftLength.LONG,
        changeover_minutes=20.0,
    )
    by_id = {p.work_order_id: p for p in plan.placements}
    assert by_id[2].scheduled_date is None
    assert by_id[2].meets_deadline is False
    assert by_id[2].days_late == 0  # unknown, not negative
    assert plan.infeasible_order_ids == [2]


def test_empty_plan() -> None:
    plan = place_orders(
        [], working_days=_WORKING_WEEK, shift_length=ShiftLength.SHORT, changeover_minutes=20.0
    )
    assert plan.days == []
    assert plan.placements == []
    assert plan.infeasible_order_ids == []
    assert plan.horizon_working_days == len(_WORKING_WEEK)


def test_working_days_skip_weekends() -> None:
    # Friday 2026-06-26 → next 3 working days skip Sat/Sun: Fri, Mon, Tue.
    days = working_days_from(date(2026, 6, 26), 3)
    assert days == [date(2026, 6, 26), date(2026, 6, 29), date(2026, 6, 30)]
