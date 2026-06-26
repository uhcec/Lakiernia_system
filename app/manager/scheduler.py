"""Pure painting auto-scheduler (NA33, the painting-plan sub-part of NA49).

This module is deliberately free of any database / ORM dependency: it takes plain value objects and
the manager's configured rule order, and returns a proposed ordering plus a colour-changeover count.
That keeps the optimisation logic fully unit-testable and lets the service layer stay thin.

Model: the proposal is a lexicographic sort of the active orders along the *enabled* rules in the
manager's priority order (see ``ScheduleRuleKey``), with a deterministic final tie-break on the work
order id. Each rule contributes one independent per-order sort key, so the priority order is the only
lever and the parts compose predictably.
"""

from collections.abc import Collection, Sequence
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


def _rule_key(rule: ScheduleRuleKey, order: SchedulableOrder) -> tuple:
    """The sort key contributed by a single rule for one order (ascending = earlier in the plan)."""
    if rule is ScheduleRuleKey.COLOUR:
        # Group identical colours; the "no colour" bucket sorts last, then alphabetically by colour.
        return (order.colour_key is None, order.colour_key or "")
    if rule is ScheduleRuleKey.DEADLINE:
        # Earliest pickup first; orders without a date sort last.
        return (order.planned_pickup_date is None, order.planned_pickup_date or date.max)
    raise ValueError(f"Unknown schedule rule: {rule!r}")


def propose_sequence(
    orders: Sequence[SchedulableOrder],
    rules: Sequence[ScheduleRuleKey],
) -> list[int]:
    """Return the proposed ordering of work-order ids for the given (enabled, ordered) rules.

    With no rules the order is deterministic by id, so an empty/all-disabled config still yields a
    stable result rather than an arbitrary one.
    """
    def composite_key(order: SchedulableOrder) -> tuple:
        key: tuple = ()
        for rule in rules:
            key += _rule_key(rule, order)
        # Deterministic final tie-break so the proposal never depends on input order.
        return key + (order.work_order_id,)

    return [order.work_order_id for order in sorted(orders, key=composite_key)]


def arrange_with_locks(
    optimised_ids: Sequence[int],
    current_order_ids: Sequence[int],
    *,
    pinned_ids: Collection[int],
    urgent_ids: Collection[int],
) -> list[int]:
    """Re-apply the manager's planning locks on top of an optimiser proposal (NA49.K).

    Without locks, pressing "Ułóż automatycznie" overwrites every manual tweak. This honours two locks
    so the optimiser arranges only the *free* orders around the ones the manager fixed:

    - ``urgent`` orders are forced to the very front of the line (kept in optimiser-preferred order
      among themselves);
    - ``pinned`` orders keep their **slot in the non-urgent sequence** — their index among the orders
      in ``current_order_ids`` (the line's live queue order) once urgents are removed — so they do not
      move when the rest is re-optimised;
    - every other order flows into the remaining slots in ``optimised_ids`` order.

    ``optimised_ids`` and ``current_order_ids`` are expected to cover the same set of ids (the line's
    active planned orders); a pin/urgent id is assumed to be in both. Urgent wins if an id is somehow in
    both lock sets.
    """
    urgent = set(urgent_ids)
    pinned = set(pinned_ids) - urgent

    front = [order_id for order_id in optimised_ids if order_id in urgent]
    # Non-urgent orders in their current queue order; pinned ones are fixed anchors at their index here.
    non_urgent_current = [order_id for order_id in current_order_ids if order_id not in urgent]
    free_optimised = iter(
        order_id
        for order_id in optimised_ids
        if order_id not in urgent and order_id not in pinned
    )
    tail = [
        order_id if order_id in pinned else next(free_optimised)
        for order_id in non_urgent_current
    ]
    return front + tail


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
