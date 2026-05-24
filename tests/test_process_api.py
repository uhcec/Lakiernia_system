from fastapi.testclient import TestClient


def advance_to_hanging(test_client: TestClient, work_order_id: int) -> None:
    test_client.post(f"/process/work-orders/{work_order_id}/stages/SURFACE_PREPARATION/start")
    test_client.post(f"/process/work-orders/{work_order_id}/stages/SURFACE_PREPARATION/finish")


def advance_to_production(test_client: TestClient, work_order_id: int) -> None:
    advance_to_hanging(test_client, work_order_id)
    test_client.post(f"/process/work-orders/{work_order_id}/stages/HANGING/start")
    test_client.post(f"/process/work-orders/{work_order_id}/stages/HANGING/finish")


def advance_to_packing(test_client: TestClient, work_order_id: int) -> None:
    advance_to_production(test_client, work_order_id)
    test_client.post(f"/process/work-orders/{work_order_id}/stages/PRODUCTION/start")
    test_client.post(f"/process/work-orders/{work_order_id}/stages/PRODUCTION/finish")
    test_client.post(f"/process/work-orders/{work_order_id}/stages/PACKING/start")


def create_planned_work_order(
    test_client: TestClient,
    *,
    title: str,
    queue_position: int,
    production_type: str = "MANUAL",
    coating_type: str = "RAL",
) -> dict:
    created = test_client.post(
        "/work-orders",
        json={"title": title, "coating_type": coating_type, "total_quantity": 100},
    ).json()
    test_client.post(
        f"/manager/work-orders/{created['id']}/plan",
        json={"production_type": production_type, "queue_position": queue_position},
    )
    return created


def test_list_stage_work_orders_returns_only_visible_planned_orders(test_client: TestClient) -> None:
    visible = create_planned_work_order(test_client, title="Visible", queue_position=2)
    completed = create_planned_work_order(test_client, title="Completed", queue_position=1)
    test_client.post(f"/process/work-orders/{completed['id']}/stages/SURFACE_PREPARATION/start")
    test_client.post(f"/process/work-orders/{completed['id']}/stages/SURFACE_PREPARATION/finish")
    unplanned = test_client.post("/work-orders", json={"title": "Unplanned", "coating_type": "RAL"}).json()

    response = test_client.get("/process/stages/SURFACE_PREPARATION/work-orders")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [completed["id"], visible["id"]]
    assert response.json()[0]["stage_status"] == {
        "stage": "SURFACE_PREPARATION",
        "status": {"value": "DONE", "label": "Zakończone"},
    }
    assert response.json()[1]["stage_status"] == {
        "stage": "SURFACE_PREPARATION",
        "status": {"value": "NOT_STARTED", "label": "Nie rozpoczęte"},
    }
    assert unplanned["id"] not in [item["id"] for item in response.json()]


def test_list_stage_work_orders_filters_production_by_production_type(test_client: TestClient) -> None:
    manual = create_planned_work_order(test_client, title="Manual", queue_position=2, production_type="MANUAL")
    automatic = create_planned_work_order(test_client, title="Automatic", queue_position=1, production_type="AUTOMATIC")

    advance_to_production(test_client, manual["id"])
    advance_to_production(test_client, automatic["id"])

    response = test_client.get("/process/stages/PRODUCTION/work-orders", params={"production_type": "MANUAL"})

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [manual["id"]]
    assert response.json()[0]["production_type"] == {"value": "MANUAL", "label": "Manualna"}


def test_ral_orders_do_not_appear_in_decoral_stage(test_client: TestClient) -> None:
    create_planned_work_order(test_client, title="RAL", queue_position=1, coating_type="RAL")
    decoral = create_planned_work_order(test_client, title="Decoral", queue_position=2, coating_type="DECORAL")

    advance_to_production(test_client, decoral["id"])
    test_client.post(f"/process/work-orders/{decoral['id']}/stages/PRODUCTION/start")
    test_client.post(f"/process/work-orders/{decoral['id']}/stages/PRODUCTION/finish")

    response = test_client.get("/process/stages/DECORAL_PRODUCTION/work-orders")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [decoral["id"]]
    assert response.json()[0]["coating_type"] == {"value": "DECORAL", "label": "Decoral"}


def test_stage_work_orders_are_sorted_by_queue_position(test_client: TestClient) -> None:
    create_planned_work_order(test_client, title="Third", queue_position=30)
    create_planned_work_order(test_client, title="First", queue_position=10)
    create_planned_work_order(test_client, title="Second", queue_position=20)

    response = test_client.get("/process/stages/SURFACE_PREPARATION/work-orders")

    assert response.status_code == 200
    assert [item["queue_position"] for item in response.json()] == [10, 20, 30]


def test_start_stage_updates_status(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Start me", queue_position=1)

    response = test_client.post(f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/start")

    assert response.status_code == 200
    assert response.json()["stage_status"] == {
        "stage": "SURFACE_PREPARATION",
        "status": {"value": "IN_PROGRESS", "label": "W trakcie"},
    }


def test_finish_stage_updates_status(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Finish me", queue_position=1)
    test_client.post(f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/start")

    response = test_client.post(f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/finish")

    assert response.status_code == 200
    assert response.json()["stage_status"] == {
        "stage": "SURFACE_PREPARATION",
        "status": {"value": "DONE", "label": "Zakończone"},
    }


def test_packing_complete_splits_quantities_and_returns_to_production(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Packing split", queue_position=1)
    advance_to_packing(test_client, created["id"])

    response = test_client.post(
        f"/process/work-orders/{created['id']}/packing/complete",
        json={"ok_quantity": 90, "correction_quantity": 10},
    )

    assert response.status_code == 200
    assert response.json()["stage_status"] == {
        "stage": "PRODUCTION",
        "status": {"value": "NOT_STARTED", "label": "Nie rozpoczęte"},
    }
    assert response.json()["current_active_quantity"] == 10
    assert response.json()["total_quantity"] == 100


def test_packing_finish_endpoint_still_acts_as_full_ok_completion(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Packing compatibility", queue_position=1)
    advance_to_packing(test_client, created["id"])

    response = test_client.post(f"/process/work-orders/{created['id']}/stages/PACKING/finish")
    work_order = test_client.get(f"/work-orders/{created['id']}")

    assert response.status_code == 200
    assert response.json()["stage_status"] == {
        "stage": "PACKING",
        "status": {"value": "DONE", "label": "Zakończone"},
    }
    assert work_order.json()["current_active_quantity"] == 0
    assert work_order.json()["process_status"] == {"value": "READY", "label": "Gotowe"}


def test_fully_packed_order_reopen_returns_clear_validation_error(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Reopen blocked after full pack", queue_position=1)
    advance_to_packing(test_client, created["id"])
    test_client.post(f"/process/work-orders/{created['id']}/stages/PACKING/finish")

    response = test_client.post(f"/process/work-orders/{created['id']}/stages/PACKING/reopen")

    assert response.status_code == 409
    assert response.json()["detail"] == "Cannot reopen process stages because the work order has no active quantity remaining."


def test_order_with_correction_active_batch_can_still_reopen_stage(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Correction still active", queue_position=1)
    advance_to_packing(test_client, created["id"])
    test_client.post(
        f"/process/work-orders/{created['id']}/packing/complete",
        json={"ok_quantity": 90, "correction_quantity": 10},
    )
    test_client.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/start")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/finish")

    response = test_client.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/reopen")

    assert response.status_code == 200
    assert response.json()["stage_status"] == {
        "stage": "PRODUCTION",
        "status": {"value": "IN_PROGRESS", "label": "W trakcie"},
    }


def test_packing_complete_rejects_invalid_quantity_sum(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Packing invalid", queue_position=1)
    advance_to_packing(test_client, created["id"])

    response = test_client.post(
        f"/process/work-orders/{created['id']}/packing/complete",
        json={"ok_quantity": 60, "correction_quantity": 50},
    )

    assert response.status_code == 409


def test_reopen_stage_moves_done_back_to_in_progress(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Reopen me", queue_position=1)
    test_client.post(f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/start")
    test_client.post(f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/finish")

    response = test_client.post(f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/reopen")

    assert response.status_code == 200
    assert response.json()["stage_status"] == {
        "stage": "SURFACE_PREPARATION",
        "status": {"value": "IN_PROGRESS", "label": "W trakcie"},
    }


def test_cannot_start_if_previous_stage_not_done(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Blocked start", queue_position=1)

    response = test_client.post(f"/process/work-orders/{created['id']}/stages/HANGING/start")

    assert response.status_code == 409


def test_cannot_finish_if_not_started(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Blocked finish", queue_position=1)

    response = test_client.post(f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/finish")

    assert response.status_code == 409