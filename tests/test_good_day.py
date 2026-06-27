"""Unit tests for the pure good-day metrics core (NA50).

Drives ``summarize_day`` / ``summarize_period`` with plain value objects — no DB — to pin the floor,
on-time %, changeover-loss, and idle/utilisation arithmetic and the period roll-up.
"""

from datetime import date, datetime

from app.manager.good_day import (
    AutomaticPassObservation,
    DayActivity,
    summarize_day,
    summarize_period,
    union_active_hours,
)


def _pass(work_order_id: int, hang_at: datetime, pack_at: datetime) -> AutomaticPassObservation:
    return AutomaticPassObservation(
        work_order_id=work_order_id,
        colour_key="RAL9010",
        total_area_m2=200.0,
        hanging_started_at=hang_at,
        packing_done_at=pack_at,
    )


def test_union_active_hours_counts_overlap_once() -> None:
    base = datetime(2026, 6, 11, 7, 0)
    # Two passes overlapping within the same hour → the union is 1 h, not the 2 h sum.
    hours = union_active_hours(
        [
            _pass(1, base, base.replace(hour=8)),
            _pass(2, base.replace(minute=30), base.replace(hour=8)),
        ]
    )
    assert hours == 1.0


def test_union_active_hours_excludes_idle_gaps_and_bad_brackets() -> None:
    base = datetime(2026, 6, 11, 7, 0)
    # A 1 h pass, an overnight gap, then another 1 h pass → 2 h occupied (the gap falls out); a
    # zero/negative bracket contributes nothing.
    hours = union_active_hours(
        [
            _pass(1, base, base.replace(hour=8)),
            _pass(2, base.replace(day=12), base.replace(day=12, hour=8)),
            _pass(3, base.replace(hour=9), base.replace(hour=9)),  # packing == hanging → dropped
        ]
    )
    assert hours == 2.0


def test_union_active_hours_empty_is_zero() -> None:
    assert union_active_hours([]) == 0.0


def _summarize(activity: DayActivity, *, floor=800.0, shift=14.0, change_min=20.0, rate=80.0):
    return summarize_day(
        activity,
        floor_m2=floor,
        shift_hours=shift,
        changeover_minutes_each=change_min,
        ceiling_rate_m2_per_h=rate,
    )


def test_meets_floor_and_on_time() -> None:
    metric = _summarize(
        DayActivity(date(2026, 6, 11), output_m2=900.0, orders_completed=4, orders_on_time=3,
                    changeover_count=0, active_hours=12.0)
    )
    assert metric.met_floor is True
    assert metric.floor_shortfall_m2 == 0.0
    assert metric.on_time_pct == 75.0
    assert metric.changeover_loss_m2 == 0.0
    assert metric.idle_hours == 2.0
    assert metric.utilisation_pct == round(100.0 * 12.0 / 14.0, 1)


def test_below_floor_and_changeover_loss() -> None:
    metric = _summarize(
        DayActivity(date(2026, 6, 11), output_m2=500.0, orders_completed=2, orders_on_time=2,
                    changeover_count=3, active_hours=8.0)
    )
    assert metric.met_floor is False
    assert metric.floor_shortfall_m2 == 300.0
    assert metric.changeover_minutes_total == 60.0  # 3 × 20
    # loss = 3 × 20 min / 60 × 80 m²/h = 80 m².
    assert metric.changeover_loss_m2 == 80.0
    assert metric.on_time_pct == 100.0


def test_no_completions_yields_null_on_time() -> None:
    metric = _summarize(
        DayActivity(date(2026, 6, 11), output_m2=0.0, orders_completed=0, orders_on_time=0,
                    changeover_count=0, active_hours=0.0)
    )
    assert metric.on_time_pct is None
    assert metric.met_floor is False
    assert metric.utilisation_pct == 0.0
    assert metric.idle_hours == 14.0


def test_summarize_period_rolls_up() -> None:
    days = [
        _summarize(DayActivity(date(2026, 6, 11), 900.0, 4, 3, 0, 12.0)),
        _summarize(DayActivity(date(2026, 6, 12), 500.0, 2, 1, 3, 8.0)),
    ]
    totals = summarize_period(days)
    assert totals.days_count == 2
    assert totals.days_met_floor == 1
    assert totals.total_output_m2 == 1400.0
    assert totals.orders_completed == 6
    assert totals.orders_on_time == 4
    assert totals.on_time_pct == round(100.0 * 4 / 6, 1)
    assert totals.total_changeover_count == 3
    assert totals.total_changeover_loss_m2 == 80.0


def test_empty_period_is_safe() -> None:
    totals = summarize_period([])
    assert totals.days_count == 0
    assert totals.on_time_pct is None
    assert totals.avg_utilisation_pct is None
    assert totals.total_output_m2 == 0.0
