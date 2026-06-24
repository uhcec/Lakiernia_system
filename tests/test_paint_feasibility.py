"""Unit tests for the pure paint-feasibility core (N49-7).

Drives ``build_forward_view`` / ``colour_series_blocked`` with plain value objects — no DB — to pin the
hard-block vs warning vs OK arithmetic and the sequence-dependent "runs out at order X" point.
"""

from app.manager.paint_feasibility import (
    PaintColourStock,
    PaintFeasibilityStatus,
    PlannedPaintOrder,
    build_forward_view,
    colour_series_blocked,
)


def _stock(colour_key, qty, *, tracked=True, manual_used=False) -> PaintColourStock:
    return PaintColourStock(
        colour_key=colour_key,
        current_stock_kg=qty,
        is_tracked=tracked,
        manual_used=manual_used,
    )


def test_sufficient_stock_is_all_ok() -> None:
    orders = [
        PlannedPaintOrder(work_order_id=1, colour_key="X", demand_kg=10.0),
        PlannedPaintOrder(work_order_id=2, colour_key="X", demand_kg=10.0),
    ]
    view = build_forward_view(orders, {"X": _stock("X", 100.0)})
    assert [o.status for o in view.orders] == [PaintFeasibilityStatus.OK, PaintFeasibilityStatus.OK]
    assert view.blocked_order_ids == []
    assert view.warning_order_ids == []
    assert view.orders[1].remaining_after_kg == 80.0


def test_metered_out_of_stock_is_hard_blocked() -> None:
    orders = [PlannedPaintOrder(work_order_id=1, colour_key="X", demand_kg=10.0)]
    view = build_forward_view(orders, {"X": _stock("X", 0.0)})
    assert view.orders[0].status is PaintFeasibilityStatus.BLOCKED
    assert view.blocked_order_ids == [1]


def test_manual_used_out_of_stock_warns_never_blocks() -> None:
    orders = [PlannedPaintOrder(work_order_id=1, colour_key="X", demand_kg=10.0)]
    view = build_forward_view(orders, {"X": _stock("X", 0.0, manual_used=True)})
    assert view.orders[0].status is PaintFeasibilityStatus.WARNING
    assert view.blocked_order_ids == []
    assert view.warning_order_ids == [1]


def test_partial_shortfall_warns_at_the_runs_out_order() -> None:
    # 25 kg stock; first order (10) fits, second (20) overruns it → the second is the "runs out" warning.
    orders = [
        PlannedPaintOrder(work_order_id=1, colour_key="X", demand_kg=10.0),
        PlannedPaintOrder(work_order_id=2, colour_key="X", demand_kg=20.0),
    ]
    view = build_forward_view(orders, {"X": _stock("X", 25.0)})
    assert view.orders[0].status is PaintFeasibilityStatus.OK
    assert view.orders[1].status is PaintFeasibilityStatus.WARNING
    assert view.orders[1].remaining_after_kg == -5.0
    assert view.blocked_order_ids == []
    assert view.warning_order_ids == [2]


def test_first_order_demand_over_stock_is_hard_blocked() -> None:
    # 5 kg stock but the FIRST order needs 100 kg → can't be painted from stock → hard block (NA54),
    # not just a warning.
    orders = [PlannedPaintOrder(work_order_id=1, colour_key="X", demand_kg=100.0)]
    view = build_forward_view(orders, {"X": _stock("X", 5.0)})
    assert view.orders[0].status is PaintFeasibilityStatus.BLOCKED
    assert view.blocked_order_ids == [1]


def test_first_order_fits_then_second_overruns_blocks_only_when_first_short() -> None:
    # First order (4) fits 5 kg → OK; second (4) overruns → WARNING (runs short later, deliver before then).
    orders = [
        PlannedPaintOrder(work_order_id=1, colour_key="X", demand_kg=4.0),
        PlannedPaintOrder(work_order_id=2, colour_key="X", demand_kg=4.0),
    ]
    view = build_forward_view(orders, {"X": _stock("X", 5.0)})
    assert view.orders[0].status is PaintFeasibilityStatus.OK
    assert view.orders[1].status is PaintFeasibilityStatus.WARNING
    assert view.blocked_order_ids == []
    assert view.warning_order_ids == [2]


def test_untracked_colour_makes_no_claim() -> None:
    # No stock entry for the colour → the inventory isn't following it → OK, no block.
    orders = [PlannedPaintOrder(work_order_id=1, colour_key="X", demand_kg=10.0)]
    view = build_forward_view(orders, {})
    assert view.orders[0].status is PaintFeasibilityStatus.OK
    assert view.orders[0].is_tracked is False
    assert view.blocked_order_ids == []


def test_colourless_order_is_ok() -> None:
    orders = [PlannedPaintOrder(work_order_id=1, colour_key=None, demand_kg=10.0)]
    view = build_forward_view(orders, {"X": _stock("X", 0.0)})
    assert view.orders[0].status is PaintFeasibilityStatus.OK


def test_two_series_are_costed_independently() -> None:
    orders = [
        PlannedPaintOrder(work_order_id=1, colour_key="X", demand_kg=10.0),
        PlannedPaintOrder(work_order_id=2, colour_key="Y", demand_kg=10.0),
    ]
    view = build_forward_view(orders, {"X": _stock("X", 100.0), "Y": _stock("Y", 0.0)})
    assert view.orders[0].status is PaintFeasibilityStatus.OK
    assert view.orders[1].status is PaintFeasibilityStatus.BLOCKED
    assert view.blocked_order_ids == [2]


def test_colour_series_blocked_predicate() -> None:
    assert colour_series_blocked(_stock("X", 0.0)) is True
    assert colour_series_blocked(_stock("X", -1.0)) is True
    assert colour_series_blocked(_stock("X", 5.0)) is False  # in stock, no demand given
    assert colour_series_blocked(_stock("X", 0.0, manual_used=True)) is False  # unmetered → warn
    assert colour_series_blocked(_stock("X", 0.0, tracked=False)) is False  # untracked → no claim
    # Demand-aware (NA54): some stock but the first order needs more than is on hand → blocked.
    assert colour_series_blocked(_stock("X", 5.0), first_order_demand_kg=100.0) is True
    assert colour_series_blocked(_stock("X", 5.0), first_order_demand_kg=3.0) is False
    # Demand-aware block still respects the manual-used / untracked escapes.
    assert colour_series_blocked(_stock("X", 5.0, manual_used=True), first_order_demand_kg=100.0) is False
    assert colour_series_blocked(_stock("X", 5.0, tracked=False), first_order_demand_kg=100.0) is False
