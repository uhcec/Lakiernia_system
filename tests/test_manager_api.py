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
        "paint_code": "P-7016",
        "paint_producer": "AkzoNobel",
        "received_date": "2026-05-25",
        "total_area_m2": 24.0,
        "profiles_to_count": True,
        "accessories_to_count": True,
    }
    payload.update(overrides)
    return payload


def create_work_order(test_client: TestClient, title: str, coating_type: str = "RAL", **overrides: object) -> dict:
    return test_client.post("/work-orders", json=build_create_payload(title, coating_type, **overrides)).json()


def advance_to_hanging(test_client: TestClient, work_order_id: int) -> None:
    start_response = test_client.post(f"/process/work-orders/{work_order_id}/stages/SURFACE_PREPARATION/start")
    finish_response = test_client.post(
        f"/process/work-orders/{work_order_id}/stages/SURFACE_PREPARATION/finish",
        json={"counted_quantity": 100},
    )

    assert start_response.status_code == 200
    assert finish_response.status_code == 200


def complete_manual_ral_order(test_client: TestClient, work_order_id: int, *, quantity: int = 100) -> None:
    start_surface_response = test_client.post(f"/process/work-orders/{work_order_id}/stages/SURFACE_PREPARATION/start")
    finish_surface_response = test_client.post(
        f"/process/work-orders/{work_order_id}/stages/SURFACE_PREPARATION/finish",
        json={"counted_quantity": quantity},
    )
    start_production_response = test_client.post(f"/process/work-orders/{work_order_id}/stages/PRODUCTION/start")
    finish_production_response = test_client.post(f"/process/work-orders/{work_order_id}/stages/PRODUCTION/finish")
    start_packing_response = test_client.post(f"/process/work-orders/{work_order_id}/stages/PACKING/start")
    complete_packing_response = test_client.post(
        f"/process/work-orders/{work_order_id}/packing/complete",
        json={"counted_quantity": quantity, "ok_quantity": quantity, "correction_quantity": 0},
    )

    assert start_surface_response.status_code == 200
    assert finish_surface_response.status_code == 200
    assert start_production_response.status_code == 200
    assert finish_production_response.status_code == 200
    assert start_packing_response.status_code == 200
    assert complete_packing_response.status_code == 200


def create_packing_correction(
    test_client: TestClient,
    title: str,
    *,
    queue_position: int,
    correction_quantity: int,
    correction_reason_category: str,
) -> dict:
    created = create_work_order(test_client, title=title, coating_type="DECORAL", total_quantity=100)

    plan_response = test_client.post(
        f"/manager/work-orders/{created['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": queue_position},
    )
    start_surface_response = test_client.post(f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/start")
    finish_surface_response = test_client.post(
        f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/finish",
        json={"counted_quantity": 100},
    )
    start_production_response = test_client.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/start")
    finish_production_response = test_client.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/finish")
    start_packing_response = test_client.post(f"/process/work-orders/{created['id']}/stages/PACKING/start")
    packing_response = test_client.post(
        f"/process/work-orders/{created['id']}/packing/complete",
        json={
            "counted_quantity": 100,
            "ok_quantity": 100 - correction_quantity,
            "correction_quantity": correction_quantity,
            "correction_profiles_quantity": correction_quantity,
            "correction_accessories_quantity": 0,
            "correction_reason_category": correction_reason_category,
        },
    )

    assert plan_response.status_code == 200
    assert start_surface_response.status_code == 200
    assert finish_surface_response.status_code == 200
    assert start_production_response.status_code == 200
    assert finish_production_response.status_code == 200
    assert start_packing_response.status_code == 200
    assert packing_response.status_code == 200

    correction_orders = [
        item
        for item in test_client.get("/manager/work-orders/unplanned").json()
        if item["parent_order"] and item["parent_order"]["id"] == created["id"]
    ]
    assert len(correction_orders) == 1
    return correction_orders[0]


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


def test_manager_work_orders_expose_current_paint_shortage_signal(test_client: TestClient) -> None:
    delivery_response = test_client.post(
        "/paints/deliveries",
        json={
            "ral_code": "RAL 7016",
            "paint_producer": "AkzoNobel",
            "paint_code": "P-7016",
            "quantity_kg": 12,
            "movement_date": "2026-05-25",
        },
        headers={"X-Station-Id": "OFFICE"},
    )
    assert delivery_response.status_code == 201

    created = create_work_order(test_client, "Paint shortage queue", total_area_m2=100.0)

    unplanned_response = test_client.get("/manager/work-orders/unplanned")

    assert unplanned_response.status_code == 200
    item = next(entry for entry in unplanned_response.json() if entry["id"] == created["id"])
    assert item["predicted_paint_quantity_kg"] == 17.0
    assert item["current_paint_stock_quantity_kg"] == 12.0
    assert item["paint_inventory_insufficient_for_prediction"] is True
    assert item["paint_inventory_shortage_quantity_kg"] == 5.0


def test_manager_queue_warns_when_hanging_resource_blocks_next_order(test_client: TestClient) -> None:
    first = create_work_order(test_client, "Blocking hanging first")
    second = create_work_order(test_client, "Blocking hanging second")
    test_client.post(f"/manager/work-orders/{first['id']}/plan", json={"production_type": "AUTOMATIC", "queue_position": 1})
    test_client.post(f"/manager/work-orders/{second['id']}/plan", json={"production_type": "AUTOMATIC", "queue_position": 2})
    advance_to_hanging(test_client, first["id"])
    advance_to_hanging(test_client, second["id"])

    start_response = test_client.post(f"/process/work-orders/{first['id']}/stages/HANGING/start")
    response = test_client.get("/manager/work-orders")

    assert start_response.status_code == 200
    assert response.status_code == 200
    first_item = next(item for item in response.json() if item["id"] == first["id"])
    second_item = next(item for item in response.json() if item["id"] == second["id"])
    assert first_item["queue_blocked_by_resource"] is None
    assert first_item["queue_blocked_reason"] is None
    assert second_item["queue_blocked_by_resource"] == "HANGING"
    assert second_item["queue_blocked_reason"] == "Zawieszanie zajęte"


def test_manager_queue_warns_when_automatic_line_blocks_hanging_finish(test_client: TestClient) -> None:
    first = create_work_order(test_client, "Blocking automatic line first")
    second = create_work_order(test_client, "Blocking automatic line second")
    test_client.post(f"/manager/work-orders/{first['id']}/plan", json={"production_type": "AUTOMATIC", "queue_position": 1})
    test_client.post(f"/manager/work-orders/{second['id']}/plan", json={"production_type": "AUTOMATIC", "queue_position": 2})
    advance_to_hanging(test_client, first["id"])
    advance_to_hanging(test_client, second["id"])
    test_client.post(f"/process/work-orders/{first['id']}/stages/HANGING/start")
    test_client.post(f"/process/work-orders/{first['id']}/stages/HANGING/finish")

    second_start_response = test_client.post(f"/process/work-orders/{second['id']}/stages/HANGING/start")
    response = test_client.get("/manager/work-orders")

    assert second_start_response.status_code == 200
    assert response.status_code == 200
    first_item = next(item for item in response.json() if item["id"] == first["id"])
    second_item = next(item for item in response.json() if item["id"] == second["id"])
    assert first_item["queue_blocked_by_resource"] is None
    assert first_item["queue_blocked_reason"] is None
    assert second_item["queue_blocked_by_resource"] == "AUTOMATIC_LINE"
    assert second_item["queue_blocked_reason"] == "Linia automatyczna zajęta"


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


def test_ral_packing_correction_resets_order_to_unplanned(test_client: TestClient) -> None:
    created = create_work_order(
        test_client,
        title="Correction planning",
        coating_type="RAL",
        total_quantity=100,
        planned_pickup_date="2026-06-18",
    )

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
        json={
            "counted_quantity": 100,
            "ok_quantity": 92,
            "correction_quantity": 8,
            "correction_profiles_quantity": 8,
            "correction_accessories_quantity": 0,
            "correction_reason_category": "niedomalowanie",
            "correction_reason_note": "dolna listwa",
        },
    )

    unplanned_response = test_client.get("/manager/work-orders/unplanned")
    detail = test_client.get(f"/work-orders/{created['id']}")

    assert packing_response.status_code == 200
    assert unplanned_response.status_code == 200
    order_in_unplanned = next(item for item in unplanned_response.json() if item["id"] == created["id"])
    assert order_in_unplanned["process_status"]["value"] == "TO_BE_PLANNED"
    assert order_in_unplanned["queue_position"] is None
    assert detail.json()["completed_quantity"] == 92
    assert detail.json()["current_active_quantity"] == 8
    assert detail.json()["correction_reason_category"] == "niedomalowanie"
    assert detail.json()["correction_reason_note"] == "dolna listwa"
    all_orders = test_client.get("/work-orders").json()["items"]
    assert len(all_orders) == 1


def test_correction_reason_report_aggregates_correction_children(test_client: TestClient) -> None:
    create_packing_correction(
        test_client,
        "Correction report first",
        queue_position=1,
        correction_quantity=8,
        correction_reason_category="niedomalowanie",
    )
    create_packing_correction(
        test_client,
        "Correction report second",
        queue_position=2,
        correction_quantity=3,
        correction_reason_category="niedomalowanie",
    )
    create_packing_correction(
        test_client,
        "Correction report third",
        queue_position=3,
        correction_quantity=4,
        correction_reason_category="za grubo",
    )

    response = test_client.get("/manager/corrections/reason-report")

    assert response.status_code == 200
    assert response.json() == [
        {
            "correction_reason_category": "niedomalowanie",
            "work_order_count": 2,
            "total_correction_quantity": 11,
        },
        {
            "correction_reason_category": "za grubo",
            "work_order_count": 1,
            "total_correction_quantity": 4,
        },
    ]


def test_correction_reason_report_exports_csv(test_client: TestClient) -> None:
    create_packing_correction(
        test_client,
        "Correction CSV",
        queue_position=1,
        correction_quantity=5,
        correction_reason_category="wtrącenia",
    )

    response = test_client.get("/manager/corrections/reason-report/export.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.text == (
        "correction_reason_category,work_order_count,total_correction_quantity\n"
        "wtrącenia,1,5\n"
    )


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
    test_client.post(
        "/paints/deliveries",
        json={
            "ral_code": "RAL 7016",
            "paint_producer": "AkzoNobel",
            "paint_code": "P-7016",
            "quantity_kg": 50.0,
            "movement_date": "2026-05-25",
        },
        headers={"X-Station-Id": "OFFICE"},
    )
    test_client.post(
        f"/process/work-orders/{created['id']}/automatic-production/paint-consumption",
        json={"consumed_paint_quantity_kg": 5.0},
        headers={"X-Station-Id": "AUTOMATIC_PRODUCTION"},
    )
    parent_pack_response = test_client.post(
        f"/process/work-orders/{created['id']}/packing/complete",
        json={
            "counted_quantity": 10,
            "ok_quantity": 7,
            "correction_quantity": 3,
            "correction_profiles_quantity": 3,
            "correction_accessories_quantity": 0,
            "correction_reason_category": "wtrącenia",
        },
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
        f"/process/work-orders/{correction_order['id']}/automatic-production/paint-consumption",
        json={"consumed_paint_quantity_kg": 2.0},
        headers={"X-Station-Id": "AUTOMATIC_PRODUCTION"},
    )
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


def test_ral_corrections_reset_order_to_unplanned_queue(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Correction namespace", coating_type="RAL", total_quantity=100)
    regular = create_work_order(test_client, title="Regular unplanned", coating_type="RAL", total_quantity=50)

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
        json={
            "counted_quantity": 100,
            "ok_quantity": 90,
            "correction_quantity": 10,
            "correction_profiles_quantity": 10,
            "correction_accessories_quantity": 0,
            "correction_reason_category": "niedomalowanie",
        },
    )

    response = test_client.get("/manager/work-orders/unplanned")

    assert response.status_code == 200
    unplanned_ids = [item["id"] for item in response.json()]
    assert created["id"] in unplanned_ids
    assert regular["id"] in unplanned_ids
    reset_order = next(item for item in response.json() if item["id"] == created["id"])
    assert reset_order["process_status"]["value"] == "TO_BE_PLANNED"
    assert reset_order["queue_position"] is None


def test_same_queue_position_is_not_allowed_between_normal_and_correction_rounds(test_client: TestClient) -> None:
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
        json={
            "counted_quantity": 100,
            "ok_quantity": 95,
            "correction_quantity": 5,
            "correction_profiles_quantity": 5,
            "correction_accessories_quantity": 0,
            "correction_reason_category": "niedomalowanie",
        },
    )

    correction_plan_response = test_client.post(
        f"/manager/work-orders/{correction_parent['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 1},
    )

    assert main_plan_response.status_code == 200
    assert correction_plan_response.status_code == 409
    assert correction_plan_response.json()["detail"] == "Queue position 1 is already taken."


def test_reorder_accepts_normal_and_correction_round_orders(test_client: TestClient) -> None:
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
        json={
            "counted_quantity": 100,
            "ok_quantity": 95,
            "correction_quantity": 5,
            "correction_profiles_quantity": 5,
            "correction_accessories_quantity": 0,
            "correction_reason_category": "niedomalowanie",
        },
    )

    correction_plan_response = test_client.post(
        f"/manager/work-orders/{correction_parent['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 3},
    )

    response = post_queue_reorder(
        test_client,
        [
            {"work_order_id": correction_parent["id"], "queue_position": 1},
            {"work_order_id": main_order["id"], "queue_position": 2},
        ],
        get_queue_revision(test_client),
    )

    assert correction_plan_response.status_code == 200
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [correction_parent["id"], main_order["id"]]


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


def test_assign_plan_reuses_completed_queue_position_and_trails_completed_order(test_client: TestClient) -> None:
    completed = create_work_order(test_client, "Completed queue slot")
    active = create_work_order(test_client, "Active queue slot")
    incoming = create_work_order(test_client, "Incoming queue slot")

    test_client.post(
        f"/manager/work-orders/{completed['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 1},
    )
    test_client.post(
        f"/manager/work-orders/{active['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 2},
    )
    complete_manual_ral_order(test_client, completed["id"])

    response = test_client.post(
        f"/manager/work-orders/{incoming['id']}/plan",
        json={"production_type": "AUTOMATIC", "queue_position": 1},
    )
    planned_response = test_client.get("/manager/work-orders")

    assert response.status_code == 200
    assert planned_response.status_code == 200
    planned_by_id = {item["id"]: item for item in planned_response.json()}
    assert planned_by_id[incoming["id"]]["queue_position"] == 1
    assert planned_by_id[active["id"]]["queue_position"] == 2
    assert planned_by_id[completed["id"]]["queue_position"] == 3
    assert planned_by_id[completed["id"]]["process_status"] == {"value": "READY", "label": "Gotowe"}


def test_assign_plan_after_completed_only_queue_trails_completed_beyond_requested_position(test_client: TestClient) -> None:
    completed = create_work_order(test_client, "Completed only queue slot")
    incoming = create_work_order(test_client, "Incoming after completed only")

    test_client.post(
        f"/manager/work-orders/{completed['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 1},
    )
    complete_manual_ral_order(test_client, completed["id"])

    response = test_client.post(
        f"/manager/work-orders/{incoming['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 2},
    )
    planned_response = test_client.get("/manager/work-orders")

    assert response.status_code == 200
    assert planned_response.status_code == 200
    planned_by_id = {item["id"]: item for item in planned_response.json()}
    assert planned_by_id[incoming["id"]]["queue_position"] == 2
    assert planned_by_id[completed["id"]]["queue_position"] == 3
    assert planned_by_id[completed["id"]]["process_status"] == {"value": "READY", "label": "Gotowe"}


def test_update_queue_position_reuses_completed_queue_position_and_trails_completed_order(test_client: TestClient) -> None:
    completed = create_work_order(test_client, "Completed queue patch slot")
    active = create_work_order(test_client, "Active queue patch slot")

    test_client.post(
        f"/manager/work-orders/{completed['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 1},
    )
    test_client.post(
        f"/manager/work-orders/{active['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 2},
    )
    complete_manual_ral_order(test_client, completed["id"])

    response = test_client.patch(f"/manager/work-orders/{active['id']}/queue-position", json={"queue_position": 1})
    planned_response = test_client.get("/manager/work-orders")

    assert response.status_code == 200
    assert planned_response.status_code == 200
    planned_by_id = {item["id"]: item for item in planned_response.json()}
    assert planned_by_id[active["id"]]["queue_position"] == 1
    assert planned_by_id[completed["id"]]["queue_position"] == 2
    assert planned_by_id[completed["id"]]["process_status"] == {"value": "READY", "label": "Gotowe"}


def test_cannot_directly_move_completed_order_in_active_queue(test_client: TestClient) -> None:
    completed = create_work_order(test_client, "Completed direct queue patch")

    test_client.post(
        f"/manager/work-orders/{completed['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 1},
    )
    complete_manual_ral_order(test_client, completed["id"])

    response = test_client.patch(f"/manager/work-orders/{completed['id']}/queue-position", json={"queue_position": 2})

    assert response.status_code == 409
    assert response.json()["detail"] == "Completed work orders cannot be moved in the active queue."


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


def test_reorder_correction_round_and_normal_orders_preserves_global_queue_positions(test_client: TestClient) -> None:
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
        json={
            "counted_quantity": 100,
            "ok_quantity": 95,
            "correction_quantity": 5,
            "correction_profiles_quantity": 5,
            "correction_accessories_quantity": 0,
            "correction_reason_category": "niedomalowanie",
        },
    )

    correction_plan_response = test_client.post(
        f"/manager/work-orders/{correction_parent['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 3},
    )

    response = post_queue_reorder(
        test_client,
        [
            {"work_order_id": correction_parent["id"], "queue_position": 1},
            {"work_order_id": main_order["id"], "queue_position": 2},
        ],
        get_queue_revision(test_client),
    )

    assert correction_plan_response.status_code == 200
    assert response.status_code == 200
    result_positions = [(item["id"], item["queue_position"]) for item in response.json()]
    correction_item = next(item for item in response.json() if item["id"] == correction_parent["id"])
    main_item = next(item for item in response.json() if item["id"] == main_order["id"])
    assert correction_item["queue_position"] == 1
    assert main_item["queue_position"] == 2
    assert len({item["queue_position"] for item in response.json() if item["queue_position"] is not None}) == len(
        [item for item in response.json() if item["queue_position"] is not None]
    )


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