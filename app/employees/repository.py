from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.employees.models import Employee, StationPresence
from app.shared.enums import StationId


class EmployeeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_active_employees(self) -> Sequence[Employee]:
        return self.session.scalars(
            select(Employee).where(Employee.is_active.is_(True)).order_by(Employee.full_name)
        ).all()

    def list_all_employees(self) -> Sequence[Employee]:
        return self.session.scalars(
            select(Employee).order_by(Employee.is_active.desc(), Employee.full_name)
        ).all()

    def get_employee(self, employee_id: int) -> Employee | None:
        return self.session.get(Employee, employee_id)

    def add_employee(self, employee: Employee) -> Employee:
        self.session.add(employee)
        self.session.flush()
        return employee

    def list_present_anywhere(self, station_id: StationId) -> Sequence[StationPresence]:
        return self.session.scalars(
            select(StationPresence).where(
                StationPresence.station_id == station_id,
                StationPresence.checked_out_at.is_(None),
            )
        ).all()

    def list_presence_sessions(self) -> Sequence[StationPresence]:
        # All check-in/out sessions (period clamping is done in the service, in Python, to avoid
        # SQLite tz/string-compare pitfalls on the stored datetimes).
        return self.session.scalars(
            select(StationPresence)
            .options(joinedload(StationPresence.employee))
            .order_by(StationPresence.checked_in_at.desc())
        ).all()

    def list_present(self, station_id: StationId) -> Sequence[StationPresence]:
        return self.session.scalars(
            select(StationPresence)
            .where(StationPresence.station_id == station_id, StationPresence.checked_out_at.is_(None))
            .order_by(StationPresence.checked_in_at)
        ).all()

    def list_open_presence(self, station_id: StationId, employee_id: int) -> Sequence[StationPresence]:
        return self.session.scalars(
            select(StationPresence).where(
                StationPresence.station_id == station_id,
                StationPresence.employee_id == employee_id,
                StationPresence.checked_out_at.is_(None),
            )
        ).all()

    def add(self, presence: StationPresence) -> StationPresence:
        self.session.add(presence)
        self.session.flush()
        return presence

    def commit(self) -> None:
        self.session.commit()
