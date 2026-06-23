"""Employee administration, per-operator statistics, presence history, and role gating (NA28 ph.2)."""

from datetime import date

import pytest
from sqlalchemy import select

from app.audit.context import StationContext
from app.audit.models import AuditEvent
from app.audit.repository import AuditRepository
from app.employees.models import Employee
from app.employees.repository import EmployeeRepository
from app.employees.schemas import EmployeeCreateRequest, EmployeeUpdateRequest
from app.employees.service import EmployeeService
from app.process.enums import CoatingType
from app.shared.enums import StationId
from app.shared.exceptions import StationActionForbiddenError
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import WorkOrderCreate
from app.work_orders.service import WorkOrderService

MANAGER = StationContext(station_id=StationId.MANAGER)
OFFICE = StationContext(station_id=StationId.OFFICE)
PACKING = StationContext(station_id=StationId.PACKING)
WIDE = (date(2000, 1, 1), date(2100, 1, 1))


def _service(db_session) -> EmployeeService:
    return EmployeeService(EmployeeRepository(db_session))


def _create_order(db_session, *, quantity: int, area: float):
    return WorkOrderService(WorkOrderRepository(db_session)).create_work_order(
        WorkOrderCreate(
            title="Stat order",
            coating_type=CoatingType.RAL,
            total_quantity=quantity,
            customer_name="ACME",
            ral_code="RAL 7016",
            paint_code="P-7016",
            paint_producer="AkzoNobel",
            received_date=date(2026, 5, 27),
            planned_pickup_date=date(2026, 6, 3),
            total_area_m2=area,
            profiles_quantity=quantity,
            accessories_quantity=0,
        )
    )


def test_create_and_update_employee_is_gated_to_office_manager(db_session) -> None:
    service = _service(db_session)
    with pytest.raises(StationActionForbiddenError):
        service.create_employee(EmployeeCreateRequest(full_name="Nieuprawniony"), station_context=PACKING)

    created = service.create_employee(EmployeeCreateRequest(full_name="Jan Kowalski"), station_context=MANAGER)
    assert created.is_active is True

    renamed = service.update_employee(created.id, EmployeeUpdateRequest(full_name="Jan Nowak"), station_context=OFFICE)
    assert renamed.full_name == "Jan Nowak"

    with pytest.raises(StationActionForbiddenError):
        service.update_employee(created.id, EmployeeUpdateRequest(full_name="X"), station_context=PACKING)


def test_include_inactive_list_is_gated_but_active_list_is_open(db_session) -> None:
    service = _service(db_session)
    active = service.create_employee(EmployeeCreateRequest(full_name="Anna"), station_context=MANAGER)
    inactive = service.create_employee(EmployeeCreateRequest(full_name="Stary"), station_context=MANAGER)
    service.update_employee(inactive.id, EmployeeUpdateRequest(is_active=False), station_context=MANAGER)

    # Active-only list is open to operators (used by the station widget).
    open_list = service.list_employees(include_inactive=False)
    assert {e.id for e in open_list} == {active.id}

    with pytest.raises(StationActionForbiddenError):
        service.list_employees(include_inactive=True, station_context=PACKING)

    full = service.list_employees(include_inactive=True, station_context=MANAGER)
    assert {e.id for e in full} == {active.id, inactive.id}


def test_deactivating_employee_checks_them_out(db_session) -> None:
    service = _service(db_session)
    employee = service.create_employee(EmployeeCreateRequest(full_name="Obecny"), station_context=MANAGER)
    service.check_in(StationId.PACKING, employee.id)
    assert service.get_station_roster(StationId.PACKING).present

    service.update_employee(employee.id, EmployeeUpdateRequest(is_active=False), station_context=MANAGER)
    assert service.get_station_roster(StationId.PACKING).present == []


def test_check_out_all_clears_the_station(db_session) -> None:
    service = _service(db_session)
    a = service.create_employee(EmployeeCreateRequest(full_name="A"), station_context=MANAGER)
    b = service.create_employee(EmployeeCreateRequest(full_name="B"), station_context=MANAGER)
    service.check_in(StationId.PACKING, a.id)
    service.check_in(StationId.PACKING, b.id)

    roster = service.check_out_all(StationId.PACKING)
    assert roster.present == []


def test_operator_stats_credit_each_present_operator_in_full(db_session) -> None:
    service = _service(db_session)
    jan = service.create_employee(EmployeeCreateRequest(full_name="Jan"), station_context=MANAGER)
    anna = service.create_employee(EmployeeCreateRequest(full_name="Anna"), station_context=MANAGER)
    service.check_in(StationId.PACKING, jan.id)
    service.check_in(StationId.PACKING, anna.id)

    order = _create_order(db_session, quantity=10, area=24.0)
    audit = AuditRepository(db_session)
    audit.add(
        AuditEvent(
            event_type="process.packing.completed",
            station_id=StationId.PACKING,
            work_order_id=order.id,
            summary="packed",
        )
    )

    with pytest.raises(StationActionForbiddenError):
        service.get_operator_stats(*WIDE, station_context=PACKING)

    stats = service.get_operator_stats(*WIDE, station_context=MANAGER)
    by_name = {op.full_name: op for op in stats.operators}
    # Both present operators get full credit for the same order.
    for name in ("Jan", "Anna"):
        assert by_name[name].orders_count == 1
        assert by_name[name].pieces_credited == 10
        assert by_name[name].m2_credited == 24.0
        assert by_name[name].actions == 1


def test_operator_stats_count_an_order_once_per_operator(db_session) -> None:
    service = _service(db_session)
    jan = service.create_employee(EmployeeCreateRequest(full_name="Jan"), station_context=MANAGER)
    service.check_in(StationId.PACKING, jan.id)
    order = _create_order(db_session, quantity=10, area=24.0)
    audit = AuditRepository(db_session)
    # Two completion events for the same order with the same operator present.
    for event_type in ("process.stage.finished", "process.packing.completed"):
        audit.add(
            AuditEvent(event_type=event_type, station_id=StationId.PACKING, work_order_id=order.id, summary="x")
        )

    stats = service.get_operator_stats(*WIDE, station_context=MANAGER)
    jan_stat = next(op for op in stats.operators if op.full_name == "Jan")
    assert jan_stat.orders_count == 1  # not double-counted
    assert jan_stat.pieces_credited == 10
    assert jan_stat.actions == 2  # but both actions are counted as activity


def test_presence_history_is_gated_and_lists_sessions(db_session) -> None:
    service = _service(db_session)
    employee = service.create_employee(EmployeeCreateRequest(full_name="Jan"), station_context=MANAGER)
    service.check_in(StationId.PACKING, employee.id)
    service.check_out(StationId.PACKING, employee.id)

    with pytest.raises(StationActionForbiddenError):
        service.get_presence_history(*WIDE, station_context=PACKING)

    history = service.get_presence_history(*WIDE, station_context=MANAGER)
    assert len(history.sessions) == 1
    assert history.sessions[0].full_name == "Jan"
    assert history.sessions[0].is_open is False
    assert history.sessions[0].hours >= 0
