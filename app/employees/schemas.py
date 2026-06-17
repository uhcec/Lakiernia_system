from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.shared.enums import StationId


class EmployeeRead(BaseModel):
    id: int
    full_name: str
    is_active: bool


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
