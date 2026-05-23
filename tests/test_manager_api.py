from fastapi.testclient import TestClient


def test_list_unplanned_work_orders(test_client: TestClient) -> None:
    first = test_client.post("/work-orders", json={"title": "Unplanned 1"}).json()
    second = test_client.post("/work-orders", json={"title": "Unplanned 2"}).json()
    planned = test_client.post("/work-orders", json={"title": "Planned"}).json()

    test_client.post(
        f"/manager/work-orders/{planned['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 3},
    )

    response = test_client.get("/manager/work-orders/unplanned")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [first["id"], second["id"]]


def test_list_planned_work_orders_sorted_by_queue_position(test_client: TestClient) -> None:
    first = test_client.post("/work-orders", json={"title": "Queue 30"}).json()
    second = test_client.post("/work-orders", json={"title": "Queue 10"}).json()
    third = test_client.post("/work-orders", json={"title": "Queue 20"}).json()

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
    created = test_client.post("/work-orders", json={"title": "Plan me"}).json()

    response = test_client.post(
        f"/manager/work-orders/{created['id']}/plan",
        json={"production_type": "AUTOMATIC", "queue_position": 5},
    )

    assert response.status_code == 200
    assert response.json()["production_type"] == {"value": "AUTOMATIC", "label": "Automatyczna"}
    assert response.json()["queue_position"] == 5


def test_cannot_assign_plan_twice(test_client: TestClient) -> None:
    created = test_client.post("/work-orders", json={"title": "Plan once"}).json()

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
    created = test_client.post("/work-orders", json={"title": "Move in queue"}).json()

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