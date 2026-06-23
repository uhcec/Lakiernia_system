"""Measurement engine — "learn the numbers" for the capacity planner (N49-2 under NA49).

The multi-day capacity planner (N49-3+) needs two real numbers it cannot get from a human tap on the
booth: how fast the automatic line **effectively** turns m² into packed product, and how much a colour
change costs. The only signals available are, per automatic order, a **HANGING start** and a **PACKING
completion** in the append-only ``StageTransitionEvent`` log — together they bracket the whole automatic
pass (hang + booth + oven + packing). See ``docs/FACTORY_DOMAIN_MODEL.md`` §7 "Measurement signals".

Like ``scheduler.py`` this module is deliberately free of any database / ORM dependency: it takes plain
observation value objects and returns measurement value objects, so the derivation is fully
unit-testable and the service layer just supplies the bracketing events.

Two derivations, both seeded so a cold system still answers and both refining as data accrues:

* **Effective rate (m²/h).** Total observed m² divided by the **union** of the per-order
  ``[hanging_start, packing_done]`` intervals. The union (not the sum) is the wall-clock time the line
  was occupied: overlapping in-flight orders count once and overnight idle gaps fall out automatically,
  so the result is the *effective line throughput* (~the daily floor ÷ shift hours, ≈55–60 m²/h), which
  is what the day-capacity model multiplies by shift length — not the instantaneous booth speed.
* **Colour-changeover cost (minutes).** A statistical estimate: the extra time between consecutive
  automatic passes when the colour changes versus when it stays the same. The confirmed structural
  bands (≤15 min under the 100 m² odzysk threshold, up to 30 min over it) are the seed/reference; the
  learned figure is the average inter-start gap difference, which sharpens as more pairs are observed.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.manager.schemas import ColourChangeoverMeasurement, LineRateMeasurement

# Seed ("cold start") automatic line rate, used until enough real passes are observed. ≈ the long-day
# floor 800 m² over a ~14 h shift (and 500 m² over ~8 h ≈ 62), i.e. the owner's ~55–60 m²/h effective
# band — deliberately the *effective* rate, not the 60–100 instantaneous booth ceiling.
SEED_AUTOMATIC_RATE_M2_PER_H = 57.0
# Need at least this many bracketed passes before trusting a measured rate over the seed.
MIN_RATE_SAMPLE_ORDERS = 3

# Colour-changeover structural bands (confirmed 2026-06-23), keyed off the 100 m² odzysk threshold.
CHANGEOVER_ODZYSK_THRESHOLD_M2 = 100.0
CHANGEOVER_BAND_SMALL_MINUTES = 15.0  # next order < threshold → "bez odzysku"
CHANGEOVER_BAND_LARGE_MINUTES = 30.0  # next order > threshold → "z odzysku"
# Provisional seed estimate before enough pairs are observed — midpoint of the two confirmed bands.
SEED_CHANGEOVER_MINUTES = 20.0
# Need at least this many colour-changed adjacent pairs (and some same-colour pairs) before trusting
# the learned changeover figure over the seed.
MIN_CHANGEOVER_SAMPLE_PAIRS = 3


@dataclass(frozen=True)
class AutomaticPassObservation:
    """One automatic order's bracketed pass, as seen in the stage-transition log.

    ``hanging_started_at`` / ``packing_done_at`` must be consistent (both naive UTC or both aware) so
    they subtract cleanly; the service normalises them. ``colour_key`` is the colour identity used to
    decide whether a consecutive pair is a changeover (``None`` = no colour).
    """

    work_order_id: int
    colour_key: str | None
    total_area_m2: float | None
    hanging_started_at: datetime
    packing_done_at: datetime


def _union_seconds(intervals: Sequence[tuple[datetime, datetime]]) -> float:
    """Total wall-clock seconds covered by a set of intervals, counting overlaps once."""
    ordered = sorted(intervals, key=lambda interval: interval[0])
    total = 0.0
    current_start: datetime | None = None
    current_end: datetime | None = None
    for start, end in ordered:
        if current_start is None:
            current_start, current_end = start, end
            continue
        if start > current_end:  # type: ignore[operator]
            total += (current_end - current_start).total_seconds()  # type: ignore[operator]
            current_start, current_end = start, end
        elif end > current_end:  # type: ignore[operator]
            current_end = end
    if current_start is not None:
        total += (current_end - current_start).total_seconds()  # type: ignore[operator]
    return total


def measure_automatic_rate(
    observations: Sequence[AutomaticPassObservation],
    *,
    seed_rate_m2_per_h: float = SEED_AUTOMATIC_RATE_M2_PER_H,
    min_orders: int = MIN_RATE_SAMPLE_ORDERS,
) -> LineRateMeasurement:
    """Effective automatic line rate from bracketed passes, falling back to the seed when sparse."""
    valid = [
        observation
        for observation in observations
        if observation.total_area_m2
        and observation.total_area_m2 > 0
        and observation.packing_done_at > observation.hanging_started_at
    ]
    observed_m2 = sum(observation.total_area_m2 or 0.0 for observation in valid)
    active_seconds = _union_seconds(
        [(observation.hanging_started_at, observation.packing_done_at) for observation in valid]
    )

    measured_rate: float | None = None
    if len(valid) >= min_orders and active_seconds > 0 and observed_m2 > 0:
        measured_rate = round(observed_m2 / (active_seconds / 3600.0), 1)

    effective_rate = measured_rate if measured_rate is not None else seed_rate_m2_per_h
    return LineRateMeasurement(
        sample_order_count=len(valid),
        observed_m2=round(observed_m2, 2),
        active_hours=round(active_seconds / 3600.0, 2),
        measured_rate_m2_per_h=measured_rate,
        seed_rate_m2_per_h=round(seed_rate_m2_per_h, 1),
        effective_rate_m2_per_h=round(effective_rate, 1),
        is_measured=measured_rate is not None,
    )


def estimate_colour_changeover(
    observations: Sequence[AutomaticPassObservation],
    *,
    seed_minutes: float = SEED_CHANGEOVER_MINUTES,
    min_pairs: int = MIN_CHANGEOVER_SAMPLE_PAIRS,
) -> ColourChangeoverMeasurement:
    """Statistical colour-changeover minutes from inter-start gaps, with the confirmed band seed.

    Estimate = average gap between consecutive automatic starts when the colour **changed** minus the
    average gap when it stayed the **same** (the residual is the changeover cost, since same-colour
    runs have no clean). Clamped at zero and only trusted once enough changed pairs (and some
    same-colour pairs to subtract) are seen; otherwise the seed midpoint of the 15/30-min bands stands.
    """
    ordered = sorted(observations, key=lambda observation: observation.hanging_started_at)
    same_colour_gaps: list[float] = []
    changed_colour_gaps: list[float] = []
    for previous, current in zip(ordered, ordered[1:]):
        gap_minutes = (current.hanging_started_at - previous.hanging_started_at).total_seconds() / 60.0
        if gap_minutes < 0:
            continue
        if previous.colour_key is not None and previous.colour_key == current.colour_key:
            same_colour_gaps.append(gap_minutes)
        elif previous.colour_key != current.colour_key:
            changed_colour_gaps.append(gap_minutes)

    measured_minutes: float | None = None
    if len(changed_colour_gaps) >= min_pairs and same_colour_gaps:
        difference = (
            sum(changed_colour_gaps) / len(changed_colour_gaps)
            - sum(same_colour_gaps) / len(same_colour_gaps)
        )
        measured_minutes = round(max(difference, 0.0), 1)

    estimated = measured_minutes if measured_minutes is not None else seed_minutes
    return ColourChangeoverMeasurement(
        same_colour_pair_count=len(same_colour_gaps),
        changed_colour_pair_count=len(changed_colour_gaps),
        measured_changeover_minutes=measured_minutes,
        seed_changeover_minutes=round(seed_minutes, 1),
        estimated_changeover_minutes=round(estimated, 1),
        is_measured=measured_minutes is not None,
        band_threshold_m2=CHANGEOVER_ODZYSK_THRESHOLD_M2,
        band_small_minutes=CHANGEOVER_BAND_SMALL_MINUTES,
        band_large_minutes=CHANGEOVER_BAND_LARGE_MINUTES,
    )
