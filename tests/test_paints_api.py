from fastapi.testclient import TestClient


def test_paint_lookup_returns_zero_for_missing_card(test_client: TestClient) -> None:
    response = test_client.get(
        "/paints/lookup",
        params={
            "ral_code": "RAL 7016",
            "paint_producer": "AkzoNobel",
            "paint_code": "P-7016",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "paint_id": None,
        "ral_code": "RAL 7016",
        "paint_producer": "AkzoNobel",
        "paint_code": "P-7016",
        "current_quantity_kg": 0,
        "exists_in_inventory": False,
    }


def test_delivery_creates_paint_card_and_updates_current_stock(test_client: TestClient) -> None:
    response = test_client.post(
        "/paints/deliveries",
        json={
            "ral_code": "RAL 7016",
            "paint_producer": "AkzoNobel",
            "paint_code": "P-7016",
            "quantity_kg": 25,
            "movement_date": "2026-06-02",
            "note": "Dostawa poranna",
        },
        headers={"X-Station-Id": "OFFICE"},
    )

    assert response.status_code == 201
    assert response.json()["current_quantity_kg"] == 25

    lookup_response = test_client.get(
        "/paints/lookup",
        params={
            "ral_code": "RAL 7016",
            "paint_producer": "AkzoNobel",
            "paint_code": "P-7016",
        },
    )

    assert lookup_response.status_code == 200
    assert lookup_response.json()["current_quantity_kg"] == 25
    assert lookup_response.json()["exists_in_inventory"] is True


def test_manual_adjustment_rejects_negative_resulting_stock(test_client: TestClient) -> None:
    delivery_response = test_client.post(
        "/paints/deliveries",
        json={
            "ral_code": "RAL 7016",
            "paint_producer": "AkzoNobel",
            "paint_code": "P-7016",
            "quantity_kg": 10,
            "movement_date": "2026-06-02",
        },
        headers={"X-Station-Id": "OFFICE"},
    )
    assert delivery_response.status_code == 201

    response = test_client.post(
        "/paints/adjustments",
        json={
            "ral_code": "RAL 7016",
            "paint_producer": "AkzoNobel",
            "paint_code": "P-7016",
            "quantity_delta_kg": -12,
            "movement_date": "2026-06-02",
            "note": "Korekta błędna",
        },
        headers={"X-Station-Id": "OFFICE"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Insufficient paint stock for AkzoNobel / RAL 7016 / P-7016."


def test_paint_movements_list_returns_delivery_and_adjustment_history(test_client: TestClient) -> None:
    delivery_response = test_client.post(
        "/paints/deliveries",
        json={
            "ral_code": "RAL 7016",
            "paint_producer": "AkzoNobel",
            "paint_code": "P-7016",
            "quantity_kg": 20,
            "movement_date": "2026-06-02",
            "note": "Dostawa główna",
        },
        headers={"X-Station-Id": "OFFICE"},
    )
    assert delivery_response.status_code == 201
    paint_id = delivery_response.json()["id"]

    adjustment_response = test_client.post(
        "/paints/adjustments",
        json={
            "ral_code": "RAL 7016",
            "paint_producer": "AkzoNobel",
            "paint_code": "P-7016",
            "quantity_delta_kg": -2,
            "movement_date": "2026-06-03",
            "note": "Korekta stanu",
        },
        headers={"X-Station-Id": "OFFICE"},
    )
    assert adjustment_response.status_code == 201

    response = test_client.get(f"/paints/{paint_id}/movements")

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert response.json()["items"][0]["movement_type"] == {"value": "MANUAL_ADJUSTMENT", "label": "Korekta ręczna"}
    assert response.json()["items"][0]["resulting_quantity_kg"] == 18
    assert response.json()["items"][1]["movement_type"] == {"value": "DELIVERY", "label": "Dostawa"}
