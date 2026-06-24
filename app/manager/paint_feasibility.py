"""Paint-stock feasibility for the planner — the hard block + forward "runs out at" view (N49-7).

Out-of-stock paint is a leading cause of a missed daily norm ("myśleli że jest, a jej nie ma"), so a
colour series whose paint is **not in stock cannot be planned** on the automatic line. This module is
the pure, DB-free arithmetic behind that rule: given the line's planned orders (in execution order),
their per-order predicted paint demand, the starting stock per colour series, and which colours are
*also* painted on the unmetered manual line, it walks the sequence and decides, per order:

* **BLOCKED** — a *metered* colour series (automatic-only, so its balance is trustworthy) that is
  **out of stock** (a tracked paint at ≤ 0 kg). This is the hard block: the planner refuses it.
* **WARNING** — either the series has *some* stock but the cumulative demand runs it dry partway down
  the sequence (the forward "runs out at order X" signal), or the colour is **manual-used** so its
  balance is low-confidence (the manual line consumes paint without metering it — owner: "niewykrywalne").
  A manual-used colour is **never** hard-blocked, only warned: we do not block on a possibly-stale balance.
* **OK** — covered by stock, or an untracked colour the inventory simply isn't following.

Like ``capacity.py`` / ``placement.py`` / ``measurement.py`` this is deliberately DB-free so the
arithmetic is fully unit-testable and the service layer only supplies the data.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum


class PaintFeasibilityStatus(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class PaintColourStock:
    """The starting paint position for one colour series the feasibility walk needs."""

    colour_key: str
    # Current inventory balance (kg). Meaningless unless ``is_tracked``.
    current_stock_kg: float
    # True when the colour has real stock movement history — genuinely delivered/managed, not the 0-kg
    # placeholder row auto-created when an order snapshots its colour. So a ≤ 0 balance means *known*
    # depleted, not never-stocked. The hard block fires only on a tracked, depleted, metered colour.
    is_tracked: bool
    # The colour is also painted on the unmetered MANUAL line → its balance is low-confidence → warn,
    # never hard-block.
    manual_used: bool


@dataclass(frozen=True)
class PlannedPaintOrder:
    """One planned automatic order projected for the feasibility walk."""

    work_order_id: int
    colour_key: str | None
    demand_kg: float


@dataclass(frozen=True)
class OrderPaintFeasibility:
    work_order_id: int
    colour_key: str | None
    demand_kg: float
    # The series' starting stock (0.0 for an untracked / colourless order).
    available_stock_kg: float
    # Cumulative demand on this colour series up to and including this order.
    cumulative_demand_kg: float
    # available_stock_kg − cumulative_demand_kg (negative once the series is overrun).
    remaining_after_kg: float
    is_tracked: bool
    manual_used: bool
    status: PaintFeasibilityStatus


@dataclass(frozen=True)
class PaintForwardView:
    """The line's forward paint outlook: per-order feasibility + the blocked / warned sets."""

    orders: list[OrderPaintFeasibility]
    blocked_order_ids: list[int]
    warning_order_ids: list[int]


def colour_series_blocked(stock: PaintColourStock) -> bool:
    """Whether a colour series is hard-blocked: tracked, metered (not manual-used), and out of stock.

    This is the single predicate the planner's plan-time gate and the forward view share, so the
    interactive "refuse to plan" and the board's blocked marker can never disagree.
    """
    return stock.is_tracked and not stock.manual_used and stock.current_stock_kg <= 0.0


def build_forward_view(
    orders: Sequence[PlannedPaintOrder],
    stock_by_colour: dict[str, PaintColourStock],
) -> PaintForwardView:
    """Walk the orders in execution order, costing each colour series down against its starting stock.

    ``orders`` must already be in the order the line will paint them (the "runs out at order X" point is
    sequence-dependent). A colourless order, or a colour with no stock entry, is treated as untracked →
    OK (the inventory isn't following it, so we make no claim).
    """
    cumulative: dict[str, float] = {}
    results: list[OrderPaintFeasibility] = []
    blocked: list[int] = []
    warned: list[int] = []

    for order in orders:
        stock = stock_by_colour.get(order.colour_key) if order.colour_key is not None else None
        demand = max(order.demand_kg, 0.0)

        if stock is None:
            results.append(
                OrderPaintFeasibility(
                    work_order_id=order.work_order_id,
                    colour_key=order.colour_key,
                    demand_kg=demand,
                    available_stock_kg=0.0,
                    cumulative_demand_kg=demand,
                    remaining_after_kg=0.0,
                    is_tracked=False,
                    manual_used=False,
                    status=PaintFeasibilityStatus.OK,
                )
            )
            continue

        running = cumulative.get(order.colour_key, 0.0) + demand
        cumulative[order.colour_key] = running
        remaining = stock.current_stock_kg - running

        if colour_series_blocked(stock):
            status = PaintFeasibilityStatus.BLOCKED
        elif stock.manual_used and remaining < 0.0:
            status = PaintFeasibilityStatus.WARNING
        elif not stock.manual_used and stock.is_tracked and remaining < 0.0:
            # Tracked, metered colour with *some* stock that the cumulative demand overruns — the
            # forward "runs out at this order" warning (a partial shortfall, not a full out-of-stock).
            status = PaintFeasibilityStatus.WARNING
        else:
            status = PaintFeasibilityStatus.OK

        if status is PaintFeasibilityStatus.BLOCKED:
            blocked.append(order.work_order_id)
        elif status is PaintFeasibilityStatus.WARNING:
            warned.append(order.work_order_id)

        results.append(
            OrderPaintFeasibility(
                work_order_id=order.work_order_id,
                colour_key=order.colour_key,
                demand_kg=demand,
                available_stock_kg=stock.current_stock_kg,
                cumulative_demand_kg=round(running, 3),
                remaining_after_kg=round(remaining, 3),
                is_tracked=stock.is_tracked,
                manual_used=stock.manual_used,
                status=status,
            )
        )

    return PaintForwardView(orders=results, blocked_order_ids=blocked, warning_order_ids=warned)
