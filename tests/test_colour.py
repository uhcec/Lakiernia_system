"""Pure unit tests for within-day colour grouping + the line lever (N49-5 / N49-6 / N49-8).

Covers the DB-free logic in ``app/manager/colour.py``: grouping identical colours, the size-band
changeover cost (which composes ``capacity.changeover_minutes_for_transition``), and the
line-assignment lever. CHANGES #5 + #7 (2026-06-26) removed the colour-direction factor and the
RAL-code lightness sweep — colour planning is now just grouping identical colours.
"""

from app.manager.capacity import (
    CHANGEOVER_BAND_LARGE_MINUTES,
    CHANGEOVER_BAND_SMALL_MINUTES,
    changeover_minutes_for_transition,
)
from app.manager.colour import (
    ColourOrderable,
    SequencedOrder,
    average_changeover_minutes,
    colour_neighbour_counts,
    group_identical_colours,
    sequence_changeover_minutes,
    suggest_line,
)


# --- group_identical_colours (N49-5) -------------------------------------------------------------


def _o(order_id: int, colour: str | None) -> ColourOrderable:
    return ColourOrderable(work_order_id=order_id, colour_key=colour)


def test_groups_identical_colours_alphabetically() -> None:
    orders = [
        _o(1, "BLACK"),
        _o(2, "WHITE"),
        _o(3, "BLACK"),
        _o(4, "GREY"),
    ]
    # Groups ordered alphabetically (BLACK, GREY, WHITE); ascending id within a group.
    assert group_identical_colours(orders) == [1, 3, 4, 2]


def test_no_colour_order_groups_last() -> None:
    orders = [_o(1, None), _o(2, "WHITE")]
    assert group_identical_colours(orders) == [2, 1]


def test_single_colour_keeps_id_order() -> None:
    orders = [_o(3, "A"), _o(1, "A"), _o(2, "A")]
    assert group_identical_colours(orders) == [1, 2, 3]


def test_empty_order_list() -> None:
    assert group_identical_colours([]) == []


# --- changeover_minutes_for_transition (N49-6 size band only) ------------------------------------


def test_small_next_order_uses_small_band() -> None:
    # ≤ 100 m² → small band (15 min), regardless of direction (CHANGES #5).
    assert changeover_minutes_for_transition(next_order_m2=50.0) == CHANGEOVER_BAND_SMALL_MINUTES


def test_large_next_order_uses_large_band() -> None:
    # > 100 m² → large band (30 min).
    assert changeover_minutes_for_transition(next_order_m2=200.0) == CHANGEOVER_BAND_LARGE_MINUTES


def test_missing_size_is_conservative_large_band() -> None:
    assert changeover_minutes_for_transition(next_order_m2=None) == CHANGEOVER_BAND_LARGE_MINUTES


# --- sequence_changeover_minutes / average (N49-5 feeds N49-6) -----------------------------------


def _s(colour: str | None, m2: float | None) -> SequencedOrder:
    return SequencedOrder(colour_key=colour, total_area_m2=m2)


def test_same_colour_run_costs_zero() -> None:
    seq = [_s("A", 200.0), _s("A", 200.0)]
    assert sequence_changeover_minutes(seq) == 0.0


def test_changeover_cost_is_next_order_size_band_only() -> None:
    # A colour change costs the NEXT order's size band — no direction discount either way.
    into_large = [_s("A", 10.0), _s("B", 200.0)]  # next order > 100 → large band
    into_small = [_s("A", 200.0), _s("B", 10.0)]  # next order ≤ 100 → small band
    assert sequence_changeover_minutes(into_large) == CHANGEOVER_BAND_LARGE_MINUTES
    assert sequence_changeover_minutes(into_small) == CHANGEOVER_BAND_SMALL_MINUTES


def test_direction_does_not_change_cost() -> None:
    # Same two colours, swapped order — both pay the same band (the next order's size is identical).
    forward = [_s("W", 200.0), _s("B", 200.0)]
    reverse = [_s("B", 200.0), _s("W", 200.0)]
    assert sequence_changeover_minutes(forward) == sequence_changeover_minutes(reverse)


def test_average_changeover_minutes_divides_by_change_count() -> None:
    seq = [
        _s("W", 200.0),
        _s("W", 200.0),  # same colour — no change
        _s("B", 200.0),  # one change
    ]
    # One change only; average == its single cost.
    assert average_changeover_minutes(seq) == sequence_changeover_minutes(seq)


def test_average_is_zero_with_no_change() -> None:
    assert average_changeover_minutes([_s("A", 10.0)]) == 0.0
    assert average_changeover_minutes([]) == 0.0


# --- colour_neighbour_counts + suggest_line (N49-8) ----------------------------------------------


def test_neighbour_counts_ignore_none() -> None:
    counts = colour_neighbour_counts(["A", "A", None, "B", None])
    assert counts == {"A": 2, "B": 1}


def test_small_colour_orphan_goes_manual() -> None:
    s = suggest_line(work_order_id=1, total_area_m2=40.0, is_colour_orphan=True)
    assert s.suggested_production_type == "MANUAL"
    assert s.is_small is True
    assert s.is_colour_orphan is True


def test_small_but_has_colour_neighbour_stays_automatic() -> None:
    s = suggest_line(work_order_id=1, total_area_m2=40.0, is_colour_orphan=False)
    assert s.suggested_production_type == "AUTOMATIC"


def test_large_colour_orphan_stays_automatic() -> None:
    s = suggest_line(work_order_id=1, total_area_m2=500.0, is_colour_orphan=True)
    assert s.suggested_production_type == "AUTOMATIC"
    assert s.is_small is False


def test_missing_m2_is_not_small_stays_automatic() -> None:
    s = suggest_line(work_order_id=1, total_area_m2=None, is_colour_orphan=True)
    assert s.suggested_production_type == "AUTOMATIC"
    assert s.is_small is False
