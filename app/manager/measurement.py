"""Measurement engine — "learn the numbers" for the capacity planner (N49-2 under NA49).

The multi-day capacity planner (N49-3+) needs one real number it cannot get from a human tap on the
booth: how fast the automatic line **effectively** turns m² into packed product. The only signals
available are, per automatic order, a **HANGING start** and a **PACKING completion** in the append-only
``StageTransitionEvent`` log — together they bracket the whole automatic pass (hang + booth + oven +
packing). See ``docs/FACTORY_DOMAIN_MODEL.md`` §7 "Measurement signals".

Like ``scheduler.py`` this module is deliberately free of any database / ORM dependency: it takes plain
observation value objects and returns measurement value objects, so the derivation is fully
unit-testable and the service layer just supplies the bracketing events.

**Effective rate (m²/h).** Total observed m² divided by the **union** of the per-order
``[hanging_start, packing_done]`` intervals. The union (not the sum) is the wall-clock time the line
was occupied: overlapping in-flight orders count once and overnight idle gaps fall out automatically,
so the result is the *effective line throughput* (~the daily floor ÷ shift hours, ≈55–60 m²/h), which
is what the day-capacity model multiplies by shift length — not the instantaneous booth speed.

(The colour-changeover **cost** is NOT learned here: a statistical inter-start-gap estimate was
contaminated by overnight/weekend gaps and, since NA52, the planner sizes changeovers from the bounded
N49-6 size bands instead — see ``capacity.changeover_minutes_for_transition`` / ``colour.py``. The old
learned estimate drove nothing and was removed 2026-06-27, owner-decided.)
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.manager.schemas import LineRateMeasurement

# Seed ("cold start") automatic line rate, used until enough real passes are observed. ≈ the long-day
# floor 800 m² over a ~14 h shift (and 500 m² over ~8 h ≈ 62), i.e. the owner's ~55–60 m²/h effective
# band — deliberately the *effective* rate, not the 60–100 instantaneous booth ceiling.
SEED_AUTOMATIC_RATE_M2_PER_H = 57.0
# Need at least this many bracketed passes before trusting a measured rate over the seed.
MIN_RATE_SAMPLE_ORDERS = 3


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
