"""Pure unit tests for the measurement engine (N49-2) — no DB, just the derivation logic."""

from datetime import datetime, timedelta

from app.manager.measurement import (
    SEED_AUTOMATIC_RATE_M2_PER_H,
    SEED_CHANGEOVER_MINUTES,
    AutomaticPassObservation,
    estimate_colour_changeover,
    measure_automatic_rate,
)

T0 = datetime(2026, 6, 10, 7, 0)


def _pass(
    work_order_id: int,
    *,
    colour: str | None = "RAL 9010",
    m2: float | None = 100.0,
    hang_offset_min: float = 0.0,
    duration_min: float = 60.0,
) -> AutomaticPassObservation:
    hang = T0 + timedelta(minutes=hang_offset_min)
    return AutomaticPassObservation(
        work_order_id=work_order_id,
        colour_key=colour,
        total_area_m2=m2,
        hanging_started_at=hang,
        packing_done_at=hang + timedelta(minutes=duration_min),
    )


def test_rate_falls_back_to_seed_when_no_observations() -> None:
    rate = measure_automatic_rate([])
    assert rate.is_measured is False
    assert rate.measured_rate_m2_per_h is None
    assert rate.effective_rate_m2_per_h == SEED_AUTOMATIC_RATE_M2_PER_H
    assert rate.sample_order_count == 0


def test_rate_falls_back_to_seed_below_min_sample() -> None:
    # Two passes only (default min is 3) → still the seed, but the observed totals are reported.
    rate = measure_automatic_rate([_pass(1), _pass(2, hang_offset_min=120)])
    assert rate.is_measured is False
    assert rate.effective_rate_m2_per_h == SEED_AUTOMATIC_RATE_M2_PER_H
    assert rate.sample_order_count == 2


def test_rate_uses_interval_union_so_overlap_counts_once() -> None:
    # Three fully-overlapping 1 h passes of 100 m² each: union = 1 h, total = 300 m² → 300 m²/h.
    rate = measure_automatic_rate([_pass(1), _pass(2), _pass(3)])
    assert rate.is_measured is True
    assert rate.active_hours == 1.0
    assert rate.observed_m2 == 300.0
    assert rate.measured_rate_m2_per_h == 300.0
    assert rate.effective_rate_m2_per_h == 300.0


def test_rate_union_excludes_idle_gap_between_passes() -> None:
    # Three back-to-back 1 h passes (no overlap, no gap) span 3 h → 300 m² / 3 h = 100 m²/h. A fourth
    # pass after a long idle gap adds its own hour but the gap itself is not counted as busy time.
    passes = [
        _pass(1, hang_offset_min=0),
        _pass(2, hang_offset_min=60),
        _pass(3, hang_offset_min=120),
        _pass(4, hang_offset_min=600),  # 8 h idle gap before this one
    ]
    rate = measure_automatic_rate(passes)
    # 4 busy hours total (4 × 1 h, gap excluded), 400 m² → 100 m²/h.
    assert rate.active_hours == 4.0
    assert rate.observed_m2 == 400.0
    assert rate.measured_rate_m2_per_h == 100.0


def test_rate_ignores_passes_without_area_or_with_bad_bracket() -> None:
    good = [_pass(1), _pass(2), _pass(3)]
    no_area = AutomaticPassObservation(4, "RAL 9010", None, T0, T0 + timedelta(hours=1))
    bad_bracket = AutomaticPassObservation(5, "RAL 9010", 100.0, T0 + timedelta(hours=2), T0)
    rate = measure_automatic_rate(good + [no_area, bad_bracket])
    assert rate.sample_order_count == 3
    assert rate.observed_m2 == 300.0


def test_changeover_falls_back_to_seed_when_sparse() -> None:
    changeover = estimate_colour_changeover([_pass(1), _pass(2, hang_offset_min=60)])
    assert changeover.is_measured is False
    assert changeover.estimated_changeover_minutes == SEED_CHANGEOVER_MINUTES
    assert changeover.band_threshold_m2 == 100.0
    assert changeover.band_small_minutes == 15.0
    assert changeover.band_large_minutes == 30.0


def test_changeover_learns_extra_gap_on_colour_change() -> None:
    # Same-colour starts are 60 min apart; a colour change inserts an extra 20 min (80 min gap).
    # Pattern of starts (minutes): A@0, A@60, A@120 (same, 60), B@200 (changed, 80), B@260 (same, 60),
    # C@340 (changed, 80), C@400 (same, 60), D@480 (changed, 80).
    passes = [
        _pass(1, colour="A", hang_offset_min=0),
        _pass(2, colour="A", hang_offset_min=60),
        _pass(3, colour="A", hang_offset_min=120),
        _pass(4, colour="B", hang_offset_min=200),
        _pass(5, colour="B", hang_offset_min=260),
        _pass(6, colour="C", hang_offset_min=340),
        _pass(7, colour="C", hang_offset_min=400),
        _pass(8, colour="D", hang_offset_min=480),
    ]
    changeover = estimate_colour_changeover(passes)
    assert changeover.is_measured is True
    assert changeover.same_colour_pair_count == 4
    assert changeover.changed_colour_pair_count == 3
    # avg changed gap (80) − avg same gap (60) = 20 min learned changeover.
    assert changeover.measured_changeover_minutes == 20.0
    assert changeover.estimated_changeover_minutes == 20.0


def test_changeover_clamps_negative_residual_to_zero() -> None:
    # Same-colour gaps larger than changed-colour gaps would give a negative residual → clamp to 0.
    passes = [
        _pass(1, colour="A", hang_offset_min=0),
        _pass(2, colour="A", hang_offset_min=90),
        _pass(3, colour="A", hang_offset_min=180),
        _pass(4, colour="B", hang_offset_min=210),
        _pass(5, colour="C", hang_offset_min=240),
        _pass(6, colour="D", hang_offset_min=270),
    ]
    changeover = estimate_colour_changeover(passes)
    assert changeover.is_measured is True
    assert changeover.measured_changeover_minutes == 0.0
