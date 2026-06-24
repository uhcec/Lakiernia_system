"""RAL-lightness colour ordering + line-assignment lever (N49-5 / N49-8 under NA49).

Two within-day planning levers that share one idea — a colour's **lightness**, derived from its RAL
code — live here so they cannot drift:

* **N49-5 light→dark sweep.** Within a day's placed orders, group identical colours into runs (a
  same-colour adjacency costs zero changeover), then order the remaining colour *changes* **light →
  dark**. Going lighter→darker is cheap (residue of the lighter colour is invisible under the darker
  one — owner's white→grey example); **dark → light is the expensive reset** to minimise. So the cheap
  day shape is a single light→dark sweep (``docs/FACTORY_DOMAIN_MODEL.md`` §7). This replaces the crude
  "largest colour run first" proxy (supersedes NA49.H) and the exact-identity-only COLOUR rule.

* **N49-8 line-assignment lever.** Suggest a line per order: a **small-m² colour-orphan** (no
  same-colour neighbour to group with) → **manual**; otherwise → **automatic** (so it can join a colour
  run / balance idle). The manager can override (``docs/FACTORY_DOMAIN_MODEL.md`` §7 "Line choice").

Like ``scheduler.py`` / ``capacity.py`` / ``placement.py`` this module is deliberately DB-free: it
takes plain value objects and returns ordered ids / value objects, so the logic is fully unit-testable
and the service layer just supplies the data.

----------------------------------------------------------------------------------------------------
⚠️ THE OPEN QUESTION lives in ``ral_lightness`` below — it is the single point to revisit.
----------------------------------------------------------------------------------------------------
Lightness is derived from the **first digit of the RAL Classic code** (``RAL <NNNN>``), whose first
digit is the colour *group*: 1=yellow, 2=orange, 3=red, 4=violet, 5=blue, 6=green, 7=grey, 8=brown,
9=black/white. That digit is **not** a perceptual lightness scale, so we map each group to an
*approximate* lightness rank good enough to order a light→dark sweep, with the two unambiguous anchors
the owner cares about — RAL 9010/9016 (pure white, lightest) and RAL 9005/9011/9017 (black, darkest) —
pinned by their full 4-digit code. Everything in between is a coarse, defensible ordering, **not** a
measured L* value.

This is the "colour-similarity STILL OPEN" question (``IMMEDIATE_NEXT_ACTIONS.md`` N49 open questions /
``FACTORY_DOMAIN_MODEL.md`` §7): the owner could not confirm whether colour **families** (e.g. all
greys) should override pure lightness, so a true CIE-Lab/HLC mapping or a family table may replace this
later. Keep that single owner decision here — do not scatter lightness assumptions across the codebase.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.manager.capacity import changeover_minutes_for_transition

# Approximate lightness rank per RAL Classic colour group (the first code digit), 0.0 = darkest …
# 1.0 = lightest. ASSUMPTION (revisit — see module docstring): a coarse, defensible ordering, NOT a
# perceptual L* scale. Yellows read lightest, then greys/greens/oranges/blues/reds/violets/browns,
# blacks darkest. The 9xx group is split by full code below (white vs black both live there).
_RAL_GROUP_LIGHTNESS: dict[int, float] = {
    1: 0.85,  # yellow — light
    2: 0.55,  # orange
    3: 0.40,  # red
    4: 0.35,  # violet
    5: 0.30,  # blue
    6: 0.45,  # green
    7: 0.60,  # grey (mid; specific greys refined below)
    8: 0.25,  # brown — dark
    9: 0.50,  # white/black/grey — MUST be resolved by full code (see _RAL_CODE_LIGHTNESS)
}

# Full-code overrides for the unambiguous anchors and common 9xx codes (where the group digit alone is
# useless — white and black share group 9). These are the colours the owner named (white→grey example)
# and the day's natural sweep endpoints.
_RAL_CODE_LIGHTNESS: dict[str, float] = {
    "9010": 1.00,  # pure white — lightest (sweep start)
    "9016": 1.00,  # traffic white
    "9003": 0.98,  # signal white
    "1015": 0.90,  # light ivory
    "7035": 0.72,  # light grey
    "7038": 0.70,  # agate grey
    "7040": 0.62,  # window grey
    "7042": 0.55,  # traffic grey A
    "7016": 0.20,  # anthracite grey — dark
    "7021": 0.12,  # black grey
    "9011": 0.03,  # graphite black
    "9017": 0.03,  # traffic black
    "9005": 0.00,  # jet black — darkest (sweep end)
}

# Where an order has no resolvable colour: treated as the darkest so a "no colour" order sorts to the
# end of the sweep rather than jumping the light start (and never claims a same-colour neighbour).
_UNKNOWN_LIGHTNESS = -1.0

# Default "small" m² bound for the line-assignment lever — an order at/under this *and* with no
# same-colour neighbour is a manual candidate. Tied to the 100 m² odzysk/paint threshold so "small"
# means "below the threshold that already governs changeover/paint economics".
SMALL_ORDER_M2_THRESHOLD = 100.0


def ral_lightness(ral_code: str | None) -> float:
    """Approximate lightness (0.0 darkest … 1.0 lightest) for a RAL Classic code; see module docstring.

    ⚠️ Single point to revisit (the open colour-similarity question). Resolves a full-code anchor first
    (white/black/named greys), else the colour-group first digit, else ``_UNKNOWN_LIGHTNESS`` for a
    missing/unparseable code so it sweeps last.
    """
    if not ral_code:
        return _UNKNOWN_LIGHTNESS
    digits = "".join(ch for ch in ral_code if ch.isdigit())
    if not digits:
        return _UNKNOWN_LIGHTNESS
    if digits in _RAL_CODE_LIGHTNESS:
        return _RAL_CODE_LIGHTNESS[digits]
    return _RAL_GROUP_LIGHTNESS.get(int(digits[0]), 0.5)


@dataclass(frozen=True)
class ColourOrderable:
    """The minimal projection of an order the within-day colour sweep needs.

    ``colour_key`` is the colour identity used to group identical colours (zero changeover); ``ral_code``
    drives the light→dark lightness of a colour *change*. ``None`` colour sweeps last.
    """

    work_order_id: int
    colour_key: str | None
    ral_code: str | None


def light_to_dark_order(orders: Sequence[ColourOrderable]) -> list[int]:
    """Order a day's orders into a light→dark sweep with identical colours grouped (N49-5).

    A *group* is one colour identity; groups are swept lightest → darkest by ``ral_lightness`` (the
    expensive dark→light reset thus happens at most once at the very end). Within a group the order is
    deterministic by work-order id, and groups of equal lightness tie-break on lightness-then-id so the
    result never depends on input order. The "no colour" group sweeps last.
    """
    # Each colour group's lightness (every member shares the colour, so the first member is enough) and
    # its members in id order.
    members: dict[str | None, list[int]] = {}
    group_lightness: dict[str | None, float] = {}
    for order in orders:
        members.setdefault(order.colour_key, []).append(order.work_order_id)
        if order.colour_key not in group_lightness:
            group_lightness[order.colour_key] = ral_lightness(order.ral_code)

    ordered_keys = sorted(
        members,
        # Lightest first (descending lightness); a missing colour (-1) naturally sinks last. Tie-break on
        # the colour identity string so equal-lightness groups are deterministic.
        key=lambda key: (-group_lightness[key], key is None, key or ""),
    )

    result: list[int] = []
    for key in ordered_keys:
        result.extend(sorted(members[key]))
    return result


@dataclass(frozen=True)
class SequencedOrder:
    """An order in its day-sequence position — the inputs the size+direction changeover cost needs."""

    colour_key: str | None
    ral_code: str | None
    total_area_m2: float | None


def sequence_changeover_minutes(orders: Sequence[SequencedOrder]) -> float:
    """Total changeover minutes for a day's ordered sequence, by size + direction (N49-5 feeds N49-6).

    Walks consecutive orders: a same-colour adjacency costs **zero** (no clean); a colour change costs
    ``capacity.changeover_minutes_for_transition`` scaled by the *next* order's size (100 m² band) and
    the colour direction (light→dark cheap via ``ral_lightness``, dark→light full clean). Because the
    within-day order is a light→dark sweep (``light_to_dark_order``), most changes are the cheap
    direction — so a better sweep visibly lowers this number, which the capacity model turns into m².
    """
    total = 0.0
    for previous, current in zip(orders, orders[1:]):
        if previous.colour_key is not None and previous.colour_key == current.colour_key:
            continue  # same colour run — no changeover
        light_to_dark = ral_lightness(previous.ral_code) >= ral_lightness(current.ral_code)
        total += changeover_minutes_for_transition(
            next_order_m2=current.total_area_m2,
            light_to_dark=light_to_dark,
        )
    return total


def average_changeover_minutes(orders: Sequence[SequencedOrder]) -> float:
    """Mean minutes per colour change for a sequence (total ÷ change count); 0 when no change occurs.

    Lets the per-day capacity model — which costs ``changeover_count × minutes_each`` — consume a single
    size+direction-aware ``minutes_each`` derived from the real sequence, instead of a flat per-change
    constant (N49-6). So the capacity m²-loss reflects size + direction, not just a count.
    """
    changes = 0
    for previous, current in zip(orders, orders[1:]):
        if previous.colour_key is None or previous.colour_key != current.colour_key:
            changes += 1
    if changes == 0:
        return 0.0
    return sequence_changeover_minutes(orders) / changes


def colour_neighbour_counts(colour_keys: Sequence[str | None]) -> dict[str | None, int]:
    """How many orders share each colour identity (``None`` excluded — "no colour" is never a group)."""
    counts: dict[str | None, int] = {}
    for key in colour_keys:
        if key is None:
            continue
        counts[key] = counts.get(key, 0) + 1
    return counts


@dataclass(frozen=True)
class LineSuggestion:
    """The planner's suggested line for one order (N49-8), with the reason, before any manager override."""

    work_order_id: int
    suggested_production_type: str  # ProductionType value ("MANUAL" / "AUTOMATIC")
    is_colour_orphan: bool
    is_small: bool


def suggest_line(
    *,
    work_order_id: int,
    total_area_m2: float | None,
    is_colour_orphan: bool,
    small_threshold_m2: float = SMALL_ORDER_M2_THRESHOLD,
) -> LineSuggestion:
    """Suggest a line for one order (N49-8): small **and** colour-orphan → manual, else automatic.

    An order with **no same-colour neighbour** to group with that is also **small** (≤ the threshold)
    gains nothing from the automatic booth's colour-run grouping, so it goes to manual (the overflow
    valve); everything else stays automatic so it can join a colour run / keep the booth fed. A missing
    m² is treated as not-small (kept on automatic, the safe default). The manager can override.
    """
    area = total_area_m2 if total_area_m2 is not None else float("inf")
    is_small = area <= small_threshold_m2
    suggested = "MANUAL" if (is_small and is_colour_orphan) else "AUTOMATIC"
    return LineSuggestion(
        work_order_id=work_order_id,
        suggested_production_type=suggested,
        is_colour_orphan=is_colour_orphan,
        is_small=is_small,
    )
