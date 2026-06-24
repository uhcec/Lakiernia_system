"""Pure unit tests for the RAL-lightness colour ordering + line lever (N49-5 / N49-6 / N49-8).

Covers the DB-free logic in ``app/manager/colour.py``: the lightness mapping (the single open
assumption), the within-day light→dark sweep with identical-colour grouping, the size+direction-aware
changeover cost (which composes ``capacity.changeover_minutes_for_transition``), and the
line-assignment lever.
"""

from app.manager.capacity import (
    CHANGEOVER_BAND_LARGE_MINUTES,
    CHANGEOVER_BAND_SMALL_MINUTES,
    CHANGEOVER_LIGHT_TO_DARK_FACTOR,
    changeover_minutes_for_transition,
)
from app.manager.colour import (
    ColourOrderable,
    SequencedOrder,
    average_changeover_minutes,
    colour_neighbour_counts,
    light_to_dark_order,
    ral_lightness,
    sequence_changeover_minutes,
    suggest_line,
)


# --- ral_lightness (the single open assumption) -------------------------------------------------


def test_white_is_lighter_than_black() -> None:
    assert ral_lightness("RAL 9010") > ral_lightness("RAL 9005")
    assert ral_lightness("RAL 9016") == 1.0
    assert ral_lightness("RAL 9005") == 0.0


def test_grey_sits_between_white_and_black() -> None:
    # Owner's white→grey example: grey is darker than white, lighter than black.
    white = ral_lightness("RAL 9010")
    grey = ral_lightness("RAL 7035")
    black = ral_lightness("RAL 9005")
    assert black < grey < white


def test_unknown_or_missing_code_sorts_darkest() -> None:
    assert ral_lightness(None) < 0.0
    assert ral_lightness("") < 0.0
    assert ral_lightness("no-digits") < 0.0


def test_group_digit_used_when_no_full_code_anchor() -> None:
    # A yellow (group 1) reads lighter than a blue (group 5) by the group fallback.
    assert ral_lightness("RAL 1234") > ral_lightness("RAL 5234")


# --- light_to_dark_order (N49-5) -----------------------------------------------------------------


def _o(order_id: int, colour: str | None, ral: str | None) -> ColourOrderable:
    return ColourOrderable(work_order_id=order_id, colour_key=colour, ral_code=ral)


def test_groups_identical_colours_then_sweeps_light_to_dark() -> None:
    orders = [
        _o(1, "BLACK", "RAL 9005"),
        _o(2, "WHITE", "RAL 9010"),
        _o(3, "BLACK", "RAL 9005"),
        _o(4, "GREY", "RAL 7035"),
    ]
    # White (lightest) → grey → black (darkest); identical colours grouped, id order within a group.
    assert light_to_dark_order(orders) == [2, 4, 1, 3]


def test_no_colour_order_sweeps_last() -> None:
    orders = [_o(1, None, None), _o(2, "WHITE", "RAL 9010")]
    assert light_to_dark_order(orders) == [2, 1]


def test_single_colour_keeps_id_order() -> None:
    orders = [_o(3, "A", "RAL 5010"), _o(1, "A", "RAL 5010"), _o(2, "A", "RAL 5010")]
    assert light_to_dark_order(orders) == [1, 2, 3]


def test_empty_order_list() -> None:
    assert light_to_dark_order([]) == []


# --- changeover_minutes_for_transition (N49-6 band) ----------------------------------------------


def test_small_next_order_uses_small_band_dark_to_light() -> None:
    # < 100 m² and dark→light → full small band (15 min).
    assert (
        changeover_minutes_for_transition(next_order_m2=50.0, light_to_dark=False)
        == CHANGEOVER_BAND_SMALL_MINUTES
    )


def test_large_next_order_uses_large_band_dark_to_light() -> None:
    # > 100 m² and dark→light → full large band (30 min).
    assert (
        changeover_minutes_for_transition(next_order_m2=200.0, light_to_dark=False)
        == CHANGEOVER_BAND_LARGE_MINUTES
    )


def test_light_to_dark_is_cheaper_than_dark_to_light() -> None:
    dark_to_light = changeover_minutes_for_transition(next_order_m2=200.0, light_to_dark=False)
    light_to_dark = changeover_minutes_for_transition(next_order_m2=200.0, light_to_dark=True)
    assert light_to_dark == dark_to_light * CHANGEOVER_LIGHT_TO_DARK_FACTOR
    assert light_to_dark < dark_to_light


def test_missing_size_is_conservative_large_band() -> None:
    assert (
        changeover_minutes_for_transition(next_order_m2=None, light_to_dark=False)
        == CHANGEOVER_BAND_LARGE_MINUTES
    )


# --- sequence_changeover_minutes / average (N49-5 feeds N49-6) -----------------------------------


def _s(colour: str | None, ral: str | None, m2: float | None) -> SequencedOrder:
    return SequencedOrder(colour_key=colour, ral_code=ral, total_area_m2=m2)


def test_same_colour_run_costs_zero() -> None:
    seq = [_s("A", "RAL 5010", 200.0), _s("A", "RAL 5010", 200.0)]
    assert sequence_changeover_minutes(seq) == 0.0


def test_light_to_dark_sweep_cheaper_than_reverse() -> None:
    light_first = [_s("W", "RAL 9010", 200.0), _s("B", "RAL 9005", 200.0)]
    dark_first = [_s("B", "RAL 9005", 200.0), _s("W", "RAL 9010", 200.0)]
    assert sequence_changeover_minutes(light_first) < sequence_changeover_minutes(dark_first)
    # Dark→light large band = 30 min.
    assert sequence_changeover_minutes(dark_first) == CHANGEOVER_BAND_LARGE_MINUTES


def test_average_changeover_minutes_divides_by_change_count() -> None:
    seq = [
        _s("W", "RAL 9010", 200.0),
        _s("W", "RAL 9010", 200.0),  # same colour — no change
        _s("B", "RAL 9005", 200.0),  # one change (light→dark)
    ]
    # One change only; average == its single cost.
    assert average_changeover_minutes(seq) == sequence_changeover_minutes(seq)


def test_average_is_zero_with_no_change() -> None:
    assert average_changeover_minutes([_s("A", "RAL 1000", 10.0)]) == 0.0
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
