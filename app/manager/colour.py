"""Within-day colour grouping + line-assignment lever (N49-5 / N49-8 under NA49).

Two within-day planning levers live here so they cannot drift:

* **Colour grouping (N49-5).** Within a day's placed orders, group identical colours into runs (a
  same-colour adjacency costs zero changeover). A colour *change* costs the size band only
  (``capacity.changeover_minutes_for_transition``); the day's changeover cost is therefore just the
  number of colour changes × the per-change size band. Group order itself does not change the number
  of changes, so groups are ordered deterministically (alphabetically by colour identity, the "no
  colour" group last) to mirror the scheduler's COLOUR rule.

* **N49-8 line-assignment lever.** Suggest a line per order: a **small-m² colour-orphan** (no
  same-colour neighbour to group with) → **manual**; otherwise → **automatic** (so it can join a colour
  run / balance idle). The manager can override.

CHANGES #5 + #7 (owner-confirmed 2026-06-26) removed the colour-*direction* factor and the RAL-code
*lightness* guessing that used to drive a light→dark sweep: the factory does not pay a cheaper
changeover for light→dark, and a code-derived lightness was a guess, not a measured value. So colour
planning reduced to grouping identical colours — see ``docs/DECISIONS.md``.

Like ``scheduler.py`` / ``capacity.py`` / ``placement.py`` this module is deliberately DB-free: it
takes plain value objects and returns ordered ids / value objects, so the logic is fully unit-testable
and the service layer just supplies the data.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.manager.capacity import changeover_minutes_for_transition

# Default "small" m² bound for the line-assignment lever — an order at/under this *and* with no
# same-colour neighbour is a manual candidate. Tied to the 100 m² odzysk/paint threshold so "small"
# means "below the threshold that already governs changeover/paint economics".
SMALL_ORDER_M2_THRESHOLD = 100.0


@dataclass(frozen=True)
class ColourOrderable:
    """The minimal projection of an order the within-day colour grouping needs.

    ``colour_key`` is the colour identity used to group identical colours (zero changeover). ``None``
    colour groups last.
    """

    work_order_id: int
    colour_key: str | None


def group_identical_colours(orders: Sequence[ColourOrderable]) -> list[int]:
    """Order a day's orders so identical colours are adjacent (N49-5).

    Groups are ordered alphabetically by colour identity (deterministic, the "no colour" group last);
    within a group, ascending by work-order id. Group order does not affect the colour-change count, so
    any deterministic order works — alphabetical mirrors the scheduler's COLOUR rule.
    """
    members: dict[str | None, list[int]] = {}
    for order in orders:
        members.setdefault(order.colour_key, []).append(order.work_order_id)

    # Alphabetical by colour identity; the "no colour" group (None) sorts last.
    ordered_keys = sorted(members, key=lambda key: (key is None, key or ""))

    result: list[int] = []
    for key in ordered_keys:
        result.extend(sorted(members[key]))
    return result


@dataclass(frozen=True)
class SequencedOrder:
    """An order in its day-sequence position — the input the size-band changeover cost needs."""

    colour_key: str | None
    total_area_m2: float | None


def sequence_changeover_minutes(orders: Sequence[SequencedOrder]) -> float:
    """Total changeover minutes for a day's ordered sequence, by size band only (N49-5 feeds N49-6).

    Walks consecutive orders: a same-colour adjacency costs **zero** (no clean); a colour change costs
    ``capacity.changeover_minutes_for_transition`` for the *next* order's size band (100 m² threshold).
    No colour-direction factor (CHANGES #5).
    """
    total = 0.0
    for previous, current in zip(orders, orders[1:]):
        if previous.colour_key is not None and previous.colour_key == current.colour_key:
            continue  # same colour run — no changeover
        total += changeover_minutes_for_transition(next_order_m2=current.total_area_m2)
    return total


def average_changeover_minutes(orders: Sequence[SequencedOrder]) -> float:
    """Mean minutes per colour change for a sequence (total ÷ change count); 0 when no change occurs.

    Used by the **multi-day placement** (``placement.py``) as a single size-aware per-change rate: there
    each day's changeover count is only known mid-fill, so the loss is valued as ``count × this rate``
    rather than a flat per-change constant (N49-6). The fixed-sequence single-day / good-day models do
    not need it — they value their m² loss from the sequence's total directly.
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
