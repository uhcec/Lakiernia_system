from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db_session
from app.employees.repository import EmployeeRepository
from app.employees.schemas import (
    EmployeeRead,
    PresenceMutationRequest,
    StationPresenceRosterRead,
)
from app.employees.service import EmployeeService
from app.shared.enums import StationId

router = APIRouter(tags=["employees"])


def get_employee_service(session: Annotated[Session, Depends(get_db_session)]) -> EmployeeService:
    return EmployeeService(EmployeeRepository(session))


@router.get("/employees", response_model=list[EmployeeRead])
def list_employees(
    service: Annotated[EmployeeService, Depends(get_employee_service)],
) -> list[EmployeeRead]:
    return service.list_active_employees()


@router.get("/stations/{station_id}/presence", response_model=StationPresenceRosterRead)
def get_station_presence(
    station_id: StationId,
    service: Annotated[EmployeeService, Depends(get_employee_service)],
) -> StationPresenceRosterRead:
    return service.get_station_roster(station_id)


@router.post("/stations/{station_id}/presence/check-in", response_model=StationPresenceRosterRead)
def check_in_employee(
    station_id: StationId,
    payload: PresenceMutationRequest,
    service: Annotated[EmployeeService, Depends(get_employee_service)],
) -> StationPresenceRosterRead:
    return service.check_in(station_id, payload.employee_id)


@router.post("/stations/{station_id}/presence/check-out", response_model=StationPresenceRosterRead)
def check_out_employee(
    station_id: StationId,
    payload: PresenceMutationRequest,
    service: Annotated[EmployeeService, Depends(get_employee_service)],
) -> StationPresenceRosterRead:
    return service.check_out(station_id, payload.employee_id)
