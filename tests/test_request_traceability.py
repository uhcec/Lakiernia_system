from fastapi.testclient import TestClient


REQUEST_ID_HEADER = "X-Request-Id"


def build_create_payload(**overrides: object) -> dict:
    payload = {
        "title": "Traceability API",
        "coating_type": "RAL",
        "total_quantity": 100,
        "customer_name": "ACME",
        "ral_code": "RAL 7016",
        "paint_producer": "AkzoNobel",
        "received_date": "2026-05-29",
        "profiles_to_count": True,
        "accessories_to_count": True,
    }
    payload.update(overrides)
    return payload


def test_request_id_header_is_generated_when_missing(test_client: TestClient) -> None:
    response = test_client.get("/health")

    assert response.status_code == 200
    request_id = response.headers[REQUEST_ID_HEADER]
    assert request_id
    assert len(request_id) == 32


def test_request_id_header_echoes_valid_client_value(test_client: TestClient) -> None:
    response = test_client.get("/health", headers={REQUEST_ID_HEADER: "factory-trace-123"})

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == "factory-trace-123"


def test_invalid_request_id_header_is_replaced(test_client: TestClient) -> None:
    response = test_client.get("/health", headers={REQUEST_ID_HEADER: "  "})

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER]
    assert response.headers[REQUEST_ID_HEADER] != "  "


def test_audit_event_records_current_request_id(test_client: TestClient) -> None:
    create_response = test_client.post(
        "/work-orders",
        json=build_create_payload(),
        headers={REQUEST_ID_HEADER: "trace-create-001", "X-Station-Id": "OFFICE"},
    )
    assert create_response.status_code == 201

    work_order_id = create_response.json()["id"]
    audit_response = test_client.get(f"/audit/work-orders/{work_order_id}/events")

    assert audit_response.status_code == 200
    events = audit_response.json()
    assert events[0]["event_type"] == "work_order.created"
    assert events[0]["request_id"] == "trace-create-001"
