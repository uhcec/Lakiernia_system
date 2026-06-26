"""Pure unit tests for the day-capacity model (N49-3 under NA49).

Covers the DB-free arithmetic in ``app/manager/capacity.py``: shift floor/ceiling, changeover
capacity loss, below-floor + over-ceiling (spill) flags, and the shift-length advice.
"""

from datetime import datetime

from app.manager.capacity import (
    CEILING_BOOTH_RATE_M2_PER_H,
    CHANGEOVER_BAND_LARGE_MINUTES,
    CHANGEOVER_BAND_SMALL_MINUTES,
    FLOOR_LONG_M2,
    FLOOR_SHORT_M2,
    SHIFT_LONG_HOURS,
    PlacedOrder,
    ShiftLength,
    changeover_minutes_for_transition,
    compute_day_capacity,
    remaining_shift_hours,
)


def _orders(*areas: float) -> list[PlacedOrder]:
    return [PlacedOrder(work_order_id=i, total_area_m2=area) for i, area in enumerate(areas, start=1)]


def test_long_day_floor_and_gross_ceiling_with_no_changeover() -> None:
    day = compute_day_capacity(
        ShiftLength.LONG, _orders(400.0, 400.0), changeover_count=0, changeover_minutes=20.0
    )
    assert day.shift_hours == 14.0
    assert day.floor_m2 == FLOOR_LONG_M2
    # 80 m²/h × 14 h = 1120, no changeover loss → net == gross.
    assert day.gross_ceiling_m2 == 1120.0
    assert day.changeover_loss_m2 == 0.0
    assert day.net_ceiling_m2 == 1120.0
    assert day.placed_m2 == 800.0
    assert day.below_floor is False  # exactly at the floor is not below it
    assert day.over_ceiling is False
    assert day.headroom_m2 == 320.0
    assert day.spill_m2 == 0.0


def test_short_day_uses_short_floor_and_ceiling() -> None:
    day = compute_day_capacity(
        ShiftLength.SHORT, _orders(300.0), changeover_count=0, changeover_minutes=20.0
    )
    assert day.shift_hours == 8.0
    assert day.floor_m2 == FLOOR_SHORT_M2
    assert day.gross_ceiling_m2 == 640.0  # 80 × 8
    assert day.placed_m2 == 300.0
    assert day.below_floor is True  # 300 < 500


def test_changeover_consumes_capacity() -> None:
    # Two 30-min changes = 60 min of booth time = 80 m² of ceiling lost (60/60 × 80).
    day = compute_day_capacity(
        ShiftLength.LONG, _orders(500.0), changeover_count=2, changeover_minutes=30.0
    )
    assert day.changeover_minutes_total == 60.0
    assert day.changeover_loss_m2 == 80.0
    assert day.net_ceiling_m2 == 1040.0  # 1120 − 80
    assert day.gross_ceiling_m2 == 1120.0


def test_over_ceiling_flags_spill_against_net_ceiling() -> None:
    # Net ceiling 1040 (1120 − 80 loss); placing 1100 m² spills 60 m².
    day = compute_day_capacity(
        ShiftLength.LONG, _orders(600.0, 500.0), changeover_count=2, changeover_minutes=30.0
    )
    assert day.placed_m2 == 1100.0
    assert day.net_ceiling_m2 == 1040.0
    assert day.over_ceiling is True
    assert day.spill_m2 == 60.0
    assert day.headroom_m2 == 0.0


def test_empty_day_is_below_floor_with_full_headroom() -> None:
    day = compute_day_capacity(
        ShiftLength.LONG, [], changeover_count=0, changeover_minutes=20.0
    )
    assert day.placed_order_count == 0
    assert day.placed_m2 == 0.0
    assert day.below_floor is True
    assert day.headroom_m2 == day.net_ceiling_m2


def test_negative_inputs_are_clamped() -> None:
    day = compute_day_capacity(
        ShiftLength.LONG,
        [PlacedOrder(work_order_id=1, total_area_m2=None), PlacedOrder(work_order_id=2, total_area_m2=-50.0)],
        changeover_count=-3,
        changeover_minutes=-10.0,
    )
    assert day.placed_m2 == 0.0
    assert day.changeover_count == 0
    assert day.changeover_loss_m2 == 0.0


def test_ceiling_rate_seed_is_the_band_midpoint() -> None:
    # The seed booth rate is the midpoint of the confirmed 60–100 m²/h band.
    assert CEILING_BOOTH_RATE_M2_PER_H == 80.0


def test_remaining_shift_hours_prorates_today() -> None:
    # Before the 07:00 start → the whole shift remains.
    assert remaining_shift_hours(datetime(2026, 6, 24, 6, 0), ShiftLength.LONG) == SHIFT_LONG_HOURS
    assert remaining_shift_hours(datetime(2026, 6, 24, 7, 0), ShiftLength.LONG) == SHIFT_LONG_HOURS
    # Mid long-shift (16:00) → 21:00 − 16:00 = 5 h left.
    assert remaining_shift_hours(datetime(2026, 6, 24, 16, 0), ShiftLength.LONG) == 5.0
    assert remaining_shift_hours(datetime(2026, 6, 24, 16, 30), ShiftLength.LONG) == 4.5
    # After the long shift end (21:00) → nothing remains.
    assert remaining_shift_hours(datetime(2026, 6, 24, 22, 0), ShiftLength.LONG) == 0.0
    # Short shift ends 15:00: at 13:00 → 2 h left.
    assert remaining_shift_hours(datetime(2026, 6, 24, 13, 0), ShiftLength.SHORT) == 2.0


def test_changeover_minutes_size_band_only() -> None:
    # CHANGES #5: cost is the NEXT order's size band only — no colour-direction factor.
    # ≤ 100 m² uses the small band, > 100 the large band.
    assert changeover_minutes_for_transition(next_order_m2=80.0) == CHANGEOVER_BAND_SMALL_MINUTES
    assert changeover_minutes_for_transition(next_order_m2=150.0) == CHANGEOVER_BAND_LARGE_MINUTES
    # Missing size is treated as the conservative large band.
    assert changeover_minutes_for_transition(next_order_m2=None) == CHANGEOVER_BAND_LARGE_MINUTES
