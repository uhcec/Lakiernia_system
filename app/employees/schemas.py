from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import StationId


class EmployeeRead(BaseModel):
    id: int
    full_name: str
    is_active: bool


class EmployeeCreateRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)

    model_config = ConfigDict(extra="forbid")


class EmployeeUpdateRequest(BaseModel):
    # Both optional: rename, change active flag, or both.
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    is_active: bool | None = None

    model_config = ConfigDict(extra="forbid")


class StationPresenceRead(BaseModel):
    employee_id: int
    full_name: str
    checked_in_at: datetime


class StationPresenceRosterRead(BaseModel):
    station_id: StationId
    # Employees currently checked in at this station (the attribution set for actions here).
    present: list[StationPresenceRead]
    # Active employees available to check in.
    employees: list[EmployeeRead]


class PresenceMutationRequest(BaseModel):
    employee_id: int

    model_config = ConfigDict(extra="forbid")


class PresenceSessionRead(BaseModel):
    """One check-in/out session, for the presence-history view."""

    employee_id: int | None
    full_name: str
    station_id: StationId
    checked_in_at: datetime
    checked_out_at: datetime | None
    hours: float
    is_open: bool


class PresenceHistoryRead(BaseModel):
    date_from: date
    date_to: date
    sessions: list[PresenceSessionRead]


class OperatorStatItem(BaseModel):
    employee_id: int
    full_name: str
    is_active: bool
    hours_present: float
    # Orders the operator was present for at least one completed stage (counted once per order).
    orders_count: int
    # Total attributed actions (any audit event the operator was present for) — activity measure.
    actions: int
    # Pieces / m² of the distinct orders credited to this operator (each present operator gets full credit).
    pieces_credited: int
    m2_credited: float


class OperatorStats(BaseModel):
    date_from: date
    date_to: date
    operators: list[OperatorStatItem]
