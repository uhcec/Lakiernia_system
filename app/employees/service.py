from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select

from app.audit.context import StationContext, ensure_station_allowed
from app.audit.models import AuditEvent, AuditEventActor
from app.employees.models import Employee, StationPresence
from app.employees.repository import EmployeeRepository
from app.employees.schemas import (
    EmployeeCreateRequest,
    EmployeeRead,
    EmployeeUpdateRequest,
    OperatorStatItem,
    OperatorStats,
    PresenceHistoryRead,
    PresenceSessionRead,
    StationPresenceRead,
    StationPresenceRosterRead,
)
from app.shared.enums import StationId
from app.shared.exceptions import ResourceNotFoundError
from app.work_orders.models import WorkOrder


# Audit events that mark a stage/order completion — used to credit pieces/m² to the operators who
# were present (each present operator gets full credit; an order is counted once per operator).
_COMPLETION_EVENT_TYPES = (
    "process.stage.finished",
    "process.packing.completed",
    "process.decoral_production.completed",
)

# Managing employees and viewing per-operator stats is for the office/manager (admins bypass).
_EMPLOYEE_ADMIN_STATIONS = {StationId.MANAGER, StationId.OFFICE}


def _naive_utc(value: datetime) -> datetime:
    """Coerce to naive UTC so DB datetimes (naive on SQLite) and aware ``now`` subtract cleanly."""
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


class EmployeeService:
    def __init__(self, repository: EmployeeRepository) -> None:
        self.repository = repository

    # --- Roster / check-in-out (open to station operators) ----------------------------------------

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

    def check_out_all(self, station_id: StationId) -> StationPresenceRosterRead:
        """End-of-shift convenience: check everyone out of a station at once."""
        present = self.repository.list_present_anywhere(station_id)
        if present:
            now = datetime.now(UTC)
            for presence in present:
                presence.checked_out_at = now
            self.repository.commit()
        return self.get_station_roster(station_id)

    # --- Employee administration (office/manager/admin) -------------------------------------------

    def list_employees(self, *, include_inactive: bool, station_context: StationContext | None = None) -> list[EmployeeRead]:
        if not include_inactive:
            return self.list_active_employees()
        self._ensure_employee_admin(station_context)
        return [self._to_employee_read(employee) for employee in self.repository.list_all_employees()]

    def create_employee(self, payload: EmployeeCreateRequest, station_context: StationContext | None = None) -> EmployeeRead:
        self._ensure_employee_admin(station_context)
        employee = self.repository.add_employee(Employee(full_name=payload.full_name.strip()))
        self.repository.commit()
        return self._to_employee_read(employee)

    def update_employee(
        self, employee_id: int, payload: EmployeeUpdateRequest, station_context: StationContext | None = None
    ) -> EmployeeRead:
        self._ensure_employee_admin(station_context)
        employee = self.repository.get_employee(employee_id)
        if employee is None:
            raise ResourceNotFoundError(f"Employee {employee_id} not found.")
        if payload.full_name is not None:
            employee.full_name = payload.full_name.strip()
        if payload.is_active is not None:
            employee.is_active = payload.is_active
            # Deactivating a worker also ends any open presence so they leave the floor rosters.
            if not payload.is_active:
                self._check_out_employee_everywhere(employee_id)
        self.repository.commit()
        return self._to_employee_read(employee)

    # --- Presence history + per-operator stats (office/manager/admin) -----------------------------

    def get_presence_history(
        self, date_from: date, date_to: date, station_context: StationContext | None = None
    ) -> PresenceHistoryRead:
        self._ensure_employee_admin(station_context)
        window_start, window_end = self._window(date_from, date_to)
        now = _naive_utc(datetime.now(UTC))

        sessions: list[PresenceSessionRead] = []
        for presence in self.repository.list_presence_sessions():
            started = _naive_utc(presence.checked_in_at)
            ended = _naive_utc(presence.checked_out_at) if presence.checked_out_at is not None else None
            # Keep sessions that overlap the window at all.
            effective_end = ended if ended is not None else now
            if started >= window_end or effective_end <= window_start:
                continue
            hours = max(0.0, (min(effective_end, window_end) - max(started, window_start)).total_seconds() / 3600)
            sessions.append(
                PresenceSessionRead(
                    employee_id=presence.employee_id,
                    full_name=presence.employee.full_name if presence.employee else "—",
                    station_id=presence.station_id,
                    checked_in_at=presence.checked_in_at,
                    checked_out_at=presence.checked_out_at,
                    hours=round(hours, 1),
                    is_open=presence.checked_out_at is None,
                )
            )
        return PresenceHistoryRead(date_from=date_from, date_to=date_to, sessions=sessions)

    def get_operator_stats(
        self, date_from: date, date_to: date, station_context: StationContext | None = None
    ) -> OperatorStats:
        self._ensure_employee_admin(station_context)
        session = self.repository.session
        window_start, window_end = self._window(date_from, date_to)
        now = _naive_utc(datetime.now(UTC))

        # Hours present per employee (clamp each session to the window; open sessions count to now).
        hours_by_employee: dict[int, float] = {}
        for presence in self.repository.list_presence_sessions():
            if presence.employee_id is None:
                continue
            started = _naive_utc(presence.checked_in_at)
            ended = _naive_utc(presence.checked_out_at) if presence.checked_out_at is not None else now
            overlap_start = max(started, window_start)
            overlap_end = min(ended, window_end)
            seconds = (overlap_end - overlap_start).total_seconds()
            if seconds > 0:
                hours_by_employee[presence.employee_id] = hours_by_employee.get(presence.employee_id, 0.0) + seconds / 3600

        # Attributed actions per employee (any audit event they were present for).
        actions_by_employee = {
            row.employee_id: int(row.actions)
            for row in session.execute(
                select(AuditEventActor.employee_id, func.count().label("actions"))
                .join(AuditEvent, AuditEvent.id == AuditEventActor.audit_event_id)
                .where(
                    AuditEventActor.employee_id.is_not(None),
                    func.date(AuditEvent.created_at) >= date_from,
                    func.date(AuditEvent.created_at) <= date_to,
                )
                .group_by(AuditEventActor.employee_id)
            ).all()
        }

        # Distinct (employee, order) pairs from completion events → credit pieces/m² once per order.
        order_pairs = (
            select(
                AuditEventActor.employee_id.label("employee_id"),
                AuditEvent.work_order_id.label("work_order_id"),
            )
            .join(AuditEvent, AuditEvent.id == AuditEventActor.audit_event_id)
            .where(
                AuditEventActor.employee_id.is_not(None),
                AuditEvent.work_order_id.is_not(None),
                AuditEvent.event_type.in_(_COMPLETION_EVENT_TYPES),
                func.date(AuditEvent.created_at) >= date_from,
                func.date(AuditEvent.created_at) <= date_to,
            )
            .distinct()
            .subquery()
        )
        credit_by_employee = {
            row.employee_id: (int(row.orders), int(row.pieces or 0), float(row.m2 or 0.0))
            for row in session.execute(
                select(
                    order_pairs.c.employee_id,
                    func.count().label("orders"),
                    func.coalesce(func.sum(WorkOrder.total_quantity), 0).label("pieces"),
                    func.coalesce(func.sum(WorkOrder.total_area_m2), 0.0).label("m2"),
                )
                .join(WorkOrder, WorkOrder.id == order_pairs.c.work_order_id)
                .group_by(order_pairs.c.employee_id)
            ).all()
        }

        operators: list[OperatorStatItem] = []
        for employee in self.repository.list_all_employees():
            orders, pieces, m2 = credit_by_employee.get(employee.id, (0, 0, 0.0))
            operators.append(
                OperatorStatItem(
                    employee_id=employee.id,
                    full_name=employee.full_name,
                    is_active=employee.is_active,
                    hours_present=round(hours_by_employee.get(employee.id, 0.0), 1),
                    orders_count=orders,
                    actions=actions_by_employee.get(employee.id, 0),
                    pieces_credited=pieces,
                    m2_credited=round(m2, 1),
                )
            )

        operators.sort(key=lambda item: (item.pieces_credited, item.m2_credited, item.hours_present), reverse=True)
        return OperatorStats(date_from=date_from, date_to=date_to, operators=operators)

    # --- helpers ----------------------------------------------------------------------------------

    def _check_out_employee_everywhere(self, employee_id: int) -> None:
        now = datetime.now(UTC)
        open_sessions = self.repository.session.scalars(
            select(StationPresence).where(
                StationPresence.employee_id == employee_id,
                StationPresence.checked_out_at.is_(None),
            )
        ).all()
        for presence in open_sessions:
            presence.checked_out_at = now

    @staticmethod
    def _ensure_employee_admin(station_context: StationContext | None) -> None:
        ensure_station_allowed(
            station_context,
            allowed_station_ids=_EMPLOYEE_ADMIN_STATIONS,
            action="employee administration",
        )

    @staticmethod
    def _window(date_from: date, date_to: date) -> tuple[datetime, datetime]:
        # Naive UTC half-open window [date_from 00:00, date_to+1 00:00).
        return (
            datetime.combine(date_from, time.min),
            datetime.combine(date_to, time.min) + timedelta(days=1),
        )

    @staticmethod
    def _to_employee_read(employee) -> EmployeeRead:
        return EmployeeRead(id=employee.id, full_name=employee.full_name, is_active=employee.is_active)
