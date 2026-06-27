import json
from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.context import StationContext
from app.audit.models import AuditEvent
from app.process.enums import CoatingType
from app.shared.enums import StationId, WorkOrderStatus
from app.shared.exceptions import InvalidWorkOrderDataError
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import WorkOrderCreate, WorkOrderUpdate
from app.work_orders.service import WorkOrderService


def build_incomplete_work_order_payload(**overrides: object) -> WorkOrderCreate:
    payload = {
        "title": "Niekompletne zlecenie",
        "coating_type": CoatingType.RAL,
        "total_quantity": 100,
        "customer_name": "ACME",
        "ral_code": "RAL 7016",
        "paint_code": "P-7016",
        "paint_producer": "AkzoNobel",
        "received_date": date(2026, 5, 25),
        "planned_pickup_date": date(2026, 6, 1),
        "total_area_m2": 24.0,
        "is_incomplete_on_arrival": True,
        "profiles_to_count": True,
        "accessories_to_count": True,
    }
    payload.update(overrides)
    return WorkOrderCreate.model_validate(payload)


def build_work_order_service(db_session: Session) -> tuple[WorkOrderService, WorkOrderRepository]:
    repository = WorkOrderRepository(db_session)
    return WorkOrderService(repository), repository


def test_create_work_order_records_station_audit_event(db_session: Session) -> None:
    service, _ = build_work_order_service(db_session)

    created = service.create_work_order(
        build_incomplete_work_order_payload(title="Audytowane zlecenie", is_incomplete_on_arrival=False),
        station_context=StationContext(station_id=StationId.OFFICE),
    )

    event = db_session.scalar(select(AuditEvent).where(AuditEvent.event_type == "work_order.created"))

    assert event is not None
    assert event.station_id == StationId.OFFICE
    assert event.work_order_id == created.id
    assert event.target_type == "work_order"
    assert event.target_id == created.id
    assert event.summary == f"Created work order {created.order_number}."
    assert json.loads(event.details_json or "{}") == {
        "order_number": created.order_number,
        "external_order_number": None,
        "work_order_kind": "STANDARD",
        "is_ocynk": False,
        "is_incomplete_on_arrival": False,
    }


def test_read_model_is_overdue_is_backend_owned_NA44(db_session: Session) -> None:
    # NA44: "overdue" is a backend-owned read-model boolean (the planned pickup day has passed and the
    # order is not READY), not a client-clock computation. Date-only, strictly before today.
    service, _ = build_work_order_service(db_session)

    overdue = service.create_work_order(
        build_incomplete_work_order_payload(is_incomplete_on_arrival=False, planned_pickup_date=date.today() - timedelta(days=1))
    )
    assert overdue.is_overdue is True

    future = service.create_work_order(
        build_incomplete_work_order_payload(is_incomplete_on_arrival=False, planned_pickup_date=date.today() + timedelta(days=1))
    )
    assert future.is_overdue is False

    due_today = service.create_work_order(
        build_incomplete_work_order_payload(is_incomplete_on_arrival=False, planned_pickup_date=date.today())
    )
    assert due_today.is_overdue is False  # the pickup day itself is not yet past the deadline


def test_update_work_order_records_station_audit_event(db_session: Session) -> None:
    service, _ = build_work_order_service(db_session)
    created = service.create_work_order(build_incomplete_work_order_payload(is_incomplete_on_arrival=False))

    service.update_work_order(
        created.id,
        WorkOrderUpdate(title="Po korekcie", planned_pickup_date=date(2026, 6, 3)),
        station_context=StationContext(station_id=StationId.OFFICE),
    )

    event = db_session.scalar(select(AuditEvent).where(AuditEvent.event_type == "work_order.updated"))

    assert event is not None
    assert event.station_id == StationId.OFFICE
    assert event.work_order_id == created.id
    assert event.target_type == "work_order"
    assert event.target_id == created.id
    assert json.loads(event.details_json or "{}") == {
        "updated_fields": ["planned_pickup_date", "title"],
        "changes": {
            "title": {"before": "Niekompletne zlecenie", "after": "Po korekcie"},
            "planned_pickup_date": {"before": "2026-06-01", "after": "2026-06-03"},
        },
    }


def test_mark_complete_arrival_rejects_invalid_profiles_state(db_session: Session) -> None:
    service, repository = build_work_order_service(db_session)
    created = service.create_work_order(
        build_incomplete_work_order_payload(profiles_quantity=100, profiles_to_count=False),
    )
    work_order = repository.get_by_id(created.id)
    assert work_order is not None
    work_order.profiles_quantity = None
    work_order.profiles_to_count = False
    db_session.commit()

    with pytest.raises(InvalidWorkOrderDataError, match="Profile"):
        service.mark_complete_arrival(created.id)

    db_session.refresh(work_order)
    assert work_order.is_incomplete_on_arrival is True
    assert work_order.profiles_quantity is None
    assert work_order.profiles_to_count is False


def test_mark_complete_arrival_rejects_invalid_accessories_state(db_session: Session) -> None:
    service, repository = build_work_order_service(db_session)
    created = service.create_work_order(
        build_incomplete_work_order_payload(accessories_quantity=100, accessories_to_count=False),
    )
    work_order = repository.get_by_id(created.id)
    assert work_order is not None
    work_order.accessories_quantity = None
    work_order.accessories_to_count = False
    db_session.commit()

    with pytest.raises(InvalidWorkOrderDataError, match="Akcesoria"):
        service.mark_complete_arrival(created.id)

    db_session.refresh(work_order)
    assert work_order.is_incomplete_on_arrival is True
    assert work_order.accessories_quantity is None
    assert work_order.accessories_to_count is False


def test_mark_complete_arrival_rejects_blank_customer_name_when_persisted_state_is_corrupted(db_session: Session) -> None:
    service, repository = build_work_order_service(db_session)
    created = service.create_work_order(build_incomplete_work_order_payload(customer_name="Poprawny klient"))
    work_order = repository.get_by_id(created.id)
    assert work_order is not None
    work_order.customer_name = "   "
    db_session.commit()

    with pytest.raises(InvalidWorkOrderDataError, match="at least 1 character"):
        service.mark_complete_arrival(created.id)

    db_session.refresh(work_order)
    assert work_order.is_incomplete_on_arrival is True
    assert work_order.customer_name == "   "


def test_valid_incomplete_order_can_still_be_marked_complete_arrival(db_session: Session) -> None:
    service, repository = build_work_order_service(db_session)
    created = service.create_work_order(build_incomplete_work_order_payload())

    completed = service.mark_complete_arrival(created.id)
    persisted = repository.get_by_id(created.id)

    assert completed.is_incomplete_on_arrival is False
    assert completed.status.value == WorkOrderStatus.ENTERED
    assert persisted is not None
    assert persisted.is_incomplete_on_arrival is False


def test_mark_complete_arrival_records_station_audit_event(db_session: Session) -> None:
    service, _ = build_work_order_service(db_session)
    created = service.create_work_order(build_incomplete_work_order_payload())

    service.mark_complete_arrival(
        created.id,
        station_context=StationContext(station_id=StationId.OFFICE),
    )

    event = db_session.scalar(select(AuditEvent).where(AuditEvent.event_type == "work_order.arrival_completed"))

    assert event is not None
    assert event.station_id == StationId.OFFICE
    assert event.work_order_id == created.id
    assert event.target_type == "work_order"
    assert event.target_id == created.id
    assert json.loads(event.details_json or "{}") == {
        "is_incomplete_on_arrival": False,
    }


def test_rejected_mark_complete_arrival_leaves_order_state_unchanged(db_session: Session) -> None:
    service, repository = build_work_order_service(db_session)
    created = service.create_work_order(
        build_incomplete_work_order_payload(
            customer_name="Stały klient",
            profiles_quantity=100,
            profiles_to_count=False,
            accessories_quantity=0,
            accessories_to_count=False,
        )
    )
    work_order = repository.get_by_id(created.id)
    assert work_order is not None
    work_order.customer_name = "   "
    work_order.accessories_quantity = None
    db_session.commit()
    unchanged_updated_at = work_order.updated_at

    with pytest.raises(InvalidWorkOrderDataError):
        service.mark_complete_arrival(created.id)

    db_session.refresh(work_order)
    assert work_order.is_incomplete_on_arrival is True
    assert work_order.customer_name == "   "
    assert work_order.profiles_quantity == 100
    assert work_order.profiles_to_count is False
    assert work_order.accessories_quantity is None
    assert work_order.accessories_to_count is False
    assert work_order.updated_at == unchanged_updated_at
