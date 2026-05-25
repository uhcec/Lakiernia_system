from fastapi.testclient import TestClient


def build_create_payload(title: str, coating_type: str = "RAL", **overrides: object) -> dict:
    payload = {
        "title": title,
        "coating_type": coating_type,
        "total_quantity": 100,
        "customer_name": "ACME",
        "ral_code": "RAL 7016",
        "paint_producer": "AkzoNobel",
        "received_date": "2026-05-25",
        "profiles_to_count": True,
        "accessories_to_count": True,
    }
    payload.update(overrides)
    return payload


def create_work_order(test_client: TestClient, title: str, coating_type: str = "RAL", **overrides: object) -> dict:
    return test_client.post("/work-orders", json=build_create_payload(title, coating_type, **overrides)).json()


def test_list_unplanned_work_orders(test_client: TestClient) -> None:
    first = create_work_order(test_client, "Unplanned 1")
    second = create_work_order(test_client, "Unplanned 2")
    incomplete = create_work_order(test_client, "Incomplete", is_incomplete_on_arrival=True)
    planned = create_work_order(test_client, "Planned")

    test_client.post(
        f"/manager/work-orders/{planned['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 3},
    )

    response = test_client.get("/manager/work-orders/unplanned")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [first["id"], second["id"]]
    assert incomplete["id"] not in [item["id"] for item in response.json()]


def test_list_planned_work_orders_sorted_by_queue_position(test_client: TestClient) -> None:
    first = create_work_order(test_client, "Queue 30")
    second = create_work_order(test_client, "Queue 10")
    third = create_work_order(test_client, "Queue 20")

    test_client.post(
        f"/manager/work-orders/{first['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 30},
    )
    test_client.post(
        f"/manager/work-orders/{second['id']}/plan",
        json={"production_type": "AUTOMATIC", "queue_position": 10},
    )
    test_client.post(
        f"/manager/work-orders/{third['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 20},
    )

    response = test_client.get("/manager/work-orders")

    assert response.status_code == 200
    assert [item["queue_position"] for item in response.json()] == [10, 20, 30]


def test_assign_plan_sets_production_type_and_queue_position(test_client: TestClient) -> None:
    created = create_work_order(test_client, "Plan me")

    response = test_client.post(
        f"/manager/work-orders/{created['id']}/plan",
        json={"production_type": "AUTOMATIC", "queue_position": 5},
    )

    assert response.status_code == 200
    assert response.json()["production_type"] == {"value": "AUTOMATIC", "label": "Automatyczna"}
    assert response.json()["queue_position"] == 5


def test_cannot_plan_incomplete_order(test_client: TestClient) -> None:
    created = create_work_order(test_client, "Incomplete plan", is_incomplete_on_arrival=True)

    response = test_client.post(
        f"/manager/work-orders/{created['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 1},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Cannot plan incomplete order. Mark as complete first."


def test_packing_correction_creates_new_unplanned_work_order(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Correction planning", coating_type="RAL", total_quantity=100)

    test_client.post(
        f"/manager/work-orders/{created['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 1},
    )
    test_client.post(
        f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/start",
        json={"counted_quantity": 100},
    )
    test_client.post(
        f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/finish",
        json={"counted_quantity": 100},
    )
    test_client.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/start")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/finish")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PACKING/start")
    packing_response = test_client.post(
        f"/process/work-orders/{created['id']}/packing/complete",
        json={"counted_quantity": 100, "ok_quantity": 92, "correction_quantity": 8},
    )

    response = test_client.get("/manager/work-orders/unplanned")

    assert packing_response.status_code == 200
    assert response.status_code == 200
    correction_order = next(item for item in response.json() if item["is_correction"] is True)
    assert correction_order["total_quantity"] == 8
    assert correction_order["parent_order"]["id"] == created["id"]
    assert correction_order["queue_position"] is None


def test_complete_order_can_still_be_planned(test_client: TestClient) -> None:
    created = create_work_order(test_client, "Complete plan")

    response = test_client.post(
        f"/manager/work-orders/{created['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 1},
    )

    assert response.status_code == 200
    assert response.json()["production_type"] == {"value": "MANUAL", "label": "Manualna"}
    assert response.json()["queue_position"] == 1


def test_cannot_assign_plan_twice(test_client: TestClient) -> None:
    created = create_work_order(test_client, "Plan once")

    first_response = test_client.post(
        f"/manager/work-orders/{created['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 1},
    )
    second_response = test_client.post(
        f"/manager/work-orders/{created['id']}/plan",
        json={"production_type": "AUTOMATIC", "queue_position": 2},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 409


def test_update_queue_position_for_planned_order(test_client: TestClient) -> None:
    created = create_work_order(test_client, "Move in queue")

    test_client.post(
        f"/manager/work-orders/{created['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 9},
    )

    response = test_client.patch(
        f"/manager/work-orders/{created['id']}/queue-position",
        json={"queue_position": 2},
    )

    assert response.status_code == 200
    assert response.json()["queue_position"] == 2


def test_bulk_reorder_updates_queue_positions(test_client: TestClient) -> None:
    first = create_work_order(test_client, "Bulk queue 1")
    second = create_work_order(test_client, "Bulk queue 2")
    third = create_work_order(test_client, "Bulk queue 3")

    test_client.post(
        f"/manager/work-orders/{first['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 1},
    )
    test_client.post(
        f"/manager/work-orders/{second['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 2},
    )
    test_client.post(
        f"/manager/work-orders/{third['id']}/plan",
        json={"production_type": "AUTOMATIC", "queue_position": 3},
    )

    response = test_client.post(
        "/manager/queue/reorder",
        json=[
            {"work_order_id": third["id"], "queue_position": 1},
            {"work_order_id": first["id"], "queue_position": 2},
            {"work_order_id": second["id"], "queue_position": 3},
        ],
    )

    assert response.status_code == 200
    assert [(item["id"], item["queue_position"]) for item in response.json()] == [
        (third["id"], 1),
        (first["id"], 2),
        (second["id"], 3),
    ]


def test_bulk_reorder_rejects_invalid_ids(test_client: TestClient) -> None:
    created = create_work_order(test_client, "Bulk queue invalid")
    test_client.post(
        f"/manager/work-orders/{created['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 1},
    )

    response = test_client.post(
        "/manager/queue/reorder",
        json=[
            {"work_order_id": created["id"], "queue_position": 1},
            {"work_order_id": 9999, "queue_position": 2},
        ],
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Work order 9999 not found."


def test_marking_incomplete_order_complete_adds_it_to_unplanned_list(test_client: TestClient) -> None:
    incomplete = create_work_order(test_client, "Incomplete", is_incomplete_on_arrival=True)

    before_response = test_client.get("/manager/work-orders/unplanned")
    complete_response = test_client.post(f"/work-orders/{incomplete['id']}/mark-complete-arrival")
    after_response = test_client.get("/manager/work-orders/unplanned")

    assert before_response.status_code == 200
    assert incomplete["id"] not in [item["id"] for item in before_response.json()]
    assert complete_response.status_code == 200
    assert after_response.status_code == 200
    assert incomplete["id"] in [item["id"] for item in after_response.json()]