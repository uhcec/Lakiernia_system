import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.audit.context import parse_station_id
from app.audit.models import AuditEvent
from app.shared.enums import StationId
from app.shared.exceptions import InvalidStationIdentityError


def test_station_header_parser_accepts_known_values_and_normalizes_separators() -> None:
    assert parse_station_id("PACKING") == StationId.PACKING
    assert parse_station_id("manual-production") == StationId.MANUAL_PRODUCTION
    assert parse_station_id("  surface_preparation  ") == StationId.SURFACE_PREPARATION


def test_station_header_parser_defaults_missing_value_to_unknown() -> None:
    assert parse_station_id(None) == StationId.UNKNOWN
    assert parse_station_id("   ") == StationId.UNKNOWN


def test_station_header_parser_rejects_invalid_value() -> None:
    with pytest.raises(InvalidStationIdentityError) as exc_info:
        parse_station_id("warehouse")

    assert str(exc_info.value) == "Invalid station identity: warehouse."


def test_audit_event_persists_station_identity(db_session: Session) -> None:
    event = AuditEvent(
        event_type="work_order.created",
        station_id=StationId.OFFICE,
        target_type="work_order",
        target_id=123,
        summary="Created work order WO-2026-1001.",
        details_json='{"order_number":"WO-2026-1001"}',
    )

    db_session.add(event)
    db_session.commit()

    persisted = db_session.get(AuditEvent, event.id)

    assert persisted is not None
    assert persisted.station_id == StationId.OFFICE
    assert persisted.event_type == "work_order.created"
    assert persisted.target_type == "work_order"
    assert persisted.created_at is not None


def test_wrong_station_cannot_create_work_order(test_client: TestClient) -> None:
    response = test_client.post(
        "/work-orders",
        json=build_work_order_payload(),
        headers={"X-Station-Id": "PACKING"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Station PACKING is not allowed to perform office work-order actions. Allowed stations: OFFICE."
    )


def test_wrong_station_cannot_assign_manager_plan(test_client: TestClient) -> None:
    created = create_work_order_with_office_station(test_client)

    response = test_client.post(
        f"/manager/work-orders/{created['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 1},
        headers={"X-Station-Id": "OFFICE"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Station OFFICE is not allowed to perform manager planning actions. Allowed stations: MANAGER."
    )


def test_wrong_station_cannot_start_process_stage(test_client: TestClient) -> None:
    created = create_work_order_with_office_station(test_client)
    assign_manual_plan_with_manager_station(test_client, created["id"])

    blocked_response = test_client.post(
        f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/start",
        headers={"X-Station-Id": "PACKING"},
    )
    allowed_response = test_client.post(
        f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/start",
        headers={"X-Station-Id": "SURFACE_PREPARATION"},
    )

    assert blocked_response.status_code == 403
    assert blocked_response.json()["detail"] == (
        "Station PACKING is not allowed to perform SURFACE_PREPARATION stage actions. Allowed stations: SURFACE_PREPARATION."
    )
    assert allowed_response.status_code == 200


def test_wrong_station_cannot_complete_packing(test_client: TestClient) -> None:
    created = create_work_order_with_office_station(test_client)
    assign_manual_plan_with_manager_station(test_client, created["id"])

    test_client.post(
        f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/start",
        headers={"X-Station-Id": "SURFACE_PREPARATION"},
    )
    test_client.post(
        f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/finish",
        json={"counted_quantity": 10},
        headers={"X-Station-Id": "SURFACE_PREPARATION"},
    )
    test_client.post(
        f"/process/work-orders/{created['id']}/stages/PRODUCTION/start",
        headers={"X-Station-Id": "MANUAL_PRODUCTION"},
    )
    test_client.post(
        f"/process/work-orders/{created['id']}/stages/PRODUCTION/finish",
        headers={"X-Station-Id": "MANUAL_PRODUCTION"},
    )
    test_client.post(
        f"/process/work-orders/{created['id']}/stages/PACKING/start",
        headers={"X-Station-Id": "PACKING"},
    )

    response = test_client.post(
        f"/process/work-orders/{created['id']}/packing/complete",
        json={"counted_quantity": 10, "ok_quantity": 10, "correction_quantity": 0},
        headers={"X-Station-Id": "HANGING"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Station HANGING is not allowed to perform PACKING actions. Allowed stations: PACKING."


def create_work_order_with_office_station(test_client: TestClient) -> dict:
    response = test_client.post(
        "/work-orders",
        json=build_work_order_payload(),
        headers={"X-Station-Id": "OFFICE"},
    )
    assert response.status_code == 201
    return response.json()


def assign_manual_plan_with_manager_station(test_client: TestClient, work_order_id: int) -> dict:
    response = test_client.post(
        f"/manager/work-orders/{work_order_id}/plan",
        json={"production_type": "MANUAL", "queue_position": 1},
        headers={"X-Station-Id": "MANAGER"},
    )
    assert response.status_code == 200
    return response.json()


def build_work_order_payload() -> dict:
    return {
        "title": "Station permission test",
        "coating_type": "RAL",
        "total_quantity": 10,
        "customer_name": "ACME",
        "ral_code": "RAL 7016",
        "paint_producer": "AkzoNobel",
        "received_date": "2026-05-30",
        "profiles_to_count": True,
        "accessories_to_count": True,
    }