"""Day-capacity model — the floor + ceiling of one working day (N49-3 under NA49).

The multi-day capacity planner treats each working day as a bucket bounded by two numbers
(``docs/SPEC.md`` §9 "Planner numbers"):

* a **floor** — the minimum *profitable* m² (800 on a long day, 500 on a short day). A day is *bad*
  when it falls **below** the floor (too little product), not when it is busy. The floors are fixed
  economic constants, not a function of the booth speed.
* a **ceiling** — the *physical* booth capacity over the shift. The automatic booth's gross painting
  speed is the confirmed **60–100 m²/h** band; over a 14 h (long) / 8 h (short) shift that bounds the
  most product the day can physically hold. Everything here is a fixed constant — there is no learned
  line rate (the premature effective-rate estimate was removed; it drove no planning decision).

A **colour change consumes capacity**: the booth is not painting during a changeover, so each change
costs ``changeover_minutes`` of booth time, i.e. m² of ceiling that can no longer be filled. The model
folds that loss into a *net* ceiling so "fill vs ceiling" already accounts for the day's colour
changes. The changeover cost itself is the bounded N49-6 size band (15/30 min), not a learned estimate.

Like ``scheduler.py`` this module is deliberately DB-free: it takes plain value objects (the placed
orders + the size-band changeover cost) and returns a ``DayCapacity`` value object, so the arithmetic
is fully unit-testable and the service layer only supplies the data.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

# Economic floors (minimum profitable m²) and shift lengths — owner-confirmed (``docs/SPEC.md`` §9).
# A long day is the 07:00–21:00 shift, a short day 07:00–15:00.
FLOOR_LONG_M2 = 800.0
FLOOR_SHORT_M2 = 500.0
SHIFT_LONG_HOURS = 14.0
SHIFT_SHORT_HOURS = 8.0
# Wall-clock hour the working shift starts (both shift lengths begin at 07:00); the end is start + hours.
SHIFT_START_HOUR = 7.0

# Physical (gross, instantaneous) automatic-booth painting rate — the confirmed 60–100 m²/h band;
# the band midpoint. Used for the physical ceiling and for costing changeover capacity loss. A fixed
# constant, not a learned rate (the effective-rate estimate was removed) — see the module docstring.
CEILING_BOOTH_RATE_M2_PER_H = 80.0

# Size changeover-cost bands (N49-6). A colour change costs time scaled by the NEXT order's size
# against the 100 m² odzysk threshold (the same number as the paint-demand threshold):
#   • next order ≤ 100 m² → "bez odzysku" (no powder recovery) → 15 min.
#   • next order > 100 m² → "z odzysku"  (powder recovered, fuller clean) → 30 min.
# CHANGES #5 (owner-confirmed 2026-06-26) removed the colour-direction factor: a colour change costs
# its size band regardless of light→dark vs dark→light. These mirror ``measurement.py``'s confirmed
# structural ``band_*`` fields — one source for the bands.
CHANGEOVER_ODZYSK_THRESHOLD_M2 = 100.0
CHANGEOVER_BAND_SMALL_MINUTES = 15.0  # next order ≤ threshold ("bez odzysku")
CHANGEOVER_BAND_LARGE_MINUTES = 30.0  # next order > threshold ("z odzysku")


class ShiftLength(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass(frozen=True)
class PlacedOrder:
    """The minimal projection of an order placed on a day the capacity model needs: its m²."""

    work_order_id: int
    total_area_m2: float | None


@dataclass(frozen=True)
class DayCapacity:
    """One working day as a capacity bucket: its floor/ceiling and how the placed work fills it."""

    shift_length: ShiftLength
    shift_hours: float
    floor_m2: float
    ceiling_rate_m2_per_h: float
    # Physical ceiling before any colour-changeover loss (rate × shift hours).
    gross_ceiling_m2: float
    changeover_count: int
    # m² of physical ceiling consumed by the day's colour changes (booth not painting during a change).
    changeover_loss_m2: float
    # What is physically paintable today once changeover loss is removed (the real fill bound).
    net_ceiling_m2: float
    placed_order_count: int
    placed_m2: float
    # placed_m2 < floor_m2 — the day is below the profitable minimum (a bad day).
    below_floor: bool
    # placed_m2 > net_ceiling_m2 — the day is overcommitted; spill_m2 won't physically fit.
    over_ceiling: bool
    spill_m2: float
    # net_ceiling_m2 − placed_m2 when not over (how much more the day can still take), else 0.
    headroom_m2: float


def shift_hours(shift_length: ShiftLength) -> float:
    return SHIFT_LONG_HOURS if shift_length is ShiftLength.LONG else SHIFT_SHORT_HOURS


def floor_m2(shift_length: ShiftLength) -> float:
    return FLOOR_LONG_M2 if shift_length is ShiftLength.LONG else FLOOR_SHORT_M2


def changeover_loss_m2(
    changeover_minutes_total: float,
    ceiling_rate_m2_per_h: float = CEILING_BOOTH_RATE_M2_PER_H,
) -> float:
    """m² of physical ceiling consumed by colour changes (booth not painting during a change).

    The day's *total* changeover minutes converted to m² at the booth rate. Negative input is clamped to
    zero so a bad estimate never *adds* capacity. Each caller supplies the total in the way that fits it,
    so the m²-loss arithmetic lives in one place: the single-day / good-day paths pass the size-band total
    of the day's fixed sequence; the multi-day placement passes ``count × per-change`` because its per-day
    changeover count is only known mid-fill (``placement.py``).
    """
    minutes = max(changeover_minutes_total, 0.0)
    return (minutes / 60.0) * ceiling_rate_m2_per_h


def changeover_minutes_for_transition(
    *,
    next_order_m2: float | None,
    band_small_minutes: float = CHANGEOVER_BAND_SMALL_MINUTES,
    band_large_minutes: float = CHANGEOVER_BAND_LARGE_MINUTES,
    threshold_m2: float = CHANGEOVER_ODZYSK_THRESHOLD_M2,
) -> float:
    """Minutes one colour change costs, by the NEXT order's size band only (N49-6, CHANGES #5).

    Next order ≤ 100 m² → the small ("bez odzysku") band (15 min), else the large ("z odzysku") band
    (30 min). A missing ``next_order_m2`` is treated as the conservative large band. No colour-direction
    factor — a change costs its size band regardless of direction (owner-confirmed 2026-06-26).
    """
    area = next_order_m2 if next_order_m2 is not None else float("inf")
    band = band_large_minutes if area > threshold_m2 else band_small_minutes
    return max(band, 0.0)


def remaining_shift_hours(now: datetime, shift_length: ShiftLength) -> float:
    """Hours left in *today's* shift from the wall-clock ``now`` (NA56), clamped to ``[0, full shift]``.

    The planner's first horizon day is today, so a plan computed mid-shift cannot promise a whole day's
    capacity (``docs/SPEC.md`` §9): a long-day plan built at 16:00 has only ~5 h left. Before
    the 07:00 start the full shift remains; after the shift end nothing remains. ``now`` is interpreted in
    its own clock (the caller passes factory-local time), using only its hour-of-day.
    """
    full = shift_hours(shift_length)
    current_hour = now.hour + now.minute / 60.0
    if current_hour <= SHIFT_START_HOUR:
        return full
    return max(min(SHIFT_START_HOUR + full - current_hour, full), 0.0)


def compute_day_capacity(
    shift_length: ShiftLength,
    placed_orders: Sequence[PlacedOrder],
    *,
    changeover_count: int,
    changeover_minutes_total: float,
    ceiling_rate_m2_per_h: float = CEILING_BOOTH_RATE_M2_PER_H,
) -> DayCapacity:
    """Compute a day's floor/ceiling fill from its placed orders and the size-band changeover cost.

    ``changeover_count`` is the day's number of colour changes (informational); ``changeover_minutes_total``
    is the size-band cost of those changes, which is what actually shrinks the net ceiling.
    """
    hours = shift_hours(shift_length)
    floor = floor_m2(shift_length)
    gross_ceiling = ceiling_rate_m2_per_h * hours

    safe_changeover_count = max(changeover_count, 0)
    changeover_loss = changeover_loss_m2(changeover_minutes_total, ceiling_rate_m2_per_h)
    net_ceiling = max(gross_ceiling - changeover_loss, 0.0)

    placed_m2 = sum(max(order.total_area_m2 or 0.0, 0.0) for order in placed_orders)
    over_ceiling = placed_m2 > net_ceiling
    spill = max(placed_m2 - net_ceiling, 0.0)
    headroom = max(net_ceiling - placed_m2, 0.0)

    return DayCapacity(
        shift_length=shift_length,
        shift_hours=hours,
        floor_m2=round(floor, 2),
        ceiling_rate_m2_per_h=round(ceiling_rate_m2_per_h, 1),
        gross_ceiling_m2=round(gross_ceiling, 2),
        changeover_count=safe_changeover_count,
        changeover_loss_m2=round(changeover_loss, 2),
        net_ceiling_m2=round(net_ceiling, 2),
        placed_order_count=len(placed_orders),
        placed_m2=round(placed_m2, 2),
        below_floor=placed_m2 < floor,
        over_ceiling=over_ceiling,
        spill_m2=round(spill, 2),
        headroom_m2=round(headroom, 2),
    )
