"""Pure unit tests for the painting auto-scheduler (NA33) — no DB, just the ordering logic."""

from datetime import date

from app.manager.enums import ScheduleRuleKey
from app.manager.scheduler import (
    SchedulableOrder,
    arrange_with_locks,
    count_colour_changeovers,
    propose_sequence,
)


def _order(work_order_id: int, colour: str | None, pickup: date | None = None, m2: float | None = 10.0) -> SchedulableOrder:
    return SchedulableOrder(
        work_order_id=work_order_id,
        colour_key=colour,
        planned_pickup_date=pickup,
        total_area_m2=m2,
    )


def test_colour_rule_clusters_same_colour_with_id_tiebreak() -> None:
    orders = [_order(1, "B"), _order(2, "A"), _order(3, "B"), _order(4, "A")]
    # Groups ordered alphabetically (A before B); within a group, deterministic by id.
    assert propose_sequence(orders, [ScheduleRuleKey.COLOUR]) == [2, 4, 1, 3]


def test_default_priority_colour_then_deadline_then_changeover() -> None:
    orders = [
        _order(1, "A", date(2026, 1, 5)),
        _order(2, "A", date(2026, 1, 1)),
        _order(3, "B", date(2026, 1, 2)),
    ]
    rules = [ScheduleRuleKey.COLOUR, ScheduleRuleKey.DEADLINE, ScheduleRuleKey.CHANGEOVER]
    # Colour clusters first (A before B); within A the earlier deadline (id 2) leads.
    assert propose_sequence(orders, rules) == [2, 1, 3]


def test_deadline_primary_clusters_colour_within_same_date() -> None:
    orders = [
        _order(1, "A", date(2026, 1, 1)),
        _order(2, "B", date(2026, 1, 1)),
        _order(3, "A", date(2026, 1, 1)),
    ]
    # Same date everywhere, so the secondary COLOUR rule clusters A (ids 1,3) before B (id 2).
    assert propose_sequence(orders, [ScheduleRuleKey.DEADLINE, ScheduleRuleKey.COLOUR]) == [1, 3, 2]


def test_changeover_rule_does_largest_m2_colour_run_first() -> None:
    orders = [_order(1, "A", m2=10.0), _order(2, "A", m2=10.0), _order(3, "B", m2=50.0)]
    # Colour B carries 50 m² vs A's 20, so the bigger run leads (maximise m²/day between cleans).
    assert propose_sequence(orders, [ScheduleRuleKey.CHANGEOVER]) == [3, 1, 2]


def test_orders_without_colour_sort_last() -> None:
    orders = [_order(1, None), _order(2, "A")]
    assert propose_sequence(orders, [ScheduleRuleKey.COLOUR]) == [2, 1]


def test_no_rules_is_deterministic_by_id() -> None:
    orders = [_order(3, "A"), _order(1, "B"), _order(2, "C")]
    assert propose_sequence(orders, []) == [1, 2, 3]


def test_count_colour_changeovers() -> None:
    assert count_colour_changeovers(["A", "A", "B", "B"]) == 1
    assert count_colour_changeovers(["A", "B", "A", "B"]) == 3
    assert count_colour_changeovers(["A"]) == 0
    assert count_colour_changeovers([]) == 0
    # None is a distinct "no colour" bucket.
    assert count_colour_changeovers(["A", None, None, "A"]) == 2


def test_arrange_with_locks_no_locks_returns_optimised_order() -> None:
    # With no pins/urgents the arranged order is exactly the optimiser's order (NA49.K).
    optimised = [3, 1, 2]
    current = [1, 2, 3]
    assert arrange_with_locks(optimised, current, pinned_ids=set(), urgent_ids=set()) == [3, 1, 2]


def test_arrange_with_locks_pinned_keeps_its_queue_slot() -> None:
    # Order 2 is pinned at its current slot (index 1 of the queue); the free orders (optimised 4,3,1)
    # fill the other slots in optimiser order, around the fixed pin.
    optimised = [4, 3, 1, 2]
    current = [1, 2, 3, 4]
    arranged = arrange_with_locks(optimised, current, pinned_ids={2}, urgent_ids=set())
    assert arranged == [4, 2, 3, 1]
    assert arranged.index(2) == current.index(2)  # pin did not move from its slot


def test_arrange_with_locks_urgent_jumps_to_front() -> None:
    # Order 3 is urgent → forced to the very front; everything else keeps the optimiser order.
    optimised = [1, 2, 3, 4]
    current = [1, 2, 3, 4]
    assert arrange_with_locks(optimised, current, pinned_ids=set(), urgent_ids={3}) == [3, 1, 2, 4]


def test_arrange_with_locks_urgent_and_pin_together() -> None:
    # Urgent (5) leads; pinned (2) holds its slot among the non-urgent orders; the rest optimise around.
    optimised = [5, 4, 3, 2, 1]
    current = [1, 2, 3, 4, 5]
    arranged = arrange_with_locks(optimised, current, pinned_ids={2}, urgent_ids={5})
    assert arranged[0] == 5  # urgent first
    # Non-urgent current order is [1,2,3,4]; pin 2 keeps index 1; free optimised [4,3,1] fill the gaps.
    assert arranged == [5, 4, 2, 3, 1]


def test_arrange_with_locks_urgent_wins_when_both_flags_collide() -> None:
    # Defensive: an id in both lock sets is treated as urgent (front), not pinned.
    arranged = arrange_with_locks([1, 2], [1, 2], pinned_ids={1}, urgent_ids={1})
    assert arranged == [1, 2]


def test_proposal_reduces_changeovers_versus_interleaved_input() -> None:
    # An interleaved A/B/A/B input (3 changeovers) collapses to A,A,B,B (1 changeover).
    orders = [_order(1, "A"), _order(2, "B"), _order(3, "A"), _order(4, "B")]
    proposed = propose_sequence(orders, [ScheduleRuleKey.COLOUR])
    colour_by_id = {order.work_order_id: order.colour_key for order in orders}
    before = count_colour_changeovers([colour_by_id[i] for i in [1, 2, 3, 4]])
    after = count_colour_changeovers([colour_by_id[i] for i in proposed])
    assert before == 3
    assert after == 1
