""""Good day" metrics — the read-side of the capacity model (NA50 under NA49).

The volume/composition stats (throughput, cycle-time, WIP-aging) answer the *old* question — how much
went through, split how — but not the one the multi-day capacity model now makes the **definition of a
good day** (``docs/SPEC.md`` §9 "Planner numbers"): did the day clear the **profitable m² floor**, did we
ship **on time** (deadlines are hard), and how much capacity did **colour changeovers** burn. This module
is the pure, DB-free arithmetic that turns a day's raw activity (output m², completions vs deadlines,
colour changes, booth-active hours) into those metrics, plus the **idle** diagnostic ("fabryka nie
stała"). The service layer supplies the activity from the stage-transition log.

It also owns the bracketed-pass value object and the honest booth **occupancy** measurement
(``union_active_hours``) the idle/utilisation diagnostic needs: the union of each pass's
``[hanging_start, packing_done]`` interval, so overlapping in-flight orders count once and overnight
idle gaps fall out. This is a plain wall-clock measurement — no seed, no learned line rate (the
premature effective-rate estimate was removed, owner-decided; it drove no decision, only a stats badge).

Like ``capacity.py`` it is deliberately free of any DB/ORM dependency so the arithmetic is fully
unit-testable.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from app.manager.capacity import changeover_loss_m2


@dataclass(frozen=True)
class AutomaticPassObservation:
    """One automatic order's bracketed pass, as seen in the stage-transition log.

    ``hanging_started_at`` / ``packing_done_at`` must be consistent (both naive UTC or both aware) so
    they subtract cleanly; the service normalises them. ``colour_key`` is the colour identity used to
    decide whether a consecutive pair is a changeover (``None`` = no colour).
    """

    work_order_id: int
    colour_key: str | None
    total_area_m2: float | None
    hanging_started_at: datetime
    packing_done_at: datetime


def _union_seconds(intervals: Sequence[tuple[datetime, datetime]]) -> float:
    """Total wall-clock seconds covered by a set of intervals, counting overlaps once."""
    ordered = sorted(intervals, key=lambda interval: interval[0])
    total = 0.0
    current_start: datetime | None = None
    current_end: datetime | None = None
    for start, end in ordered:
        if current_start is None:
            current_start, current_end = start, end
            continue
        if start > current_end:  # type: ignore[operator]
            total += (current_end - current_start).total_seconds()  # type: ignore[operator]
            current_start, current_end = start, end
        elif end > current_end:  # type: ignore[operator]
            current_end = end
    if current_start is not None:
        total += (current_end - current_start).total_seconds()  # type: ignore[operator]
    return total


def union_active_hours(observations: Sequence[AutomaticPassObservation]) -> float:
    """Wall-clock hours the line was occupied across the bracketed passes (overlaps counted once).

    Drives the day's utilisation / idle diagnostic. Only well-formed brackets
    (``packing_done_at > hanging_started_at``) count; overnight gaps between passes fall out of the union.
    """
    valid = [
        observation
        for observation in observations
        if observation.packing_done_at > observation.hanging_started_at
    ]
    active_seconds = _union_seconds(
        [(observation.hanging_started_at, observation.packing_done_at) for observation in valid]
    )
    return round(active_seconds / 3600.0, 2)


@dataclass(frozen=True)
class DayActivity:
    """One day's raw activity for a line, assembled from the stage-transition log."""

    day: date
    output_m2: float
    orders_completed: int
    orders_on_time: int
    changeover_count: int
    # Wall-clock hours the booth was occupied that day (union of the day's passes, overlaps once).
    active_hours: float


@dataclass(frozen=True)
class GoodDayMetrics:
    day: date
    output_m2: float
    floor_m2: float
    # output_m2 ≥ floor_m2 — the day cleared the profitable minimum.
    met_floor: bool
    floor_shortfall_m2: float
    orders_completed: int
    orders_on_time: int
    # Percent of the day's completions shipped on/before their hard pickup date (None when none completed).
    on_time_pct: float | None
    changeover_count: int
    # m² of booth capacity burned by the day's colour changes (the same arithmetic the planner uses).
    changeover_loss_m2: float
    shift_hours: float
    active_hours: float
    idle_hours: float
    # active_hours / shift_hours as a percent (None when the shift length is unknown / zero).
    utilisation_pct: float | None


@dataclass(frozen=True)
class GoodDayTotals:
    """Period roll-up across the day metrics."""

    days_count: int
    days_met_floor: int
    total_output_m2: float
    orders_completed: int
    orders_on_time: int
    on_time_pct: float | None
    total_changeover_count: int
    total_changeover_loss_m2: float
    avg_utilisation_pct: float | None


def summarize_day(
    activity: DayActivity,
    *,
    floor_m2: float,
    shift_hours: float,
    changeover_minutes_total: float,
    ceiling_rate_m2_per_h: float,
) -> GoodDayMetrics:
    """Turn one day's raw activity into the good-day metrics (floor, on-time, changeover, idle).

    ``changeover_minutes_total`` is the size-band cost of the day's colour changes (the planner's N49-6
    number); it is what the m² loss is valued from.
    """
    output = max(activity.output_m2, 0.0)
    met_floor = output >= floor_m2
    shortfall = max(floor_m2 - output, 0.0)

    on_time_pct = (
        round(100.0 * activity.orders_on_time / activity.orders_completed, 1)
        if activity.orders_completed > 0
        else None
    )

    changeover_count = max(activity.changeover_count, 0)
    loss_m2 = changeover_loss_m2(changeover_minutes_total, ceiling_rate_m2_per_h)

    active = max(activity.active_hours, 0.0)
    idle = max(shift_hours - active, 0.0)
    utilisation_pct = round(100.0 * active / shift_hours, 1) if shift_hours > 0 else None

    return GoodDayMetrics(
        day=activity.day,
        output_m2=round(output, 2),
        floor_m2=round(floor_m2, 2),
        met_floor=met_floor,
        floor_shortfall_m2=round(shortfall, 2),
        orders_completed=activity.orders_completed,
        orders_on_time=activity.orders_on_time,
        on_time_pct=on_time_pct,
        changeover_count=changeover_count,
        changeover_loss_m2=round(loss_m2, 2),
        shift_hours=round(shift_hours, 2),
        active_hours=round(active, 2),
        idle_hours=round(idle, 2),
        utilisation_pct=utilisation_pct,
    )


def summarize_period(metrics: Sequence[GoodDayMetrics]) -> GoodDayTotals:
    """Roll the per-day metrics into period totals (overall on-time %, total loss, avg utilisation)."""
    completed = sum(metric.orders_completed for metric in metrics)
    on_time = sum(metric.orders_on_time for metric in metrics)
    utilisations = [metric.utilisation_pct for metric in metrics if metric.utilisation_pct is not None]
    return GoodDayTotals(
        days_count=len(metrics),
        days_met_floor=sum(1 for metric in metrics if metric.met_floor),
        total_output_m2=round(sum(metric.output_m2 for metric in metrics), 2),
        orders_completed=completed,
        orders_on_time=on_time,
        on_time_pct=round(100.0 * on_time / completed, 1) if completed > 0 else None,
        total_changeover_count=sum(metric.changeover_count for metric in metrics),
        total_changeover_loss_m2=round(sum(metric.changeover_loss_m2 for metric in metrics), 2),
        avg_utilisation_pct=round(sum(utilisations) / len(utilisations), 1) if utilisations else None,
    )
