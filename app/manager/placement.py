"""Deadline-feasible multi-day placement (N49-4 under NA49).

The day-capacity model (``capacity.py``, N49-3) bounds *one* day; this module lays the line's orders
across a sequence of working days so no hard pickup deadline is missed. It is the heart of the planner:
the factory's real job is to hit the daily m² floor while shipping every order on time, and one large
order can fill a whole day, so "what order, on which day?" is a capacity question, not a single-list
sort.

Objective hierarchy (``docs/WORKFLOW.md`` "Target planning model"): **hard deadline > daily floor >
colour grouping.** This module owns the first level — earliest-deadline-first (EDF) placement into
day-buckets bounded by the day's *net* ceiling — and reports, per order, whether the day it lands on
still meets its pickup date (a "won't make it" warning). Within-day line assignment and the light→dark
colour sweep are the next levels (N49-5/N49-8) and deliberately out of scope here; within a day this
keeps the EDF order.

A **colour change consumes capacity** (``capacity.changeover_loss_m2``), so each day's usable ceiling
shrinks as more distinct colours pile onto it — the same arithmetic the single-day model uses, shared so
the two never drift. Packing against the *net* ceiling keeps the deadline promise conservative: a day is
only called feasible for work it can paint *after* paying for its colour changes.

Like ``scheduler.py`` / ``capacity.py`` / ``measurement.py`` this module is deliberately DB-free: it
takes plain value objects (the orders + the working-day calendar + the learned changeover cost) and
returns a ``MultiDayPlan`` value object, so the placement arithmetic is fully unit-testable and the
service layer only supplies the data.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from app.manager.capacity import (
    CEILING_BOOTH_RATE_M2_PER_H,
    ShiftLength,
    changeover_loss_m2,
    floor_m2,
    shift_hours,
)
from app.manager.scheduler import count_colour_changeovers

# Working-day calendar: Saturday (5) and Sunday (6) are non-working. CONFIRMED 2026-06-24 (NA56): the
# shop runs Mon–Fri; a holiday list is deferred (none modelled yet). This is the single configurable
# point — ``working_days_from(..., weekend_weekdays=...)`` overrides it, so a future shop-specific
# calendar passes its own set here rather than editing the module. Deadlines are plain calendar dates, so
# a part due on a weekend is simply met by the preceding working day (placed date ≤ pickup date holds).
DEFAULT_WEEKEND_WEEKDAYS: frozenset[int] = frozenset({5, 6})


@dataclass(frozen=True)
class PlaceableOrder:
    """The minimal projection of a planned order the placement needs.

    ``planned_pickup_date`` is the hard deadline (required at intake since N49-1). ``colour_key`` is the
    colour identity used to count per-day colour changes (``None`` = no colour); ``total_area_m2`` is the
    capacity the order consumes.
    """

    work_order_id: int
    total_area_m2: float | None
    planned_pickup_date: date
    colour_key: str | None = None


@dataclass(frozen=True)
class OrderPlacement:
    """Where one order landed and whether that still ships it on time."""

    work_order_id: int
    day_index: int
    # The working-day date the order is scheduled on; None when it falls beyond the supplied horizon.
    scheduled_date: date | None
    planned_pickup_date: date
    # scheduled_date is known and ≤ the pickup deadline (beyond-horizon counts as NOT meeting it).
    meets_deadline: bool
    # Calendar days the scheduled date is past the deadline (0 when on time or beyond the horizon).
    days_late: int


@dataclass(frozen=True)
class PlannedDay:
    """One working day in the plan: its capacity bucket and the orders placed in it."""

    day_index: int
    scheduled_date: date | None
    shift_length: ShiftLength
    floor_m2: float
    gross_ceiling_m2: float
    net_ceiling_m2: float
    changeover_count: int
    placed_order_ids: list[int]
    placed_m2: float
    below_floor: bool
    over_ceiling: bool


@dataclass(frozen=True)
class MultiDayPlan:
    """The line's orders laid across working days, with the deadline-feasibility verdict."""

    shift_length: ShiftLength
    horizon_working_days: int
    days: list[PlannedDay]
    placements: list[OrderPlacement]
    # Orders that miss their deadline or fall beyond the planning horizon (the "won't make it" set).
    infeasible_order_ids: list[int]


def working_days_from(
    start: date,
    count: int,
    *,
    weekend_weekdays: frozenset[int] = DEFAULT_WEEKEND_WEEKDAYS,
) -> list[date]:
    """The next ``count`` working days on/after ``start`` (skipping the configured weekend weekdays)."""
    days: list[date] = []
    current = start
    while len(days) < max(count, 0):
        if current.weekday() not in weekend_weekdays:
            days.append(current)
        current += timedelta(days=1)
    return days


class _OpenDay:
    """Mutable accumulator for the day currently being filled (collapsed to a ``PlannedDay`` at close)."""

    __slots__ = ("colours", "order_ids", "placed_m2")

    def __init__(self) -> None:
        self.colours: list[str | None] = []
        self.order_ids: list[int] = []
        self.placed_m2: float = 0.0


def place_orders(
    orders: Sequence[PlaceableOrder],
    *,
    working_days: Sequence[date],
    shift_length: ShiftLength,
    changeover_minutes: float,
    ceiling_rate_m2_per_h: float = CEILING_BOOTH_RATE_M2_PER_H,
    first_day_hours: float | None = None,
) -> MultiDayPlan:
    """Place orders earliest-deadline-first into net-ceiling-bounded working days.

    Greedy EDF fill: orders are sorted by ``(planned_pickup_date, work_order_id)`` and packed into the
    current day until the next order would exceed that day's *net* ceiling (gross booth capacity minus
    the m² lost to the day's colour changes), then a new day opens. An order larger than a whole day's
    net ceiling is still placed alone on its own day, which is flagged ``over_ceiling`` (it physically
    spans more than a day — a real signal for the manager, not an error). Day index ``i`` maps to
    ``working_days[i]``; orders past the supplied horizon get ``scheduled_date=None`` and count as
    infeasible.

    ``first_day_hours`` (NA56) pro-rates **day 0 only** to the hours left in today's shift: its gross
    ceiling and floor scale by ``first_day_hours / full shift hours`` (so a plan built mid-shift doesn't
    promise a whole day today). ``None`` (the default) means a full day 0 — identical to the prior model.

    Each **later** day is *judged* against its own shift (NA57): the fill above always uses the plan-level
    (physical full-day) ceiling to decide day boundaries, but for display a day that holds little work is
    classified SHORT — and measured against the short floor (500), not the long floor (800) — when its m²
    fit a short day's net ceiling. So an under-filled overflow day (e.g. 550 m²) reads as a sensible short
    day rather than a "failed" long day, while a genuinely under-target long day (e.g. 700 m²) still flags
    below floor. SHORT is only chosen when the work fits, so a day is never flagged over its own ceiling.
    """
    full_hours = shift_hours(shift_length)
    floor = floor_m2(shift_length)
    # Day 0 may be a partial day (planned mid-shift); every later day is a full working day for the FILL.
    day0_hours = first_day_hours if first_day_hours is not None else full_hours
    day0_fraction = day0_hours / full_hours if full_hours > 0 else 1.0

    def gross_ceiling_for(day_index: int) -> float:
        hours = day0_hours if day_index == 0 else full_hours
        return ceiling_rate_m2_per_h * hours

    def floor_for(day_index: int) -> float:
        return floor * day0_fraction if day_index == 0 else floor

    def changeover_loss(changeover_count: int) -> float:
        return changeover_loss_m2(changeover_count, changeover_minutes, ceiling_rate_m2_per_h)

    def net_ceiling(day_index: int, changeover_count: int) -> float:
        return max(gross_ceiling_for(day_index) - changeover_loss(changeover_count), 0.0)

    def display_shift_for(day_index: int, placed_m2: float, changeover_count: int) -> ShiftLength:
        """The shift a day is *judged* against for display (NA57). Day 0 keeps the plan-level shift (its
        floor is hours-pro-rated, NA56). A later day is SHORT when its work fits a short day's net ceiling
        AND is below the long-day floor — so an overflow day is measured against the short floor, not the
        long one — else LONG. SHORT only when the work fits, so it is never flagged over its own ceiling."""
        if day_index == 0:
            return shift_length
        short_net = max(ceiling_rate_m2_per_h * shift_hours(ShiftLength.SHORT) - changeover_loss(changeover_count), 0.0)
        if placed_m2 <= short_net and placed_m2 < floor_m2(ShiftLength.LONG):
            return ShiftLength.SHORT
        return ShiftLength.LONG

    ordered = sorted(orders, key=lambda order: (order.planned_pickup_date, order.work_order_id))

    closed_days: list[_OpenDay] = []
    current = _OpenDay()
    for order in ordered:
        area = max(order.total_area_m2 or 0.0, 0.0)
        tentative_changeovers = count_colour_changeovers(current.colours + [order.colour_key])
        if current.order_ids and current.placed_m2 + area > net_ceiling(len(closed_days), tentative_changeovers):
            closed_days.append(current)
            current = _OpenDay()
        current.colours.append(order.colour_key)
        current.order_ids.append(order.work_order_id)
        current.placed_m2 += area
    if current.order_ids:
        closed_days.append(current)

    days: list[PlannedDay] = []
    placement_day: dict[int, int] = {}
    for day_index, open_day in enumerate(closed_days):
        changeover_count = count_colour_changeovers(open_day.colours)
        # Display shift/floor/ceiling are judged PER DAY (NA57); day 0 keeps the plan-level shift with its
        # hours-pro-rated floor (NA56). The fill above already used the plan-level ceiling, so the day
        # membership is unchanged — only how each day is *labelled and measured* changes here.
        day_shift = display_shift_for(day_index, open_day.placed_m2, changeover_count)
        if day_index == 0:
            day_gross = gross_ceiling_for(0)
            day_floor = floor_for(0)
        else:
            day_gross = ceiling_rate_m2_per_h * shift_hours(day_shift)
            day_floor = floor_m2(day_shift)
        net = max(day_gross - changeover_loss(changeover_count), 0.0)
        scheduled_date = working_days[day_index] if day_index < len(working_days) else None
        for order_id in open_day.order_ids:
            placement_day[order_id] = day_index
        days.append(
            PlannedDay(
                day_index=day_index,
                scheduled_date=scheduled_date,
                shift_length=day_shift,
                floor_m2=round(day_floor, 2),
                gross_ceiling_m2=round(day_gross, 2),
                net_ceiling_m2=round(net, 2),
                changeover_count=changeover_count,
                placed_order_ids=list(open_day.order_ids),
                placed_m2=round(open_day.placed_m2, 2),
                below_floor=open_day.placed_m2 < day_floor,
                over_ceiling=open_day.placed_m2 > net,
            )
        )

    placements: list[OrderPlacement] = []
    infeasible_order_ids: list[int] = []
    for order in ordered:
        day_index = placement_day[order.work_order_id]
        scheduled_date = working_days[day_index] if day_index < len(working_days) else None
        meets_deadline = scheduled_date is not None and scheduled_date <= order.planned_pickup_date
        days_late = (
            max((scheduled_date - order.planned_pickup_date).days, 0)
            if scheduled_date is not None
            else 0
        )
        placements.append(
            OrderPlacement(
                work_order_id=order.work_order_id,
                day_index=day_index,
                scheduled_date=scheduled_date,
                planned_pickup_date=order.planned_pickup_date,
                meets_deadline=meets_deadline,
                days_late=days_late,
            )
        )
        if not meets_deadline:
            infeasible_order_ids.append(order.work_order_id)

    return MultiDayPlan(
        shift_length=shift_length,
        horizon_working_days=len(working_days),
        days=days,
        placements=placements,
        infeasible_order_ids=infeasible_order_ids,
    )
