"""Development-only control of the virtual clock (``app.shared.clock``).

Used by the workflow simulation (``scripts/sim/``) to advance simulated factory time. This router is
mounted **only** in local/development environments (see ``app/api/router.py``); it does not exist in
production, and ``clock.set_virtual_now`` independently refuses to engage outside development.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from app.shared import clock

router = APIRouter(prefix="/dev/clock", tags=["dev"])


class SetClockRequest(BaseModel):
    now: datetime


class ClockState(BaseModel):
    virtual_now: datetime | None
    now: datetime


def _state() -> ClockState:
    return ClockState(virtual_now=clock.virtual_now(), now=clock.now())


@router.get("")
def get_clock() -> ClockState:
    return _state()


@router.put("")
def set_clock(payload: SetClockRequest) -> ClockState:
    """Freeze the simulated clock at the given instant."""
    clock.set_virtual_now(payload.now)
    return _state()


@router.delete("")
def clear_clock() -> ClockState:
    """Return to real wall-clock time."""
    clock.set_virtual_now(None)
    return _state()
