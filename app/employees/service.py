from datetime import UTC, datetime

from app.employees.models import StationPresence
from app.employees.repository import EmployeeRepository
from app.employees.schemas import (
    EmployeeRead,
    StationPresenceRead,
    StationPresenceRosterRead,
)
from app.shared.enums import StationId
from app.shared.exceptions import ResourceNotFoundError


class EmployeeService:
    def __init__(self, repository: EmployeeRepository) -> None:
        self.repository = repository

    def list_active_employees(self) -> list[EmployeeRead]:
        return [self._to_employee_read(employee) for employee in self.repository.list_active_employees()]

    def get_station_roster(self, station_id: StationId) -> StationPresenceRosterRead:
        present = [
            StationPresenceRead(
                employee_id=presence.employee_id,
                full_name=presence.employee.full_name,
                checked_in_at=presence.checked_in_at,
            )
            for presence in self.repository.list_present(station_id)
        ]
        return StationPresenceRosterRead(
            station_id=station_id,
            present=present,
            employees=self.list_active_employees(),
        )

    def check_in(self, station_id: StationId, employee_id: int) -> StationPresenceRosterRead:
        employee = self.repository.get_employee(employee_id)
        if employee is None or not employee.is_active:
            raise ResourceNotFoundError(f"Active employee {employee_id} not found.")
        # Idempotent: a second check-in while already present is a no-op.
        if not self.repository.list_open_presence(station_id, employee_id):
            self.repository.add(StationPresence(station_id=station_id, employee_id=employee_id))
            self.repository.commit()
        return self.get_station_roster(station_id)

    def check_out(self, station_id: StationId, employee_id: int) -> StationPresenceRosterRead:
        open_rows = self.repository.list_open_presence(station_id, employee_id)
        if open_rows:
            now = datetime.now(UTC)
            for presence in open_rows:
                presence.checked_out_at = now
            self.repository.commit()
        return self.get_station_roster(station_id)

    @staticmethod
    def _to_employee_read(employee) -> EmployeeRead:
        return EmployeeRead(id=employee.id, full_name=employee.full_name, is_active=employee.is_active)
