import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.audit.context import StationContext, ensure_station_allowed, parse_station_id
from app.audit.models import AuditEvent
from app.shared.enums import StationId
from app.shared.exceptions import InvalidStationIdentityError, StationActionForbiddenError


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


def test_ensure_station_allowed_admin_bypasses_any_action() -> None:
    admin = StationContext(station_id=StationId.PACKING, is_admin=True)
    # Admin may perform an action even though their station is not in the allowed set (NA1).
    ensure_station_allowed(admin, allowed_station_ids={StationId.OFFICE}, action="office actions")


def test_ensure_station_allowed_internal_and_system_callers_are_trusted() -> None:
    ensure_station_allowed(None, allowed_station_ids={StationId.OFFICE}, action="seed/internal")
    system = StationContext(station_id=StationId.SYSTEM, is_admin=False)
    ensure_station_allowed(system, allowed_station_ids={StationId.OFFICE}, action="seed/internal")


def test_ensure_station_allowed_unknown_no_longer_bypasses() -> None:
    # The missing-header (UNKNOWN) early-allow is gone; an unknown station is denied (NA1).
    unknown = StationContext(station_id=StationId.UNKNOWN, is_admin=False)
    with pytest.raises(StationActionForbiddenError):
        ensure_station_allowed(unknown, allowed_station_ids={StationId.OFFICE}, action="office actions")


def test_ensure_station_allowed_wrong_station_is_denied() -> None:
    packing = StationContext(station_id=StationId.PACKING, is_admin=False)
    with pytest.raises(StationActionForbiddenError):
        ensure_station_allowed(packing, allowed_station_ids={StationId.OFFICE}, action="office actions")


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


def test_stage_permissions_cover_hanging_manual_production_and_decoral(test_client: TestClient) -> None:
    automatic = create_work_order_with_office_station(test_client)
    assign_plan_with_manager_station(test_client, automatic["id"], production_type="AUTOMATIC", queue_position=1)
    advance_surface_preparation_with_station(test_client, automatic["id"])

    hanging_start_blocked = post_stage_action(test_client, automatic["id"], "HANGING", "start", station_id="PACKING")
    hanging_start_allowed = post_stage_action(test_client, automatic["id"], "HANGING", "start", station_id="HANGING")
    hanging_finish_blocked = post_stage_action(test_client, automatic["id"], "HANGING", "finish", station_id="MANUAL_PRODUCTION")
    hanging_finish_allowed = post_stage_action(test_client, automatic["id"], "HANGING", "finish", station_id="HANGING")

    assert hanging_start_blocked.status_code == 403
    assert hanging_start_blocked.json()["detail"] == (
        "Station PACKING is not allowed to perform HANGING stage actions. Allowed stations: HANGING."
    )
    assert hanging_start_allowed.status_code == 200
    assert hanging_finish_blocked.status_code == 403
    assert hanging_finish_blocked.json()["detail"] == (
        "Station MANUAL_PRODUCTION is not allowed to perform HANGING stage actions. Allowed stations: HANGING."
    )
    assert hanging_finish_allowed.status_code == 200

    manual = create_work_order_with_office_station(test_client)
    assign_plan_with_manager_station(test_client, manual["id"], production_type="MANUAL", queue_position=2)
    advance_surface_preparation_with_station(test_client, manual["id"])

    production_start_blocked = post_stage_action(test_client, manual["id"], "PRODUCTION", "start", station_id="HANGING")
    production_start_allowed = post_stage_action(test_client, manual["id"], "PRODUCTION", "start", station_id="MANUAL_PRODUCTION")
    production_finish_blocked = post_stage_action(test_client, manual["id"], "PRODUCTION", "finish", station_id="PACKING")
    production_finish_allowed = post_stage_action(test_client, manual["id"], "PRODUCTION", "finish", station_id="MANUAL_PRODUCTION")

    assert production_start_blocked.status_code == 403
    assert production_start_blocked.json()["detail"] == (
        "Station HANGING is not allowed to perform PRODUCTION stage actions. Allowed stations: MANUAL_PRODUCTION."
    )
    assert production_start_allowed.status_code == 200
    assert production_finish_blocked.status_code == 403
    assert production_finish_blocked.json()["detail"] == (
        "Station PACKING is not allowed to perform PRODUCTION stage actions. Allowed stations: MANUAL_PRODUCTION."
    )
    assert production_finish_allowed.status_code == 200

    decoral = create_work_order_with_office_station(test_client, coating_type="DECORAL")
    assign_plan_with_manager_station(test_client, decoral["id"], production_type="MANUAL", queue_position=3)
    advance_decoral_to_decoral_production_with_station(test_client, decoral["id"])

    decoral_start_blocked = post_stage_action(test_client, decoral["id"], "DECORAL_PRODUCTION", "start", station_id="PACKING")
    decoral_start_allowed = post_stage_action(test_client, decoral["id"], "DECORAL_PRODUCTION", "start", station_id="DECORAL_PRODUCTION")
    decoral_finish_blocked = post_stage_action(test_client, decoral["id"], "DECORAL_PRODUCTION", "finish", station_id="MANUAL_PRODUCTION")
    decoral_finish_allowed = post_stage_action(test_client, decoral["id"], "DECORAL_PRODUCTION", "finish", station_id="DECORAL_PRODUCTION")

    assert decoral_start_blocked.status_code == 403
    assert decoral_start_blocked.json()["detail"] == (
        "Station PACKING is not allowed to perform DECORAL_PRODUCTION stage actions. Allowed stations: DECORAL_PRODUCTION."
    )
    assert decoral_start_allowed.status_code == 200
    assert decoral_finish_blocked.status_code == 403
    assert decoral_finish_blocked.json()["detail"] == (
        "Station MANUAL_PRODUCTION is not allowed to perform DECORAL_PRODUCTION stage actions. Allowed stations: DECORAL_PRODUCTION."
    )
    assert decoral_finish_allowed.status_code == 200


def test_automatic_production_station_authorization_precedes_manual_action_conflict(test_client: TestClient) -> None:
    created = create_work_order_with_office_station(test_client)
    assign_plan_with_manager_station(test_client, created["id"], production_type="AUTOMATIC", queue_position=1)
    advance_surface_preparation_with_station(test_client, created["id"])
    post_stage_action(test_client, created["id"], "HANGING", "start", station_id="HANGING")
    post_stage_action(test_client, created["id"], "HANGING", "finish", station_id="HANGING")

    wrong_station_response = post_stage_action(test_client, created["id"], "PRODUCTION", "finish", station_id="HANGING")
    automatic_station_response = post_stage_action(
        test_client,
        created["id"],
        "PRODUCTION",
        "finish",
        station_id="AUTOMATIC_PRODUCTION",
    )

    assert wrong_station_response.status_code == 403
    assert wrong_station_response.json()["detail"] == (
        "Station HANGING is not allowed to perform PRODUCTION stage actions. Allowed stations: AUTOMATIC_PRODUCTION."
    )
    assert automatic_station_response.status_code == 409
    assert automatic_station_response.json()["detail"] == (
        "Automatic production does not use manual start/finish. Finish HANGING to enter automatic production and complete from PACKING."
    )


def create_work_order_with_office_station(test_client: TestClient, *, coating_type: str = "RAL") -> dict:
    response = test_client.post(
        "/work-orders",
        json=build_work_order_payload(coating_type=coating_type),
        headers={"X-Station-Id": "OFFICE"},
    )
    assert response.status_code == 201
    return response.json()


def assign_manual_plan_with_manager_station(test_client: TestClient, work_order_id: int) -> dict:
    return assign_plan_with_manager_station(test_client, work_order_id, production_type="MANUAL", queue_position=1)


def assign_plan_with_manager_station(
    test_client: TestClient,
    work_order_id: int,
    *,
    production_type: str,
    queue_position: int,
) -> dict:
    response = test_client.post(
        f"/manager/work-orders/{work_order_id}/plan",
        json={"production_type": production_type, "queue_position": queue_position},
        headers={"X-Station-Id": "MANAGER"},
    )
    assert response.status_code == 200
    return response.json()


def post_stage_action(
    test_client: TestClient,
    work_order_id: int,
    stage: str,
    action: str,
    *,
    station_id: str,
    payload: dict | None = None,
):
    return test_client.post(
        f"/process/work-orders/{work_order_id}/stages/{stage}/{action}",
        json=payload,
        headers={"X-Station-Id": station_id},
    )


def advance_surface_preparation_with_station(test_client: TestClient, work_order_id: int) -> None:
    start_response = post_stage_action(test_client, work_order_id, "SURFACE_PREPARATION", "start", station_id="SURFACE_PREPARATION")
    finish_response = post_stage_action(
        test_client,
        work_order_id,
        "SURFACE_PREPARATION",
        "finish",
        station_id="SURFACE_PREPARATION",
        payload={"counted_quantity": 10},
    )
    assert start_response.status_code == 200
    assert finish_response.status_code == 200


def advance_decoral_to_decoral_production_with_station(test_client: TestClient, work_order_id: int) -> None:
    advance_surface_preparation_with_station(test_client, work_order_id)
    assert post_stage_action(test_client, work_order_id, "PRODUCTION", "start", station_id="MANUAL_PRODUCTION").status_code == 200
    assert post_stage_action(test_client, work_order_id, "PRODUCTION", "finish", station_id="MANUAL_PRODUCTION").status_code == 200
    assert post_stage_action(test_client, work_order_id, "PACKING", "start", station_id="PACKING").status_code == 200

    packing_response = test_client.post(
        f"/process/work-orders/{work_order_id}/packing/complete",
        json={"counted_quantity": 10, "ok_quantity": 10, "correction_quantity": 0},
        headers={"X-Station-Id": "PACKING"},
    )
    assert packing_response.status_code == 200


def build_work_order_payload(*, coating_type: str = "RAL") -> dict:
    return {
        "title": "Station permission test",
        "coating_type": coating_type,
        "total_quantity": 10,
        "customer_name": "ACME",
        "ral_code": "RAL 7016",
        "paint_code": "P-7016",
        "paint_producer": "AkzoNobel",
        "received_date": "2026-05-30",
        "planned_pickup_date": "2026-06-06",
        "total_area_m2": 20.0,
        "profiles_to_count": True,
        "accessories_to_count": True,
    }
