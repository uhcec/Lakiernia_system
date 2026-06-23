"""Pure painting auto-scheduler (NA33, the painting-plan sub-part of NA49).

This module is deliberately free of any database / ORM dependency: it takes plain value objects and
the manager's configured rule order, and returns a proposed ordering plus a colour-changeover count.
That keeps the optimisation logic fully unit-testable and lets the service layer stay thin.

Model: the proposal is a lexicographic sort of the active orders along the *enabled* rules in the
manager's priority order (see ``ScheduleRuleKey``), with a deterministic final tie-break on the work
order id. Each rule contributes one independent per-order sort key, so the priority order is the only
lever and the parts compose predictably.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from app.manager.enums import ScheduleRuleKey


@dataclass(frozen=True)
class SchedulableOrder:
    """The minimal projection of a planned work order the scheduler needs to order it.

    ``colour_key`` is the colour identity used for grouping (same paint = same string); ``None`` means
    the order has no colour and is treated as its own "no colour" bucket that sorts last.
    """

    work_order_id: int
    colour_key: str | None
    planned_pickup_date: date | None
    total_area_m2: float | None


def _colour_group_totals(orders: Iterable[SchedulableOrder]) -> dict[str | None, float]:
    """Total m² per colour group — drives the CHANGEOVER ("largest runs first") rule."""
    totals: dict[str | None, float] = {}
    for order in orders:
        totals[order.colour_key] = totals.get(order.colour_key, 0.0) + (order.total_area_m2 or 0.0)
    return totals


def _rule_key(
    rule: ScheduleRuleKey,
    order: SchedulableOrder,
    group_totals: dict[str | None, float],
) -> tuple:
    """The sort key contributed by a single rule for one order (ascending = earlier in the plan)."""
    if rule is ScheduleRuleKey.COLOUR:
        # Group identical colours; the "no colour" bucket sorts last, then alphabetically by colour.
        return (order.colour_key is None, order.colour_key or "")
    if rule is ScheduleRuleKey.DEADLINE:
        # Earliest pickup first; orders without a date sort last.
        return (order.planned_pickup_date is None, order.planned_pickup_date or date.max)
    if rule is ScheduleRuleKey.CHANGEOVER:
        # Largest single-colour run first (maximise m²/day); members of a colour share this key, so
        # this also keeps a colour together.
        return (-group_totals.get(order.colour_key, 0.0),)
    raise ValueError(f"Unknown schedule rule: {rule!r}")


def propose_sequence(
    orders: Sequence[SchedulableOrder],
    rules: Sequence[ScheduleRuleKey],
) -> list[int]:
    """Return the proposed ordering of work-order ids for the given (enabled, ordered) rules.

    With no rules the order is deterministic by id, so an empty/all-disabled config still yields a
    stable result rather than an arbitrary one.
    """
    group_totals = _colour_group_totals(orders)

    def composite_key(order: SchedulableOrder) -> tuple:
        key: tuple = ()
        for rule in rules:
            key += _rule_key(rule, order, group_totals)
        # Deterministic final tie-break so the proposal never depends on input order.
        return key + (order.work_order_id,)

    return [order.work_order_id for order in sorted(orders, key=composite_key)]


def count_colour_changeovers(colour_sequence: Sequence[str | None]) -> int:
    """Number of colour changes between consecutive orders in a sequence.

    A change is any adjacent pair whose colour identity differs (``None`` is a distinct "no colour").
    This is the headline number behind the "lepsze ułożenie (−N zmian koloru)" suggestion.
    """
    changeovers = 0
    for previous, current in zip(colour_sequence, colour_sequence[1:]):
        if previous != current:
            changeovers += 1
    return changeovers


def colour_changeovers_for_order_ids(
    ordered_ids: Sequence[int],
    colour_by_id: dict[int, str | None],
) -> int:
    """Convenience: colour-changeover count for a given id ordering using a colour lookup."""
    return count_colour_changeovers([colour_by_id.get(order_id) for order_id in ordered_ids])
