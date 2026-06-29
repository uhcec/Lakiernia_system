"""Pure unit tests for the shared day-capacity helpers (N49-3 under NA49).

Covers the DB-free arithmetic in ``app/manager/capacity.py`` that survives after the unused single-day
``compute_day_capacity`` snapshot was removed (no UI consumer): the booth-rate seed, mid-shift hour
pro-rating (``remaining_shift_hours``), and the size-band changeover cost
(``changeover_minutes_for_transition``). The day's m²-loss arithmetic is exercised through
``test_good_day.py`` and the service tests.
"""

from datetime import datetime

from app.manager.capacity import (
    CEILING_BOOTH_RATE_M2_PER_H,
    CHANGEOVER_BAND_LARGE_MINUTES,
    CHANGEOVER_BAND_SMALL_MINUTES,
    SHIFT_LONG_HOURS,
    ShiftLength,
    changeover_minutes_for_transition,
    remaining_shift_hours,
)


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
