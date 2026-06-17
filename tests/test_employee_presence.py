from sqlalchemy import select

from app.audit.models import AuditEvent
from app.audit.repository import AuditRepository
from app.employees.models import Employee
from app.employees.repository import EmployeeRepository
from app.employees.service import EmployeeService
from app.shared.enums import StationId


def _service(db_session) -> EmployeeService:
    return EmployeeService(EmployeeRepository(db_session))


def _seed_employees(db_session, *names: str) -> list[Employee]:
    employees = [Employee(full_name=name) for name in names]
    db_session.add_all(employees)
    db_session.commit()
    return db_session.scalars(select(Employee).order_by(Employee.id)).all()


def test_check_in_is_idempotent_and_roster_reflects_presence(db_session) -> None:
    jan, anna = _seed_employees(db_session, "Jan Kowalski", "Anna Nowak")
    service = _service(db_session)

    service.check_in(StationId.PACKING, jan.id)
    service.check_in(StationId.PACKING, jan.id)  # idempotent — no duplicate presence
    assert [p.employee_id for p in service.get_station_roster(StationId.PACKING).present] == [jan.id]

    service.check_in(StationId.PACKING, anna.id)
    assert {p.employee_id for p in service.get_station_roster(StationId.PACKING).present} == {jan.id, anna.id}

    service.check_out(StationId.PACKING, jan.id)
    roster = service.get_station_roster(StationId.PACKING)
    assert [p.employee_id for p in roster.present] == [anna.id]
    # check-out is idempotent
    service.check_out(StationId.PACKING, jan.id)
    assert [p.employee_id for p in service.get_station_roster(StationId.PACKING).present] == [anna.id]


def test_presence_is_per_station(db_session) -> None:
    (jan,) = _seed_employees(db_session, "Jan Kowalski")
    service = _service(db_session)
    service.check_in(StationId.PACKING, jan.id)
    assert service.get_station_roster(StationId.PACKING).present
    assert not service.get_station_roster(StationId.HANGING).present


def test_audit_event_attributes_currently_present_employees(db_session) -> None:
    jan, anna = _seed_employees(db_session, "Jan Kowalski", "Anna Nowak")
    service = _service(db_session)
    service.check_in(StationId.PACKING, jan.id)
    service.check_in(StationId.PACKING, anna.id)

    audit = AuditRepository(db_session)
    event = audit.add(AuditEvent(event_type="process.stage.finished", station_id=StationId.PACKING, summary="x"))
    db_session.refresh(event)
    assert sorted(actor.employee_name for actor in event.actors) == ["Anna Nowak", "Jan Kowalski"]


def test_audit_event_has_no_actors_without_presence_or_for_system(db_session) -> None:
    audit = AuditRepository(db_session)
    no_one = audit.add(AuditEvent(event_type="process.stage.finished", station_id=StationId.HANGING, summary="x"))
    assert no_one.actors == []

    # internal/seed (SYSTEM) actions carry no station roster
    system = audit.add(AuditEvent(event_type="seed", station_id=StationId.SYSTEM, summary="y"))
    assert system.actors == []
