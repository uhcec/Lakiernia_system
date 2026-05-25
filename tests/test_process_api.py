from fastapi.testclient import TestClient


def build_create_payload(
    *,
    title: str,
    coating_type: str = "RAL",
    total_quantity: int = 100,
) -> dict:
    return {
        "title": title,
        "coating_type": coating_type,
        "total_quantity": total_quantity,
        "customer_name": "ACME",
        "ral_code": "RAL 7016",
        "paint_producer": "AkzoNobel",
        "received_date": "2026-05-25",
        "profiles_to_count": True,
        "accessories_to_count": True,
    }


def advance_to_hanging(test_client: TestClient, work_order_id: int) -> None:
    test_client.post(f"/process/work-orders/{work_order_id}/stages/SURFACE_PREPARATION/start")
    test_client.post(f"/process/work-orders/{work_order_id}/stages/SURFACE_PREPARATION/finish")


def advance_to_production(test_client: TestClient, work_order_id: int) -> None:
    detail = test_client.get(f"/work-orders/{work_order_id}").json()
    advance_to_hanging(test_client, work_order_id)
    if detail["production_type"]["value"] != "MANUAL":
        test_client.post(f"/process/work-orders/{work_order_id}/stages/HANGING/start")


def advance_to_packing(test_client: TestClient, work_order_id: int) -> None:
    advance_to_production(test_client, work_order_id)
    detail = test_client.get(f"/work-orders/{work_order_id}").json()
    if detail["production_type"]["value"] == "MANUAL":
        production_stage = test_client.get("/process/stages/PRODUCTION/work-orders", params={"production_type": detail["production_type"]["value"]}).json()
        production_status = next(item for item in production_stage if item["id"] == work_order_id)["stage_status"]["status"]["value"]
        if production_status == "NOT_STARTED":
            test_client.post(f"/process/work-orders/{work_order_id}/stages/PRODUCTION/start")
        test_client.post(f"/process/work-orders/{work_order_id}/stages/PRODUCTION/finish")
    detail = test_client.get(f"/work-orders/{work_order_id}").json()
    packing_status = next(stage for stage in detail["stage_states"] if stage["stage"]["value"] == "PACKING")["status"]["value"]
    if packing_status == "NOT_STARTED":
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
        json=build_create_payload(title=title, coating_type=coating_type, total_quantity=100),
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
    unplanned = test_client.post("/work-orders", json=build_create_payload(title="Unplanned")).json()

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


def test_manual_skips_hanging_and_goes_directly_to_manual_production(test_client: TestClient) -> None:
    manual = create_planned_work_order(test_client, title="Manual path", queue_position=1, production_type="MANUAL")
    advance_to_hanging(test_client, manual["id"])

    hanging_response = test_client.get("/process/stages/HANGING/work-orders")
    production_response = test_client.get("/process/stages/PRODUCTION/work-orders", params={"production_type": "MANUAL"})

    assert manual["id"] not in [item["id"] for item in hanging_response.json()]
    assert manual["id"] in [item["id"] for item in production_response.json()]


def test_automatic_requires_hanging_before_production_visibility(test_client: TestClient) -> None:
    automatic = create_planned_work_order(test_client, title="Automatic path", queue_position=1, production_type="AUTOMATIC")
    advance_to_hanging(test_client, automatic["id"])

    hanging_response = test_client.get("/process/stages/HANGING/work-orders")
    production_response = test_client.get("/process/stages/PRODUCTION/work-orders", params={"production_type": "AUTOMATIC"})

    assert automatic["id"] in [item["id"] for item in hanging_response.json()]
    assert automatic["id"] not in [item["id"] for item in production_response.json()]


def test_automatic_hanging_start_makes_production_preview_visible(test_client: TestClient) -> None:
    automatic = create_planned_work_order(test_client, title="Automatic auto start", queue_position=1, production_type="AUTOMATIC")
    advance_to_hanging(test_client, automatic["id"])

    response = test_client.post(f"/process/work-orders/{automatic['id']}/stages/HANGING/start")
    production_response = test_client.get("/process/stages/PRODUCTION/work-orders", params={"production_type": "AUTOMATIC"})

    assert response.status_code == 200
    assert automatic["id"] in [item["id"] for item in production_response.json()]
    production_item = next(item for item in production_response.json() if item["id"] == automatic["id"])
    assert production_item["stage_status"] == {
        "stage": "PRODUCTION",
        "status": {"value": "IN_PROGRESS", "label": "W trakcie"},
    }


def test_automatic_hanging_finish_is_rejected(test_client: TestClient) -> None:
    automatic = create_planned_work_order(test_client, title="Automatic hanging blocked", queue_position=1, production_type="AUTOMATIC")
    advance_to_hanging(test_client, automatic["id"])
    test_client.post(f"/process/work-orders/{automatic['id']}/stages/HANGING/start")

    response = test_client.post(f"/process/work-orders/{automatic['id']}/stages/HANGING/finish")

    assert response.status_code == 409
    assert response.json()["detail"] == "Automatic hanging can only start painting. Finish it from PACKING."


def test_automatic_hanging_start_makes_order_visible_in_packing(test_client: TestClient) -> None:
    automatic = create_planned_work_order(test_client, title="Automatic packing visibility", queue_position=1, production_type="AUTOMATIC")
    advance_to_hanging(test_client, automatic["id"])

    test_client.post(f"/process/work-orders/{automatic['id']}/stages/HANGING/start")

    packing_response = test_client.get("/process/stages/PACKING/work-orders")
    production_response = test_client.get("/process/stages/PRODUCTION/work-orders", params={"production_type": "AUTOMATIC"})

    assert packing_response.status_code == 200
    assert automatic["id"] in [item["id"] for item in packing_response.json()]
    packing_item = next(item for item in packing_response.json() if item["id"] == automatic["id"])
    assert packing_item["stage_status"] == {
        "stage": "PACKING",
        "status": {"value": "IN_PROGRESS", "label": "W trakcie"},
    }
    assert automatic["id"] in [item["id"] for item in production_response.json()]


def test_automatic_packing_can_complete_after_hanging_start(test_client: TestClient) -> None:
    automatic = create_planned_work_order(test_client, title="Automatic pack after hanging start", queue_position=1, production_type="AUTOMATIC")
    advance_to_hanging(test_client, automatic["id"])

    test_client.post(f"/process/work-orders/{automatic['id']}/stages/HANGING/start")

    response = test_client.post(
        f"/process/work-orders/{automatic['id']}/packing/complete",
        json={"ok_quantity": 100, "correction_quantity": 0},
    )
    detail = test_client.get(f"/work-orders/{automatic['id']}")

    assert response.status_code == 200
    assert response.json()["stage_status"] == {
        "stage": "PACKING",
        "status": {"value": "DONE", "label": "Zakończone"},
    }
    assert detail.json()["current_active_quantity"] == 0
    assert detail.json()["completed_quantity"] == 100
    assert detail.json()["process_status"] == {"value": "READY", "label": "Gotowe"}


def test_automatic_production_preview_rejects_actions_after_hanging_start(test_client: TestClient) -> None:
    automatic = create_planned_work_order(test_client, title="Automatic preview after hanging start", queue_position=1, production_type="AUTOMATIC")
    advance_to_hanging(test_client, automatic["id"])

    test_client.post(f"/process/work-orders/{automatic['id']}/stages/HANGING/start")

    start_response = test_client.post(f"/process/work-orders/{automatic['id']}/stages/PRODUCTION/start")
    finish_response = test_client.post(f"/process/work-orders/{automatic['id']}/stages/PRODUCTION/finish")

    assert start_response.status_code == 409
    assert finish_response.status_code == 409
    assert start_response.json()["detail"] == "Automatic production is preview-only. Start the process from HANGING and finish it from PACKING."


def test_automatic_production_preview_rejects_direct_start_and_finish(test_client: TestClient) -> None:
    automatic = create_planned_work_order(test_client, title="Automatic preview only", queue_position=1, production_type="AUTOMATIC")
    advance_to_production(test_client, automatic["id"])

    start_response = test_client.post(f"/process/work-orders/{automatic['id']}/stages/PRODUCTION/start")
    finish_response = test_client.post(f"/process/work-orders/{automatic['id']}/stages/PRODUCTION/finish")

    assert start_response.status_code == 409
    assert finish_response.status_code == 409
    assert start_response.json()["detail"] == "Automatic production is preview-only. Start the process from HANGING and finish it from PACKING."


def test_ral_orders_do_not_appear_in_decoral_stage(test_client: TestClient) -> None:
    create_planned_work_order(test_client, title="RAL", queue_position=1, coating_type="RAL")
    decoral = create_planned_work_order(test_client, title="Decoral", queue_position=2, coating_type="DECORAL", production_type="MANUAL")

    test_client.post(f"/process/work-orders/{decoral['id']}/stages/SURFACE_PREPARATION/start")
    test_client.post(f"/process/work-orders/{decoral['id']}/stages/SURFACE_PREPARATION/finish")
    test_client.post(f"/process/work-orders/{decoral['id']}/stages/PRODUCTION/start")
    test_client.post(f"/process/work-orders/{decoral['id']}/stages/PRODUCTION/finish")
    test_client.post(f"/process/work-orders/{decoral['id']}/stages/PACKING/start")
    test_client.post(
        f"/process/work-orders/{decoral['id']}/packing/complete",
        json={"ok_quantity": 100, "correction_quantity": 0},
    )

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


def test_decoral_ok_quantity_goes_to_decoral_production_after_packing(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Decoral packing path", queue_position=1, production_type="MANUAL", coating_type="DECORAL")
    test_client.post(f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/start")
    test_client.post(f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/finish")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/start")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/finish")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PACKING/start")

    response = test_client.post(
        f"/process/work-orders/{created['id']}/packing/complete",
        json={"ok_quantity": 100, "correction_quantity": 0},
    )
    detail = test_client.get(f"/work-orders/{created['id']}")

    assert response.status_code == 200
    assert response.json()["stage_status"] == {
        "stage": "DECORAL_PRODUCTION",
        "status": {"value": "NOT_STARTED", "label": "Nie rozpoczęte"},
    }
    assert detail.json()["process_status"] == {"value": "DECORAL_PRODUCTION", "label": "Produkcja Decoral"}


def test_decoral_production_finish_completes_order(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Decoral complete", queue_position=1, production_type="MANUAL", coating_type="DECORAL")
    test_client.post(f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/start")
    test_client.post(f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/finish")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/start")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/finish")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PACKING/start")
    test_client.post(
        f"/process/work-orders/{created['id']}/packing/complete",
        json={"ok_quantity": 100, "correction_quantity": 0},
    )
    test_client.post(f"/process/work-orders/{created['id']}/stages/DECORAL_PRODUCTION/start")

    response = test_client.post(f"/process/work-orders/{created['id']}/stages/DECORAL_PRODUCTION/finish")
    detail = test_client.get(f"/work-orders/{created['id']}")

    assert response.status_code == 200
    assert detail.json()["process_status"] == {"value": "READY", "label": "Gotowe"}
    assert detail.json()["completed_quantity"] == 100


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


def test_automatic_full_ok_can_finish_from_packing(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Automatic full OK", queue_position=1, production_type="AUTOMATIC")
    advance_to_packing(test_client, created["id"])

    response = test_client.post(
        f"/process/work-orders/{created['id']}/packing/complete",
        json={"ok_quantity": 100, "correction_quantity": 0},
    )
    detail = test_client.get(f"/work-orders/{created['id']}")

    assert response.status_code == 200
    assert response.json()["stage_status"] == {
        "stage": "PACKING",
        "status": {"value": "DONE", "label": "Zakończone"},
    }
    assert detail.json()["current_active_quantity"] == 0
    assert detail.json()["completed_quantity"] == 100
    assert detail.json()["process_status"] == {"value": "READY", "label": "Gotowe"}


def test_manual_and_automatic_corrections_return_to_correct_action_lists(test_client: TestClient) -> None:
    manual = create_planned_work_order(test_client, title="Manual correction", queue_position=1, production_type="MANUAL")
    automatic = create_planned_work_order(test_client, title="Automatic correction", queue_position=2, production_type="AUTOMATIC")
    advance_to_packing(test_client, manual["id"])
    advance_to_packing(test_client, automatic["id"])

    test_client.post(
        f"/process/work-orders/{manual['id']}/packing/complete",
        json={"ok_quantity": 95, "correction_quantity": 5},
    )
    test_client.post(
        f"/process/work-orders/{automatic['id']}/packing/complete",
        json={"ok_quantity": 95, "correction_quantity": 5},
    )

    manual_production = test_client.get("/process/stages/PRODUCTION/work-orders", params={"production_type": "MANUAL"})
    automatic_hanging = test_client.get("/process/stages/HANGING/work-orders")

    assert manual["id"] in [item["id"] for item in manual_production.json()]
    assert automatic["id"] in [item["id"] for item in automatic_hanging.json()]


def test_automatic_correction_batch_can_finish_from_packing(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Automatic correction finish", queue_position=1, production_type="AUTOMATIC")
    advance_to_packing(test_client, created["id"])

    split_response = test_client.post(
        f"/process/work-orders/{created['id']}/packing/complete",
        json={"ok_quantity": 95, "correction_quantity": 5},
    )
    assert split_response.status_code == 200

    detail_after_split = test_client.get(f"/work-orders/{created['id']}").json()
    correction_batch = next(
        batch
        for batch in detail_after_split["batches"]
        if batch["type"]["value"] == "CORRECTION" and batch["is_active"] is True
    )
    batch_id = correction_batch["id"]

    start_response = test_client.post(f"/process/work-orders/{created['id']}/batches/{batch_id}/stages/HANGING/start")
    finish_packing_response = test_client.post(
        f"/process/work-orders/{created['id']}/batches/{batch_id}/packing/complete",
        json={"ok_quantity": 5, "correction_quantity": 0},
    )
    detail = test_client.get(f"/work-orders/{created['id']}")

    assert start_response.status_code == 200
    assert finish_packing_response.status_code == 200
    assert finish_packing_response.json()["stage_status"] == {
        "stage": "PACKING",
        "status": {"value": "DONE", "label": "Zakończone"},
    }
    assert detail.json()["current_active_quantity"] == 0
    assert detail.json()["completed_quantity"] == 100
    assert detail.json()["process_status"] == {"value": "READY", "label": "Gotowe"}


def test_decoral_automatic_mixed_split_is_visible_in_hanging_and_decoral(test_client: TestClient) -> None:
    created = create_planned_work_order(
        test_client,
        title="Decoral automatic split",
        queue_position=1,
        production_type="AUTOMATIC",
        coating_type="DECORAL",
    )
    advance_to_packing(test_client, created["id"])

    response = test_client.post(
        f"/process/work-orders/{created['id']}/packing/complete",
        json={"ok_quantity": 70, "correction_quantity": 30},
    )
    hanging_response = test_client.get("/process/stages/HANGING/work-orders")
    decoral_response = test_client.get("/process/stages/DECORAL_PRODUCTION/work-orders")

    assert response.status_code == 200

    correction_row = next(item for item in hanging_response.json() if item["id"] == created["id"])
    ok_row = next(item for item in decoral_response.json() if item["id"] == created["id"])

    assert correction_row["batch_quantity"] == 30
    assert correction_row["batch_type"] == "CORRECTION"
    assert ok_row["batch_quantity"] == 70
    assert ok_row["batch_type"] == "MAIN"
    assert ok_row["batch_is_partial"] is True


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