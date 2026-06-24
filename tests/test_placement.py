"""Pure unit tests for the deadline-feasible multi-day placement (N49-4 under NA49).

Covers the DB-free arithmetic in ``app/manager/placement.py``: EDF day-bucket packing against the net
ceiling, the "won't make it" (late / beyond-horizon) verdict, colour-change capacity loss per day, the
oversized-order edge, and the working-day calendar.
"""

from datetime import date

from app.manager.capacity import FLOOR_SHORT_M2, ShiftLength
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


def test_first_day_hours_prorates_day_zero_only() -> None:
    # A 5 h day-0 gross ceiling = 80 × 5 = 400 m²; the 700 m² order can't fit today and spills to day 1,
    # which is a full LONG day (700 > the short ceiling, so judged against the long floor). Day 0's floor
    # is pro-rated too (800 × 5/14 ≈ 285.71), so 400 ≥ it → not below.
    plan = place_orders(
        [
            _order(1, 400.0, date(2026, 7, 10)),
            _order(2, 700.0, date(2026, 7, 10)),
        ],
        working_days=_WORKING_WEEK,
        shift_length=ShiftLength.LONG,
        changeover_minutes=20.0,
        first_day_hours=5.0,
    )
    assert len(plan.days) == 2
    assert plan.days[0].gross_ceiling_m2 == 400.0
    assert plan.days[0].placed_m2 == 400.0
    assert plan.days[0].floor_m2 == round(800.0 * 5.0 / 14.0, 2)
    assert plan.days[0].below_floor is False
    # Day 1 is a full working day (gross 1120, long floor 800); it holds 700 m² so it's genuinely below.
    assert plan.days[1].gross_ceiling_m2 == 1120.0
    assert plan.days[1].floor_m2 == 800.0
    assert plan.days[1].below_floor is True


def test_underfilled_later_day_is_judged_as_a_short_day() -> None:
    # 3 × 550 m² same colour: day 0 fills to 1100 (LONG), the trailing 550 spills to day 1. 550 fits a
    # short day (≤ 640) and is below the long floor → judged SHORT (floor 500), so it clears 500 and is
    # NOT flagged below floor (it's a fine short day, not a failed long day). NA57.
    plan = place_orders(
        [_order(i, 550.0, date(2026, 7, 10)) for i in range(1, 4)],
        working_days=_WORKING_WEEK,
        shift_length=ShiftLength.LONG,
        changeover_minutes=20.0,
    )
    assert len(plan.days) == 2
    assert plan.days[0].shift_length is ShiftLength.LONG
    assert plan.days[0].placed_m2 == 1100.0
    assert plan.days[1].placed_m2 == 550.0
    assert plan.days[1].shift_length is ShiftLength.SHORT
    assert plan.days[1].floor_m2 == FLOOR_SHORT_M2
    assert plan.days[1].below_floor is False
    assert plan.days[1].over_ceiling is False  # SHORT only when it fits → never over its own ceiling


def test_tiny_later_day_is_short_and_below_its_own_floor() -> None:
    # day 0 = 1100, day 1 = 200. 200 fits a short day but is below the short floor too → SHORT + below,
    # but measured against 500, not the long 800.
    plan = place_orders(
        [_order(1, 550.0, date(2026, 7, 10)), _order(2, 550.0, date(2026, 7, 10)), _order(3, 200.0, date(2026, 7, 10))],
        working_days=_WORKING_WEEK,
        shift_length=ShiftLength.LONG,
        changeover_minutes=20.0,
    )
    assert plan.days[1].placed_m2 == 200.0
    assert plan.days[1].shift_length is ShiftLength.SHORT
    assert plan.days[1].floor_m2 == FLOOR_SHORT_M2
    assert plan.days[1].below_floor is True
    assert plan.days[1].over_ceiling is False


def test_underfilled_long_day_still_flags_below_the_long_floor() -> None:
    # day 0 = 1100, day 1 = 700. 700 needs more than a short day (> 640) → it's a genuinely under-target
    # LONG day, correctly flagged below the long floor (700 < 800).
    plan = place_orders(
        [_order(1, 550.0, date(2026, 7, 10)), _order(2, 550.0, date(2026, 7, 10)), _order(3, 700.0, date(2026, 7, 10))],
        working_days=_WORKING_WEEK,
        shift_length=ShiftLength.LONG,
        changeover_minutes=20.0,
    )
    assert plan.days[1].placed_m2 == 700.0
    assert plan.days[1].shift_length is ShiftLength.LONG
    assert plan.days[1].floor_m2 == 800.0
    assert plan.days[1].below_floor is True
    assert plan.days[1].over_ceiling is False


def test_shift_over_keeps_today_empty_and_starts_work_next_day() -> None:
    # first_day_hours=0 (planned after the shift ends) → today has zero capacity. The order must NOT be
    # stranded on today flagged over-ceiling (NA56 edge); today stays an empty closed column and the work
    # starts on day 1.
    plan = place_orders(
        [_order(1, 280.0, date(2026, 7, 10)), _order(2, 300.0, date(2026, 7, 10))],
        working_days=_WORKING_WEEK,
        shift_length=ShiftLength.LONG,
        changeover_minutes=20.0,
        first_day_hours=0.0,
    )
    assert plan.days[0].scheduled_date == _MON  # today is still shown (a column)…
    assert plan.days[0].placed_m2 == 0.0  # …but empty (closed)
    assert plan.days[0].gross_ceiling_m2 == 0.0
    assert plan.days[0].over_ceiling is False  # no stranded over-ceiling order on a zero-capacity today
    assert plan.days[1].placed_m2 == 580.0  # the work starts tomorrow
    assert all(p.meets_deadline for p in plan.placements)


def test_partial_today_takes_what_fits_then_overflows() -> None:
    # 2 h left today = 80 × 2 = 160 m². A 100 m² first order fits today; the next 100 overflows to day 1.
    plan = place_orders(
        [_order(1, 100.0, date(2026, 7, 10)), _order(2, 100.0, date(2026, 7, 10))],
        working_days=_WORKING_WEEK,
        shift_length=ShiftLength.LONG,
        changeover_minutes=20.0,
        first_day_hours=2.0,
    )
    assert plan.days[0].placed_m2 == 100.0  # today took what fits in its remaining hours
    assert plan.days[1].placed_m2 == 100.0


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
