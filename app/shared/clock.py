"""Single source of "now" for the application, with a development-only virtual clock.

In normal operation ``now()`` is exactly ``datetime.now(UTC)`` — there is no behavioural
change. The virtual clock exists so the workflow **simulation** (``scripts/sim/``) can make
three simulated factory-days produce realistic timestamps *and* drive the planner's
shift/day/capacity logic on simulated time. It is inert in production: the override can only be
engaged through a development-guarded path (``set_virtual_now`` raises outside development, and the
``/dev/clock`` router that calls it is only mounted in local/development environments), and is never
set otherwise.

Every place in ``app/`` that previously called ``datetime.now(UTC)`` (model column defaults and
service code alike) now routes through here, so a single advance moves *all* recorded timestamps
together and audit, stats, and stage-transition events never disagree about what time it is.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.config import get_settings

_LOCAL_APP_ENVS = {"development", "test", "testing", "local"}

# The frozen simulated instant, or ``None`` for real wall-clock time. Process-global on purpose:
# the simulation drives a single backend worker (NA8), so one module-level value is the clock.
_virtual_now: datetime | None = None


def _development() -> bool:
    return get_settings().app_env.lower() in _LOCAL_APP_ENVS


def now() -> datetime:
    """Timezone-aware current UTC instant — or the dev virtual instant when one is set."""
    if _virtual_now is not None:
        return _virtual_now
    return datetime.now(UTC)


def now_naive_local() -> datetime:
    """Naive wall-clock "now" for hour-of-day logic (the planner's remaining-shift-hours).

    Mirrors the historical bare ``datetime.now()``: naive local time in production. Under the
    virtual clock the simulated instant *is* the factory wall clock, so its tz info is stripped and
    its wall-clock hour is used directly (the simulation sets it to the intended shift hour).
    """
    if _virtual_now is not None:
        return _virtual_now.replace(tzinfo=None)
    return datetime.now()


def set_virtual_now(value: datetime | None) -> None:
    """Freeze the clock at ``value`` (tz-aware UTC), or clear it with ``None``. Development only."""
    global _virtual_now
    if value is not None:
        if not _development():
            raise RuntimeError("the virtual clock can only be set in a local/development environment")
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        else:
            value = value.astimezone(UTC)
    _virtual_now = value


def virtual_now() -> datetime | None:
    """The current virtual instant if the clock is frozen, else ``None``."""
    return _virtual_now
