from fastapi.testclient import TestClient


def build_create_payload(**overrides: object) -> dict:
    payload = {
        "title": "Audyt API",
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


def test_list_work_order_audit_events_returns_chronological_history(test_client: TestClient) -> None:
    create_response = test_client.post(
        "/work-orders",
        json=build_create_payload(),
        headers={"X-Station-Id": "OFFICE"},
    )
    assert create_response.status_code == 201
    work_order_id = create_response.json()["id"]

    update_response = test_client.patch(
        f"/work-orders/{work_order_id}",
        json={"title": "Audyt API po zmianie"},
        headers={"X-Station-Id": "OFFICE"},
    )
    assert update_response.status_code == 200

    response = test_client.get(f"/audit/work-orders/{work_order_id}/events")

    assert response.status_code == 200
    body = response.json()
    assert [event["event_type"] for event in body] == ["work_order.created", "work_order.updated"]
    assert body[0]["station_id"] == "OFFICE"
    assert body[0]["details"] == {
        "order_number": create_response.json()["order_number"],
        "is_incomplete_on_arrival": False,
    }
    assert body[1]["details"]["updated_fields"] == ["title"]
    assert body[1]["details"]["changes"]["title"] == {
        "before": "Audyt API",
        "after": "Audyt API po zmianie",
    }


def test_list_work_order_audit_events_supports_pagination(test_client: TestClient) -> None:
    create_response = test_client.post("/work-orders", json=build_create_payload())
    assert create_response.status_code == 201
    work_order_id = create_response.json()["id"]
    test_client.patch(f"/work-orders/{work_order_id}", json={"notes": "Pierwsza notatka"})

    response = test_client.get(f"/audit/work-orders/{work_order_id}/events", params={"limit": 1, "offset": 1})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["event_type"] == "work_order.updated"


def test_list_work_order_audit_events_rejects_missing_work_order(test_client: TestClient) -> None:
    response = test_client.get("/audit/work-orders/999/events")

    assert response.status_code == 404
    assert response.json() == {"detail": "Work order 999 not found."}
