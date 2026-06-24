"""Day-capacity model — the floor + ceiling of one working day (N49-3 under NA49).

The multi-day capacity planner treats each working day as a bucket bounded by two numbers
(``docs/FACTORY_DOMAIN_MODEL.md`` §7 "Planning ground truth"):

* a **floor** — the minimum *profitable* m² (800 on a long day, 500 on a short day). A day is *bad*
  when it falls **below** the floor (too little product), not when it is busy. The floors are fixed
  economic constants, not a function of the booth speed.
* a **ceiling** — the *physical* booth capacity over the shift. The automatic booth's gross painting
  speed is the confirmed **60–100 m²/h** band; over a 14 h (long) / 8 h (short) shift that bounds the
  most product the day can physically hold. This is deliberately the *gross* booth rate, distinct from
  the *effective* rate learned in ``measurement.py`` (N49-2, ≈57 m²/h) which already folds idle +
  changeover into a realistic-output number — here we want the raw physical bound and then subtract
  the day's changeover loss explicitly.

A **colour change consumes capacity**: the booth is not painting during a changeover, so each change
costs ``changeover_minutes`` of booth time, i.e. m² of ceiling that can no longer be filled. The model
folds that loss into a *net* ceiling so "fill vs ceiling" already accounts for the day's colour
changes (the changeover cost itself is learned in ``measurement.py``).

Like ``scheduler.py`` / ``measurement.py`` this module is deliberately DB-free: it takes plain value
objects (the placed orders + the learned changeover cost) and returns a ``DayCapacity`` value object,
so the arithmetic is fully unit-testable and the service layer only supplies the data.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

# Economic floors (minimum profitable m²) and shift lengths — confirmed 2026-06-23
# (``docs/FACTORY_DOMAIN_MODEL.md`` §7). A long day is the 07:00–21:00 shift, a short day 07:00–15:00.
FLOOR_LONG_M2 = 800.0
FLOOR_SHORT_M2 = 500.0
SHIFT_LONG_HOURS = 14.0
SHIFT_SHORT_HOURS = 8.0

# Physical (gross, instantaneous) automatic-booth painting rate — the confirmed 60–100 m²/h band;
# seed = the band midpoint. Used for the physical ceiling and for costing changeover capacity loss.
# NOT the effective rate (N49-2, ≈57) which folds idle/changeover in — see the module docstring.
CEILING_BOOTH_RATE_M2_PER_H = 80.0

# Size + direction changeover-cost bands (N49-6, ``docs/FACTORY_DOMAIN_MODEL.md`` §7). A colour change
# costs time scaled by the NEXT order's size against the 100 m² odzysk threshold (the same number as the
# paint-demand threshold) and by the colour DIRECTION:
#   • next order < 100 m² → "bez odzysku" (no powder recovery) → ≤ 15 min.
#   • next order > 100 m² → "z odzysku"  (powder recovered, fuller clean) → up to 30 min.
#   • light → dark is cheap (lighter residue is invisible under the darker coat — owner's white→grey);
#     dark → light needs a full clean (residue would show), so it pays the band's full minutes.
# These mirror ``measurement.py``'s confirmed structural ``band_*`` fields — one source for the bands.
CHANGEOVER_ODZYSK_THRESHOLD_M2 = 100.0
CHANGEOVER_BAND_SMALL_MINUTES = 15.0  # next order ≤ threshold ("bez odzysku")
CHANGEOVER_BAND_LARGE_MINUTES = 30.0  # next order > threshold ("z odzysku")
# Light → dark is the cheap direction: only a fraction of the band's clean time is needed (no full
# reset). A same-or-lighter-into-darker transition pays this fraction; dark → light pays the full band.
CHANGEOVER_LIGHT_TO_DARK_FACTOR = 0.5


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
    changeover_minutes_each: float
    changeover_minutes_total: float
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
    changeover_count: int,
    changeover_minutes: float,
    ceiling_rate_m2_per_h: float = CEILING_BOOTH_RATE_M2_PER_H,
) -> float:
    """m² of physical ceiling consumed by colour changes (booth not painting during a change).

    ``changeover_count`` × ``changeover_minutes`` of booth time, converted to m² at the booth rate.
    Negative inputs are clamped to zero so a bad estimate never *adds* capacity. Shared by the
    single-day model (``compute_day_capacity``) and the multi-day placement (``placement.py``), so the
    two never drift in how a colour change costs capacity.
    """
    count = max(changeover_count, 0)
    minutes = max(changeover_minutes, 0.0)
    return (count * minutes / 60.0) * ceiling_rate_m2_per_h


def changeover_minutes_for_transition(
    *,
    next_order_m2: float | None,
    light_to_dark: bool,
    band_small_minutes: float = CHANGEOVER_BAND_SMALL_MINUTES,
    band_large_minutes: float = CHANGEOVER_BAND_LARGE_MINUTES,
    light_to_dark_factor: float = CHANGEOVER_LIGHT_TO_DARK_FACTOR,
    threshold_m2: float = CHANGEOVER_ODZYSK_THRESHOLD_M2,
) -> float:
    """Minutes one colour change costs, by the NEXT order's size + the colour direction (N49-6).

    Size band first: next order ≤ 100 m² → the small ("bez odzysku") band, else the large ("z odzysku")
    band. Direction then scales it: a **light → dark** change is cheap (a fraction of the band — the
    lighter residue hides under the darker coat), while **dark → light** pays the full band (a true
    clean). A missing ``next_order_m2`` is treated as the conservative large band. The full 30/15-min
    bands are the dark→light cost; light→dark is the discounted move. ``docs/FACTORY_DOMAIN_MODEL.md`` §7.
    """
    area = next_order_m2 if next_order_m2 is not None else float("inf")
    band = band_large_minutes if area > threshold_m2 else band_small_minutes
    factor = max(min(light_to_dark_factor, 1.0), 0.0) if light_to_dark else 1.0
    return max(band, 0.0) * factor


def advise_shift_length(available_ready_m2: float) -> ShiftLength:
    """Advise the shift length from the work available to run (``docs/FACTORY_DOMAIN_MODEL.md`` §7).

    Enough ready work to clear the long-day floor → run a long day; otherwise a short day (a long day
    that idled below 800 m² would be unprofitable). The threshold is the long-day floor itself.
    """
    return ShiftLength.LONG if available_ready_m2 >= FLOOR_LONG_M2 else ShiftLength.SHORT


def compute_day_capacity(
    shift_length: ShiftLength,
    placed_orders: Sequence[PlacedOrder],
    *,
    changeover_count: int,
    changeover_minutes: float,
    ceiling_rate_m2_per_h: float = CEILING_BOOTH_RATE_M2_PER_H,
) -> DayCapacity:
    """Compute a day's floor/ceiling fill from its placed orders and the learned changeover cost."""
    hours = shift_hours(shift_length)
    floor = floor_m2(shift_length)
    gross_ceiling = ceiling_rate_m2_per_h * hours

    safe_changeover_count = max(changeover_count, 0)
    each_minutes = max(changeover_minutes, 0.0)
    changeover_minutes_total = safe_changeover_count * each_minutes
    changeover_loss = changeover_loss_m2(safe_changeover_count, each_minutes, ceiling_rate_m2_per_h)
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
        changeover_minutes_each=round(each_minutes, 1),
        changeover_minutes_total=round(changeover_minutes_total, 1),
        changeover_loss_m2=round(changeover_loss, 2),
        net_ceiling_m2=round(net_ceiling, 2),
        placed_order_count=len(placed_orders),
        placed_m2=round(placed_m2, 2),
        below_floor=placed_m2 < floor,
        over_ceiling=over_ceiling,
        spill_m2=round(spill, 2),
        headroom_m2=round(headroom, 2),
    )
