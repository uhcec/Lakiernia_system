from fastapi.testclient import TestClient


def build_create_payload(**overrides: object) -> dict:
    payload = {
        "title": "Audyt API",
        "coating_type": "RAL",
        "total_quantity": 100,
        "customer_name": "ACME",
        "ral_code": "RAL 7016",
        "paint_code": "P-7016",
        "paint_producer": "AkzoNobel",
        "received_date": "2026-05-29",
        "total_area_m2": 24.0,
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
        "external_order_number": None,
        "work_order_kind": "STANDARD",
        "is_ocynk": False,
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


def test_list_audit_events_filters_by_request_and_station(test_client: TestClient) -> None:
    first_response = test_client.post(
        "/work-orders",
        json=build_create_payload(title="Audyt request A"),
        headers={"X-Request-Id": "audit-search-a", "X-Station-Id": "OFFICE"},
    )
    second_create_response = test_client.post(
        "/work-orders",
        json=build_create_payload(title="Audyt request B"),
        headers={"X-Request-Id": "audit-search-b-create", "X-Station-Id": "OFFICE"},
    )
    assert first_response.status_code == 201
    assert second_create_response.status_code == 201

    second_response = test_client.post(
        f"/manager/work-orders/{second_create_response.json()['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 1},
        headers={"X-Request-Id": "audit-search-b", "X-Station-Id": "MANAGER"},
    )
    assert second_response.status_code == 200

    request_response = test_client.get("/audit/events", params={"request_id": "audit-search-a"})

    assert request_response.status_code == 200
    request_body = request_response.json()
    assert request_body["limit"] == 100
    assert request_body["offset"] == 0
    assert [event["request_id"] for event in request_body["items"]] == ["audit-search-a"]
    assert request_body["items"][0]["work_order_id"] == first_response.json()["id"]

    station_response = test_client.get("/audit/events", params={"station_id": "MANAGER"})

    assert station_response.status_code == 200
    station_items = station_response.json()["items"]
    assert [event["station_id"] for event in station_items] == ["MANAGER"]
    assert station_items[0]["work_order_id"] == second_response.json()["id"]


def test_list_audit_events_filters_by_event_type_and_work_order(test_client: TestClient) -> None:
    create_response = test_client.post("/work-orders", json=build_create_payload(), headers={"X-Request-Id": "audit-filter"})
    assert create_response.status_code == 201
    work_order_id = create_response.json()["id"]
    update_response = test_client.patch(f"/work-orders/{work_order_id}", json={"notes": "Audit search note"})
    assert update_response.status_code == 200

    response = test_client.get(
        "/audit/events",
        params={"work_order_id": work_order_id, "event_type": "work_order.updated", "limit": 10},
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["event_type"] == "work_order.updated"
    assert items[0]["work_order_id"] == work_order_id
    assert items[0]["details"]["updated_fields"] == ["notes"]


def test_export_audit_events_csv_uses_search_filters(test_client: TestClient) -> None:
    create_response = test_client.post(
        "/work-orders",
        json=build_create_payload(title="Eksport audytu"),
        headers={"X-Request-Id": "audit-export", "X-Station-Id": "OFFICE"},
    )
    assert create_response.status_code == 201

    response = test_client.get("/audit/events/export.csv", params={"request_id": "audit-export"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == 'attachment; filename="audit-events.csv"'
    lines = response.text.splitlines()
    assert lines[0] == "id,created_at,event_type,station_id,request_id,work_order_id,target_type,target_id,summary,details_json"
    assert len(lines) == 2
    assert "work_order.created" in lines[1]
    assert "audit-export" in lines[1]
    assert "OFFICE" in lines[1]
