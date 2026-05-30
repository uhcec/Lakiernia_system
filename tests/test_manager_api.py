from fastapi.testclient import TestClient
import pytest
from sqlalchemy.exc import IntegrityError


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


def get_queue_revision(test_client: TestClient) -> str:
    planned = test_client.get("/manager/work-orders")
    assert planned.status_code == 200
    return max(item["updated_at"] for item in planned.json())


def post_queue_reorder(test_client: TestClient, items: list[dict], queue_revision: str):
    return test_client.post(
        "/manager/queue/reorder",
        json={
            "queue_revision": queue_revision,
            "items": items,
        },
    )


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
    assert correction_order["queue_namespace"] == {"value": "CORRECTIONS", "label": "Corrections"}
    assert correction_order["queue_position"] is None


def test_completed_decoral_correction_preserves_correction_quantity_context_in_manager_queue(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Completed decoral correction", coating_type="DECORAL", total_quantity=10)

    test_client.post(
        f"/manager/work-orders/{created['id']}/plan",
        json={"production_type": "AUTOMATIC", "queue_position": 1},
    )
    test_client.post(f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/start")
    test_client.post(
        f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/finish",
        json={"counted_quantity": 10},
    )
    test_client.post(f"/process/work-orders/{created['id']}/stages/HANGING/start")
    test_client.post(f"/process/work-orders/{created['id']}/stages/HANGING/finish")
    parent_pack_response = test_client.post(
        f"/process/work-orders/{created['id']}/packing/complete",
        json={"counted_quantity": 10, "ok_quantity": 7, "correction_quantity": 3},
    )
    assert parent_pack_response.status_code == 200

    correction_order = next(
        item
        for item in test_client.get("/manager/work-orders/unplanned").json()
        if item["parent_order"]["id"] == created["id"]
    )
    test_client.post(
        f"/manager/work-orders/{correction_order['id']}/plan",
        json={"production_type": "AUTOMATIC", "queue_position": 2},
    )

    parent_batch_id = parent_pack_response.json()["batch_id"]
    test_client.post(f"/process/work-orders/{created['id']}/batches/{parent_batch_id}/stages/DECORAL_PRODUCTION/start")
    test_client.post(f"/process/work-orders/{created['id']}/batches/{parent_batch_id}/stages/DECORAL_PRODUCTION/finish")

    test_client.post(f"/process/work-orders/{correction_order['id']}/stages/HANGING/start")
    test_client.post(f"/process/work-orders/{correction_order['id']}/stages/HANGING/finish")
    test_client.post(
        f"/process/work-orders/{correction_order['id']}/packing/complete",
        json={"counted_quantity": 3, "ok_quantity": 3, "correction_quantity": 0},
    )
    test_client.post(f"/process/work-orders/{correction_order['id']}/stages/DECORAL_PRODUCTION/start")
    test_client.post(f"/process/work-orders/{correction_order['id']}/stages/DECORAL_PRODUCTION/finish")

    planned_response = test_client.get("/manager/work-orders")

    assert planned_response.status_code == 200
    completed_orders = {
        item["id"]: item for item in planned_response.json() if item["process_status"]["value"] == "READY"
    }
    parent_item = completed_orders[created["id"]]
    correction_item = completed_orders[correction_order["id"]]

    assert correction_item["total_quantity"] == 3
    assert correction_item["completed_quantity"] == 3
    assert correction_item["is_historical_correction"] is True
    assert correction_item["parent_order"]["id"] == created["id"]
    assert correction_item["parent_order"]["total_quantity"] == 10
    assert parent_item["is_historical_correction"] is False
    assert parent_item["correction_orders"][0]["id"] == correction_order["id"]
    assert parent_item["correction_orders"][0]["total_quantity"] == 3
    assert parent_item["correction_orders"][0]["is_historical_correction"] is True


def test_corrections_are_listed_in_shared_unplanned_queue(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Correction namespace", coating_type="RAL", total_quantity=100)
    create_work_order(test_client, title="Regular unplanned", coating_type="RAL", total_quantity=50)

    test_client.post(
        f"/manager/work-orders/{created['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 1},
    )
    test_client.post(
        f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/start",
        json={"counted_quantity": 100},
    )
    test_client.post(f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/finish")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/start")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/finish")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PACKING/start")
    test_client.post(
        f"/process/work-orders/{created['id']}/packing/complete",
        json={"counted_quantity": 100, "ok_quantity": 90, "correction_quantity": 10},
    )

    response = test_client.get("/manager/work-orders/unplanned")

    assert response.status_code == 200
    assert any(item["is_correction"] is False for item in response.json())
    assert any(item["is_correction"] is True for item in response.json())


def test_same_queue_position_is_not_allowed_between_normal_and_correction_orders(test_client: TestClient) -> None:
    main_order = create_work_order(test_client, "Main queue")
    correction_parent = create_work_order(test_client, "Correction parent")

    main_plan_response = test_client.post(
        f"/manager/work-orders/{main_order['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 1},
    )

    test_client.post(
        f"/manager/work-orders/{correction_parent['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 4},
    )
    test_client.post(
        f"/process/work-orders/{correction_parent['id']}/stages/SURFACE_PREPARATION/start",
        json={"counted_quantity": 100},
    )
    test_client.post(f"/process/work-orders/{correction_parent['id']}/stages/SURFACE_PREPARATION/finish")
    test_client.post(f"/process/work-orders/{correction_parent['id']}/stages/PRODUCTION/start")
    test_client.post(f"/process/work-orders/{correction_parent['id']}/stages/PRODUCTION/finish")
    test_client.post(f"/process/work-orders/{correction_parent['id']}/stages/PACKING/start")
    test_client.post(
        f"/process/work-orders/{correction_parent['id']}/packing/complete",
        json={"counted_quantity": 100, "ok_quantity": 95, "correction_quantity": 5},
    )

    correction_order = next(
        item
        for item in test_client.get("/manager/work-orders/unplanned").json()
        if item["parent_order"]["id"] == correction_parent["id"]
    )

    correction_plan_response = test_client.post(
        f"/manager/work-orders/{correction_order['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 1},
    )

    assert main_plan_response.status_code == 200
    assert correction_plan_response.status_code == 409
    assert correction_plan_response.json()["detail"] == "Queue position 1 is already taken."


def test_reorder_accepts_mixed_normal_and_correction_orders(test_client: TestClient) -> None:
    main_order = create_work_order(test_client, "Main reorder")
    correction_parent = create_work_order(test_client, "Correction reorder parent")

    test_client.post(
        f"/manager/work-orders/{main_order['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 1},
    )
    test_client.post(
        f"/manager/work-orders/{correction_parent['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 2},
    )
    test_client.post(
        f"/process/work-orders/{correction_parent['id']}/stages/SURFACE_PREPARATION/start",
        json={"counted_quantity": 100},
    )
    test_client.post(f"/process/work-orders/{correction_parent['id']}/stages/SURFACE_PREPARATION/finish")
    test_client.post(f"/process/work-orders/{correction_parent['id']}/stages/PRODUCTION/start")
    test_client.post(f"/process/work-orders/{correction_parent['id']}/stages/PRODUCTION/finish")
    test_client.post(f"/process/work-orders/{correction_parent['id']}/stages/PACKING/start")
    test_client.post(
        f"/process/work-orders/{correction_parent['id']}/packing/complete",
        json={"counted_quantity": 100, "ok_quantity": 95, "correction_quantity": 5},
    )

    correction_order = next(
        item
        for item in test_client.get("/manager/work-orders/unplanned").json()
        if item["parent_order"]["id"] == correction_parent["id"]
    )
    correction_plan_response = test_client.post(
        f"/manager/work-orders/{correction_order['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 3},
    )

    response = post_queue_reorder(
        test_client,
        [
            {"work_order_id": correction_order["id"], "queue_position": 1},
            {"work_order_id": main_order["id"], "queue_position": 2},
            {"work_order_id": correction_parent["id"], "queue_position": 3},
        ],
        get_queue_revision(test_client),
    )

    assert correction_plan_response.status_code == 200
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [correction_order["id"], main_order["id"], correction_parent["id"]]


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


def test_cannot_plan_order_into_occupied_queue_position(test_client: TestClient) -> None:
    first = create_work_order(test_client, "Queue occupied 1")
    second = create_work_order(test_client, "Queue occupied 2")

    first_response = test_client.post(
        f"/manager/work-orders/{first['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 4},
    )
    second_response = test_client.post(
        f"/manager/work-orders/{second['id']}/plan",
        json={"production_type": "AUTOMATIC", "queue_position": 4},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "Queue position 4 is already taken."


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


def test_cannot_update_queue_position_to_occupied_position(test_client: TestClient) -> None:
    first = create_work_order(test_client, "Queue move occupied 1")
    second = create_work_order(test_client, "Queue move occupied 2")

    test_client.post(
        f"/manager/work-orders/{first['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 2},
    )
    test_client.post(
        f"/manager/work-orders/{second['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 5},
    )

    response = test_client.patch(
        f"/manager/work-orders/{second['id']}/queue-position",
        json={"queue_position": 2},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Queue position 2 is already taken."


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

    response = post_queue_reorder(
        test_client,
        [
            {"work_order_id": third["id"], "queue_position": 1},
            {"work_order_id": first["id"], "queue_position": 2},
            {"work_order_id": second["id"], "queue_position": 3},
        ],
        get_queue_revision(test_client),
    )

    assert response.status_code == 200
    assert [(item["id"], item["queue_position"]) for item in response.json()] == [
        (third["id"], 1),
        (first["id"], 2),
        (second["id"], 3),
    ]


def test_drag_drop_reorder_still_works(test_client: TestClient) -> None:
    first = create_work_order(test_client, "Drag queue 1")
    second = create_work_order(test_client, "Drag queue 2")
    third = create_work_order(test_client, "Drag queue 3")

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
        json={"production_type": "MANUAL", "queue_position": 3},
    )

    response = post_queue_reorder(
        test_client,
        [
            {"work_order_id": second["id"], "queue_position": 1},
            {"work_order_id": first["id"], "queue_position": 2},
            {"work_order_id": third["id"], "queue_position": 3},
        ],
        get_queue_revision(test_client),
    )

    assert response.status_code == 200
    assert [(item["id"], item["queue_position"]) for item in response.json()] == [
        (second["id"], 1),
        (first["id"], 2),
        (third["id"], 3),
    ]


def test_reorder_mixed_normal_and_correction_orders_preserves_global_queue_positions(test_client: TestClient) -> None:
    main_order = create_work_order(test_client, "Global queue main")
    ready_order = create_work_order(test_client, "Global queue ready")
    correction_parent = create_work_order(test_client, "Global queue correction")

    test_client.post(
        f"/manager/work-orders/{main_order['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 1},
    )
    test_client.post(
        f"/manager/work-orders/{ready_order['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 2},
    )
    test_client.post(
        f"/manager/work-orders/{correction_parent['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 4},
    )

    test_client.post(
        f"/process/work-orders/{ready_order['id']}/stages/SURFACE_PREPARATION/start",
        json={"counted_quantity": 100},
    )
    test_client.post(f"/process/work-orders/{ready_order['id']}/stages/SURFACE_PREPARATION/finish")
    test_client.post(f"/process/work-orders/{ready_order['id']}/stages/PRODUCTION/start")
    test_client.post(f"/process/work-orders/{ready_order['id']}/stages/PRODUCTION/finish")
    test_client.post(f"/process/work-orders/{ready_order['id']}/stages/PACKING/start")
    test_client.post(
        f"/process/work-orders/{ready_order['id']}/packing/complete",
        json={"counted_quantity": 100, "ok_quantity": 100, "correction_quantity": 0},
    )

    test_client.post(
        f"/process/work-orders/{correction_parent['id']}/stages/SURFACE_PREPARATION/start",
        json={"counted_quantity": 100},
    )
    test_client.post(f"/process/work-orders/{correction_parent['id']}/stages/SURFACE_PREPARATION/finish")
    test_client.post(f"/process/work-orders/{correction_parent['id']}/stages/PRODUCTION/start")
    test_client.post(f"/process/work-orders/{correction_parent['id']}/stages/PRODUCTION/finish")
    test_client.post(f"/process/work-orders/{correction_parent['id']}/stages/PACKING/start")
    test_client.post(
        f"/process/work-orders/{correction_parent['id']}/packing/complete",
        json={"counted_quantity": 100, "ok_quantity": 95, "correction_quantity": 5},
    )

    correction_order = next(
        item
        for item in test_client.get("/manager/work-orders/unplanned").json()
        if item["parent_order"]["id"] == correction_parent["id"]
    )
    correction_plan_response = test_client.post(
        f"/manager/work-orders/{correction_order['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 3},
    )

    response = post_queue_reorder(
        test_client,
        [
            {"work_order_id": correction_order["id"], "queue_position": 1},
            {"work_order_id": main_order["id"], "queue_position": 2},
            {"work_order_id": correction_parent["id"], "queue_position": 3},
        ],
        get_queue_revision(test_client),
    )

    assert correction_plan_response.status_code == 200
    assert response.status_code == 200
    assert [(item["id"], item["queue_position"]) for item in response.json()] == [
        (correction_order["id"], 1),
        (main_order["id"], 2),
        (correction_parent["id"], 3),
        (ready_order["id"], 4),
    ]
    assert len({item["queue_position"] for item in response.json()}) == len(response.json())


def test_bulk_reorder_rejects_positions_taken_by_unmentioned_planned_orders(test_client: TestClient) -> None:
    first = create_work_order(test_client, "Partial reorder 1")
    second = create_work_order(test_client, "Partial reorder 2")
    third = create_work_order(test_client, "Partial reorder 3")

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
        json={"production_type": "MANUAL", "queue_position": 3},
    )

    response = post_queue_reorder(
        test_client,
        [
            {"work_order_id": first["id"], "queue_position": 3},
            {"work_order_id": second["id"], "queue_position": 1},
        ],
        get_queue_revision(test_client),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Queue reorder payload must include all active planned work orders."


def test_bulk_reorder_rejects_invalid_ids(test_client: TestClient) -> None:
    created = create_work_order(test_client, "Bulk queue invalid")
    test_client.post(
        f"/manager/work-orders/{created['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 1},
    )

    response = post_queue_reorder(
        test_client,
        [
            {"work_order_id": created["id"], "queue_position": 1},
            {"work_order_id": 9999, "queue_position": 2},
        ],
        get_queue_revision(test_client),
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


def test_queue_position_integrity_error_returns_controlled_409(monkeypatch: pytest.MonkeyPatch, test_client: TestClient) -> None:
    from app.manager.repository import ManagerRepository

    created = create_work_order(test_client, "Integrity collision")
    original_commit = ManagerRepository.commit

    def raise_integrity_error(self):
        raise IntegrityError("", {}, Exception("unique queue collision"))

    monkeypatch.setattr(ManagerRepository, "commit", raise_integrity_error)

    response = test_client.post(
        f"/manager/work-orders/{created['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 1},
    )

    monkeypatch.setattr(ManagerRepository, "commit", original_commit)

    assert response.status_code == 409
    assert response.json()["detail"] == "Queue position 1 is already taken."


def test_stale_reorder_snapshot_is_rejected(test_client: TestClient) -> None:
    first = create_work_order(test_client, "Stale queue 1")
    second = create_work_order(test_client, "Stale queue 2")
    third = create_work_order(test_client, "Stale queue 3")

    test_client.post(f"/manager/work-orders/{first['id']}/plan", json={"production_type": "MANUAL", "queue_position": 1})
    test_client.post(f"/manager/work-orders/{second['id']}/plan", json={"production_type": "MANUAL", "queue_position": 2})
    test_client.post(f"/manager/work-orders/{third['id']}/plan", json={"production_type": "MANUAL", "queue_position": 3})

    stale_revision = get_queue_revision(test_client)
    move_response = test_client.patch(
        f"/manager/work-orders/{third['id']}/queue-position",
        json={"queue_position": 4},
    )
    assert move_response.status_code == 200

    response = post_queue_reorder(
        test_client,
        [
            {"work_order_id": third["id"], "queue_position": 1},
            {"work_order_id": first["id"], "queue_position": 2},
            {"work_order_id": second["id"], "queue_position": 3},
        ],
        stale_revision,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Queue reorder payload is stale. Refresh the manager queue and try again."


def test_fresh_reorder_snapshot_is_accepted(test_client: TestClient) -> None:
    first = create_work_order(test_client, "Fresh queue 1")
    second = create_work_order(test_client, "Fresh queue 2")
    third = create_work_order(test_client, "Fresh queue 3")

    test_client.post(f"/manager/work-orders/{first['id']}/plan", json={"production_type": "MANUAL", "queue_position": 1})
    test_client.post(f"/manager/work-orders/{second['id']}/plan", json={"production_type": "MANUAL", "queue_position": 2})
    test_client.post(f"/manager/work-orders/{third['id']}/plan", json={"production_type": "MANUAL", "queue_position": 3})

    response = post_queue_reorder(
        test_client,
        [
            {"work_order_id": third["id"], "queue_position": 1},
            {"work_order_id": first["id"], "queue_position": 2},
            {"work_order_id": second["id"], "queue_position": 3},
        ],
        get_queue_revision(test_client),
    )

    assert response.status_code == 200
    assert [(item["id"], item["queue_position"]) for item in response.json()] == [
        (third["id"], 1),
        (first["id"], 2),
        (second["id"], 3),
    ]


def test_two_manager_overwrite_is_prevented_by_queue_revision(test_client: TestClient) -> None:
    first = create_work_order(test_client, "Manager overwrite 1")
    second = create_work_order(test_client, "Manager overwrite 2")
    third = create_work_order(test_client, "Manager overwrite 3")

    test_client.post(f"/manager/work-orders/{first['id']}/plan", json={"production_type": "MANUAL", "queue_position": 1})
    test_client.post(f"/manager/work-orders/{second['id']}/plan", json={"production_type": "MANUAL", "queue_position": 2})
    test_client.post(f"/manager/work-orders/{third['id']}/plan", json={"production_type": "MANUAL", "queue_position": 3})

    manager_a_revision = get_queue_revision(test_client)
    manager_b_revision = get_queue_revision(test_client)

    first_reorder = post_queue_reorder(
        test_client,
        [
            {"work_order_id": third["id"], "queue_position": 1},
            {"work_order_id": first["id"], "queue_position": 2},
            {"work_order_id": second["id"], "queue_position": 3},
        ],
        manager_a_revision,
    )
    second_reorder = post_queue_reorder(
        test_client,
        [
            {"work_order_id": second["id"], "queue_position": 1},
            {"work_order_id": third["id"], "queue_position": 2},
            {"work_order_id": first["id"], "queue_position": 3},
        ],
        manager_b_revision,
    )
    final_queue = test_client.get("/manager/work-orders")

    assert first_reorder.status_code == 200
    assert second_reorder.status_code == 409
    assert second_reorder.json()["detail"] == "Queue reorder payload is stale. Refresh the manager queue and try again."
    assert [(item["id"], item["queue_position"]) for item in final_queue.json()] == [
        (third["id"], 1),
        (first["id"], 2),
        (second["id"], 3),
    ]