from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.audit.context import StationContext, get_station_context
from app.database.session import get_db_session
from app.employees.repository import EmployeeRepository
from app.employees.schemas import (
    EmployeeCreateRequest,
    EmployeeRead,
    EmployeeUpdateRequest,
    OperatorStats,
    PresenceHistoryRead,
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
    station_context: Annotated[StationContext, Depends(get_station_context)],
    include_inactive: Annotated[bool, Query()] = False,
) -> list[EmployeeRead]:
    return service.list_employees(include_inactive=include_inactive, station_context=station_context)


@router.post("/employees", response_model=EmployeeRead, status_code=201)
def create_employee(
    payload: EmployeeCreateRequest,
    service: Annotated[EmployeeService, Depends(get_employee_service)],
    station_context: Annotated[StationContext, Depends(get_station_context)],
) -> EmployeeRead:
    return service.create_employee(payload, station_context=station_context)


@router.patch("/employees/{employee_id}", response_model=EmployeeRead)
def update_employee(
    employee_id: int,
    payload: EmployeeUpdateRequest,
    service: Annotated[EmployeeService, Depends(get_employee_service)],
    station_context: Annotated[StationContext, Depends(get_station_context)],
) -> EmployeeRead:
    return service.update_employee(employee_id, payload, station_context=station_context)


@router.get("/employees/stats", response_model=OperatorStats)
def get_operator_stats(
    service: Annotated[EmployeeService, Depends(get_employee_service)],
    station_context: Annotated[StationContext, Depends(get_station_context)],
    date_from: Annotated[date, Query()],
    date_to: Annotated[date, Query()],
) -> OperatorStats:
    return service.get_operator_stats(date_from, date_to, station_context=station_context)


@router.get("/employees/presence/history", response_model=PresenceHistoryRead)
def get_presence_history(
    service: Annotated[EmployeeService, Depends(get_employee_service)],
    station_context: Annotated[StationContext, Depends(get_station_context)],
    date_from: Annotated[date, Query()],
    date_to: Annotated[date, Query()],
) -> PresenceHistoryRead:
    return service.get_presence_history(date_from, date_to, station_context=station_context)


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


@router.post("/stations/{station_id}/presence/check-out-all", response_model=StationPresenceRosterRead)
def check_out_all_employees(
    station_id: StationId,
    service: Annotated[EmployeeService, Depends(get_employee_service)],
) -> StationPresenceRosterRead:
    return service.check_out_all(station_id)
