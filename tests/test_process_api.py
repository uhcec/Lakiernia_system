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


def start_surface_preparation(
    test_client: TestClient,
    work_order_id: int,
    *,
    counted_quantity: int | None = None,
):
    if counted_quantity is None:
        detail = test_client.get(f"/work-orders/{work_order_id}").json()
        counted_quantity = detail["current_active_quantity"]

    return test_client.post(
        f"/process/work-orders/{work_order_id}/stages/SURFACE_PREPARATION/start",
        json={"counted_quantity": counted_quantity},
    )


def complete_packing_request(
    test_client: TestClient,
    work_order_id: int,
    *,
    counted_quantity: int,
    ok_quantity: int,
    correction_quantity: int,
    batch_id: int | None = None,
):
    path = (
        f"/process/work-orders/{work_order_id}/batches/{batch_id}/packing/complete"
        if batch_id is not None
        else f"/process/work-orders/{work_order_id}/packing/complete"
    )
    return test_client.post(
        path,
        json={
            "counted_quantity": counted_quantity,
            "ok_quantity": ok_quantity,
            "correction_quantity": correction_quantity,
        },
    )


def advance_to_hanging(test_client: TestClient, work_order_id: int) -> None:
    detail = test_client.get(f"/work-orders/{work_order_id}").json()
    if detail["is_correction"]:
        if detail["production_type"]["value"] == "AUTOMATIC":
            test_client.post(f"/process/work-orders/{work_order_id}/stages/HANGING/start")
        return

    start_surface_preparation(test_client, work_order_id)
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
        production_stage = test_client.get(
            "/process/stages/PRODUCTION/work-orders",
            params={
                "production_type": detail["production_type"]["value"],
                "queue_namespace": detail["queue_namespace"]["value"],
            },
        ).json()
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
    total_quantity: int = 100,
) -> dict:
    created = test_client.post(
        "/work-orders",
        json=build_create_payload(title=title, coating_type=coating_type, total_quantity=total_quantity),
    ).json()
    test_client.post(
        f"/manager/work-orders/{created['id']}/plan",
        json={"production_type": production_type, "queue_position": queue_position},
    )
    return created


def test_list_stage_work_orders_returns_only_visible_planned_orders(test_client: TestClient) -> None:
    visible = create_planned_work_order(test_client, title="Visible", queue_position=2)
    completed = create_planned_work_order(test_client, title="Completed", queue_position=1)
    start_surface_preparation(test_client, completed["id"])
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


# docs/WORKFLOW.md scenario S02 (RAL + AUTOMATIC + none)
def test_automatic_packing_can_complete_after_hanging_start(test_client: TestClient) -> None:
    automatic = create_planned_work_order(test_client, title="Automatic pack after hanging start", queue_position=1, production_type="AUTOMATIC")
    advance_to_hanging(test_client, automatic["id"])

    test_client.post(f"/process/work-orders/{automatic['id']}/stages/HANGING/start")

    response = complete_packing_request(test_client, automatic["id"], counted_quantity=100, ok_quantity=100, correction_quantity=0)
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

    start_surface_preparation(test_client, decoral["id"])
    test_client.post(f"/process/work-orders/{decoral['id']}/stages/SURFACE_PREPARATION/finish")
    test_client.post(f"/process/work-orders/{decoral['id']}/stages/PRODUCTION/start")
    test_client.post(f"/process/work-orders/{decoral['id']}/stages/PRODUCTION/finish")
    test_client.post(f"/process/work-orders/{decoral['id']}/stages/PACKING/start")
    complete_packing_request(test_client, decoral["id"], counted_quantity=100, ok_quantity=100, correction_quantity=0)

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

    response = start_surface_preparation(test_client, created["id"])

    assert response.status_code == 200
    assert response.json()["stage_status"] == {
        "stage": "SURFACE_PREPARATION",
        "status": {"value": "IN_PROGRESS", "label": "W trakcie"},
    }
    assert response.json()["planned_quantity"] == 100
    assert response.json()["counted_quantity"] == 100
    assert response.json()["quantity_difference"] == 0


def test_cannot_start_surface_preparation_without_counted_quantity(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Missing counted", queue_position=1)

    response = test_client.post(f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/start")

    assert response.status_code == 409
    assert response.json()["detail"] == "Counted quantity is required to start surface preparation."


def test_start_surface_preparation_returns_difference_and_persists_count(test_client: TestClient) -> None:
    created = test_client.post(
        "/work-orders",
        json=build_create_payload(title="Count diff", total_quantity=10),
    ).json()
    test_client.post(
        f"/manager/work-orders/{created['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 1},
    )

    response = start_surface_preparation(test_client, created["id"], counted_quantity=6)
    stage_response = test_client.get("/process/stages/SURFACE_PREPARATION/work-orders")

    assert response.status_code == 200
    assert response.json()["planned_quantity"] == 10
    assert response.json()["counted_quantity"] == 6
    assert response.json()["quantity_difference"] == -4

    stage_item = next(item for item in stage_response.json() if item["id"] == created["id"])
    assert stage_item["counted_quantity"] == 6
    assert stage_item["quantity_difference"] == -4


def test_packing_uses_surface_preparation_actual_quantity_and_preserves_difference(test_client: TestClient) -> None:
    created = create_planned_work_order(
        test_client,
        title="Packing uses actual quantity",
        queue_position=1,
        production_type="MANUAL",
        total_quantity=100,
    )

    start_surface_preparation(test_client, created["id"], counted_quantity=95)
    test_client.post(f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/finish")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/start")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/finish")

    packing_start_response = test_client.post(f"/process/work-orders/{created['id']}/stages/PACKING/start")
    packing_rows_response = test_client.get("/process/stages/PACKING/work-orders")
    packing_complete_response = complete_packing_request(
        test_client,
        created["id"],
        counted_quantity=95,
        ok_quantity=90,
        correction_quantity=5,
    )
    unplanned_response = test_client.get("/manager/work-orders/unplanned")

    assert packing_start_response.status_code == 200
    assert packing_start_response.json()["planned_quantity"] == 100
    assert packing_start_response.json()["counted_quantity"] == 95
    assert packing_start_response.json()["quantity_difference"] == -5
    packing_item = next(item for item in packing_rows_response.json() if item["id"] == created["id"])
    assert packing_item["planned_quantity"] == 100
    assert packing_item["counted_quantity"] == 95
    assert packing_item["quantity_difference"] == -5
    assert packing_complete_response.status_code == 200
    correction_order = next(item for item in unplanned_response.json() if item["parent_order"]["id"] == created["id"])
    assert correction_order["total_quantity"] == 5


def test_packing_rejects_quantity_above_surface_preparation_actual_quantity(test_client: TestClient) -> None:
    created = create_planned_work_order(
        test_client,
        title="Packing rejects stale expected quantity",
        queue_position=1,
        production_type="MANUAL",
        total_quantity=100,
    )

    start_surface_preparation(test_client, created["id"], counted_quantity=95)
    test_client.post(f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/finish")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/start")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/finish")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PACKING/start")

    response = complete_packing_request(
        test_client,
        created["id"],
        counted_quantity=100,
        ok_quantity=95,
        correction_quantity=5,
    )

    assert response.status_code == 409


def test_second_automatic_hanging_start_is_rejected_when_line_is_busy(test_client: TestClient) -> None:
    first = create_planned_work_order(
        test_client,
        title="Automatic line first",
        queue_position=1,
        production_type="AUTOMATIC",
    )
    second = create_planned_work_order(
        test_client,
        title="Automatic line second",
        queue_position=2,
        production_type="AUTOMATIC",
    )

    advance_to_hanging(test_client, first["id"])
    advance_to_hanging(test_client, second["id"])

    first_start_response = test_client.post(f"/process/work-orders/{first['id']}/stages/HANGING/start")
    second_start_response = test_client.post(f"/process/work-orders/{second['id']}/stages/HANGING/start")

    assert first_start_response.status_code == 200
    assert second_start_response.status_code == 409
    assert second_start_response.json()["detail"] == "Automatic line is already occupied by another active job."


def test_cannot_start_surface_preparation_with_non_positive_count(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Bad counted", queue_position=1)

    response = start_surface_preparation(test_client, created["id"], counted_quantity=0)

    assert response.status_code == 409
    assert response.json()["detail"] == "Counted quantity must be greater than zero."


def test_finish_stage_updates_status(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Finish me", queue_position=1)
    start_surface_preparation(test_client, created["id"])

    response = test_client.post(f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/finish")

    assert response.status_code == 200
    assert response.json()["stage_status"] == {
        "stage": "SURFACE_PREPARATION",
        "status": {"value": "DONE", "label": "Zakończone"},
    }


def test_packing_complete_splits_quantities_and_marks_parent_waiting_for_corrections(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Packing split", queue_position=1)
    advance_to_packing(test_client, created["id"])

    response = complete_packing_request(test_client, created["id"], counted_quantity=100, ok_quantity=90, correction_quantity=10)
    detail = test_client.get(f"/work-orders/{created['id']}")
    work_orders = test_client.get("/work-orders")
    correction_order = next(item for item in work_orders.json()["items"] if item["is_correction"] is True)

    assert response.status_code == 200
    assert response.json()["stage_status"] == {
        "stage": "PACKING",
        "status": {"value": "DONE", "label": "Zakończone"},
    }
    assert detail.json()["total_quantity"] == 100
    assert detail.json()["completed_quantity"] == 0
    assert detail.json()["current_active_quantity"] == 0
    assert detail.json()["waiting_ok_quantity"] == 90
    assert detail.json()["pending_correction_quantity"] == 10
    assert detail.json()["total_progress_quantity"] == 90
    assert detail.json()["process_status"] == {"value": "WAITING_FOR_CORRECTIONS", "label": "Czeka na poprawki"}
    assert correction_order["total_quantity"] == 10
    assert correction_order["parent_order"]["id"] == created["id"]
    assert correction_order["process_status"] == {"value": "TO_BE_PLANNED", "label": "Do zaplanowania"}


def test_decoral_ok_quantity_goes_to_decoral_production_after_packing(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Decoral packing path", queue_position=1, production_type="MANUAL", coating_type="DECORAL")
    start_surface_preparation(test_client, created["id"])
    test_client.post(f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/finish")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/start")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/finish")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PACKING/start")

    response = complete_packing_request(test_client, created["id"], counted_quantity=100, ok_quantity=100, correction_quantity=0)
    detail = test_client.get(f"/work-orders/{created['id']}")

    assert response.status_code == 200
    assert response.json()["stage_status"] == {
        "stage": "DECORAL_PRODUCTION",
        "status": {"value": "NOT_STARTED", "label": "Nie rozpoczęte"},
    }
    assert detail.json()["process_status"] == {"value": "DECORAL_PRODUCTION", "label": "Produkcja Decoral"}


def test_decoral_production_finish_completes_order(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Decoral complete", queue_position=1, production_type="MANUAL", coating_type="DECORAL")
    start_surface_preparation(test_client, created["id"])
    test_client.post(f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/finish")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/start")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/finish")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PACKING/start")
    complete_packing_request(test_client, created["id"], counted_quantity=100, ok_quantity=100, correction_quantity=0)
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

    response = complete_packing_request(test_client, created["id"], counted_quantity=100, ok_quantity=100, correction_quantity=0)
    detail = test_client.get(f"/work-orders/{created['id']}")

    assert response.status_code == 200
    assert response.json()["stage_status"] == {
        "stage": "PACKING",
        "status": {"value": "DONE", "label": "Zakończone"},
    }
    assert detail.json()["current_active_quantity"] == 0
    assert detail.json()["completed_quantity"] == 100
    assert detail.json()["process_status"] == {"value": "READY", "label": "Gotowe"}


def test_manual_and_automatic_corrections_create_new_unplanned_orders(test_client: TestClient) -> None:
    manual = create_planned_work_order(test_client, title="Manual correction", queue_position=1, production_type="MANUAL")
    automatic = create_planned_work_order(test_client, title="Automatic correction", queue_position=2, production_type="AUTOMATIC")
    advance_to_packing(test_client, manual["id"])
    advance_to_packing(test_client, automatic["id"])

    complete_packing_request(test_client, manual["id"], counted_quantity=100, ok_quantity=95, correction_quantity=5)
    complete_packing_request(test_client, automatic["id"], counted_quantity=100, ok_quantity=95, correction_quantity=5)

    manual_production = test_client.get("/process/stages/PRODUCTION/work-orders", params={"production_type": "MANUAL"})
    automatic_hanging = test_client.get("/process/stages/HANGING/work-orders")
    unplanned_response = test_client.get("/manager/work-orders/unplanned")

    assert manual["id"] not in [item["id"] for item in manual_production.json()]
    assert automatic["id"] not in [item["id"] for item in automatic_hanging.json()]
    correction_orders = [item for item in unplanned_response.json() if item["is_correction"] is True]
    assert len(correction_orders) == 2
    assert {item["parent_order"]["id"] for item in correction_orders} == {manual["id"], automatic["id"]}


def test_correction_order_can_be_planned_after_packing_split(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Correction planning", queue_position=1, production_type="AUTOMATIC")
    advance_to_packing(test_client, created["id"])

    split_response = complete_packing_request(test_client, created["id"], counted_quantity=100, ok_quantity=95, correction_quantity=5)
    assert split_response.status_code == 200

    correction_order = next(
        item
        for item in test_client.get("/manager/work-orders/unplanned").json()
        if item["parent_order"]["id"] == created["id"]
    )
    plan_response = test_client.post(
        f"/manager/work-orders/{correction_order['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 3},
    )
    detail = test_client.get(f"/work-orders/{correction_order['id']}")

    assert plan_response.status_code == 200
    assert detail.json()["total_quantity"] == 5
    assert detail.json()["process_status"] == {"value": "PRODUCTION_MANUAL", "label": "Produkcja ręczna"}


def test_stage_list_can_filter_by_queue_namespace(test_client: TestClient) -> None:
    main = create_planned_work_order(test_client, title="Main production list", queue_position=1, production_type="MANUAL")
    advance_to_hanging(test_client, main["id"])

    parent = create_planned_work_order(test_client, title="Correction source", queue_position=2, production_type="MANUAL")
    advance_to_packing(test_client, parent["id"])
    complete_packing_request(test_client, parent["id"], counted_quantity=100, ok_quantity=95, correction_quantity=5)
    correction_order = next(
        item
        for item in test_client.get("/manager/work-orders/unplanned").json()
        if item["parent_order"]["id"] == parent["id"]
    )
    test_client.post(
        f"/manager/work-orders/{correction_order['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 3},
    )

    main_response = test_client.get("/process/stages/PRODUCTION/work-orders", params={"production_type": "MANUAL"})
    corrections_response = test_client.get(
        "/process/stages/PRODUCTION/work-orders",
        params={"production_type": "MANUAL", "queue_namespace": "CORRECTIONS"},
    )

    assert main_response.status_code == 200
    assert corrections_response.status_code == 200
    assert [item["id"] for item in main_response.json()] == [main["id"], correction_order["id"]]
    assert [item["id"] for item in corrections_response.json()] == [correction_order["id"]]


def test_decoral_automatic_mixed_split_waits_for_correction_child(test_client: TestClient) -> None:
    created = create_planned_work_order(
        test_client,
        title="Decoral automatic split",
        queue_position=1,
        production_type="AUTOMATIC",
        coating_type="DECORAL",
    )
    advance_to_packing(test_client, created["id"])

    response = complete_packing_request(test_client, created["id"], counted_quantity=100, ok_quantity=70, correction_quantity=30)
    hanging_response = test_client.get("/process/stages/HANGING/work-orders")
    decoral_response = test_client.get("/process/stages/DECORAL_PRODUCTION/work-orders")
    unplanned_response = test_client.get("/manager/work-orders/unplanned")
    detail = test_client.get(f"/work-orders/{created['id']}")

    assert response.status_code == 200
    correction_order = next(item for item in unplanned_response.json() if item["parent_order"]["id"] == created["id"])

    assert hanging_response.json() == []
    assert [item["id"] for item in decoral_response.json()] == [created["id"]]
    assert decoral_response.json()[0]["batch_quantity"] == 70
    assert detail.json()["process_status"] == {"value": "DECORAL_PRODUCTION", "label": "Produkcja Decoral"}
    assert detail.json()["waiting_ok_quantity"] == 70
    assert correction_order["total_quantity"] == 30


def test_decoral_correction_child_plans_back_to_painting_flow_via_api(test_client: TestClient) -> None:
    created = create_planned_work_order(
        test_client,
        title="Decoral correction return",
        queue_position=1,
        production_type="MANUAL",
        coating_type="DECORAL",
        total_quantity=10,
    )
    advance_to_packing(test_client, created["id"])

    split_response = complete_packing_request(
        test_client,
        created["id"],
        counted_quantity=10,
        ok_quantity=7,
        correction_quantity=3,
    )
    parent_detail = test_client.get(f"/work-orders/{created['id']}")
    correction_order = next(
        item
        for item in test_client.get("/manager/work-orders/unplanned").json()
        if item["parent_order"]["id"] == created["id"]
    )

    assert split_response.status_code == 200
    assert split_response.json()["stage_status"] == {
        "stage": "DECORAL_PRODUCTION",
        "status": {"value": "NOT_STARTED", "label": "Nie rozpoczęte"},
    }
    assert parent_detail.json()["process_status"] == {"value": "DECORAL_PRODUCTION", "label": "Produkcja Decoral"}

    plan_response = test_client.post(
        f"/manager/work-orders/{correction_order['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 2},
    )
    correction_detail = test_client.get(f"/work-orders/{correction_order['id']}")

    assert plan_response.status_code == 200
    assert correction_detail.json()["process_status"] == {"value": "PRODUCTION_MANUAL", "label": "Produkcja ręczna"}


def test_completed_correction_child_marks_parent_ready_via_api(test_client: TestClient) -> None:
    created = create_planned_work_order(
        test_client,
        title="Correction merge API",
        queue_position=1,
        production_type="MANUAL",
        total_quantity=10,
    )
    advance_to_packing(test_client, created["id"])

    split_response = complete_packing_request(test_client, created["id"], counted_quantity=10, ok_quantity=7, correction_quantity=3)
    assert split_response.status_code == 200

    correction_order = next(
        item
        for item in test_client.get("/manager/work-orders/unplanned").json()
        if item["parent_order"]["id"] == created["id"]
    )
    plan_response = test_client.post(
        f"/manager/work-orders/{correction_order['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 2},
    )
    assert plan_response.status_code == 200

    test_client.post(f"/process/work-orders/{correction_order['id']}/stages/PRODUCTION/start")
    test_client.post(f"/process/work-orders/{correction_order['id']}/stages/PRODUCTION/finish")
    test_client.post(f"/process/work-orders/{correction_order['id']}/stages/PACKING/start")
    child_complete = complete_packing_request(
        test_client,
        correction_order["id"],
        counted_quantity=3,
        ok_quantity=3,
        correction_quantity=0,
    )
    parent_detail = test_client.get(f"/work-orders/{created['id']}")
    child_detail = test_client.get(f"/work-orders/{correction_order['id']}")

    assert child_complete.status_code == 200
    assert parent_detail.json()["process_status"] == {"value": "READY", "label": "Gotowe"}
    assert parent_detail.json()["completed_quantity"] == 10
    assert any(item["id"] == correction_order["id"] for item in parent_detail.json()["correction_orders"])
    assert child_detail.json()["parent_order"]["id"] == created["id"]


def test_multi_round_correction_chain_marks_original_parent_ready_via_api(test_client: TestClient) -> None:
    created = create_planned_work_order(
        test_client,
        title="Multi-round correction API",
        queue_position=1,
        production_type="MANUAL",
        total_quantity=10,
    )
    advance_to_packing(test_client, created["id"])

    first_split = complete_packing_request(
        test_client,
        created["id"],
        counted_quantity=10,
        ok_quantity=7,
        correction_quantity=3,
    )
    assert first_split.status_code == 200

    first_correction = next(
        item
        for item in test_client.get("/manager/work-orders/unplanned").json()
        if item["parent_order"]["id"] == created["id"]
    )
    first_plan = test_client.post(
        f"/manager/work-orders/{first_correction['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 2},
    )
    assert first_plan.status_code == 200

    advance_to_packing(test_client, first_correction["id"])
    second_split = complete_packing_request(
        test_client,
        first_correction["id"],
        counted_quantity=3,
        ok_quantity=2,
        correction_quantity=1,
    )
    assert second_split.status_code == 200

    second_correction = next(
        item
        for item in test_client.get("/manager/work-orders/unplanned").json()
        if item["parent_order"]["id"] == first_correction["id"]
    )
    second_plan = test_client.post(
        f"/manager/work-orders/{second_correction['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 3},
    )
    assert second_plan.status_code == 200

    advance_to_packing(test_client, second_correction["id"])
    final_complete = complete_packing_request(
        test_client,
        second_correction["id"],
        counted_quantity=1,
        ok_quantity=1,
        correction_quantity=0,
    )

    parent_detail = test_client.get(f"/work-orders/{created['id']}")
    first_child_detail = test_client.get(f"/work-orders/{first_correction['id']}")
    second_child_detail = test_client.get(f"/work-orders/{second_correction['id']}")

    assert final_complete.status_code == 200
    assert parent_detail.json()["process_status"] == {"value": "READY", "label": "Gotowe"}
    assert parent_detail.json()["status"] == {"value": "FINISHED", "label": "Skończone"}
    assert parent_detail.json()["completed_quantity"] == 10
    assert first_child_detail.json()["process_status"] == {"value": "READY", "label": "Gotowe"}
    assert first_child_detail.json()["completed_quantity"] == 3
    assert second_child_detail.json()["process_status"] == {"value": "READY", "label": "Gotowe"}
    assert second_child_detail.json()["completed_quantity"] == 1


# docs/WORKFLOW.md scenario S06 (RAL + AUTOMATIC + correction after packing)
def test_automatic_correction_child_can_complete_and_merge_parent_via_api(test_client: TestClient) -> None:
    created = create_planned_work_order(
        test_client,
        title="Automatic correction merge API",
        queue_position=1,
        production_type="AUTOMATIC",
        total_quantity=10,
    )
    advance_to_packing(test_client, created["id"])

    split_response = complete_packing_request(
        test_client,
        created["id"],
        counted_quantity=10,
        ok_quantity=8,
        correction_quantity=2,
    )
    assert split_response.status_code == 200

    correction_order = next(
        item
        for item in test_client.get("/manager/work-orders/unplanned").json()
        if item["parent_order"]["id"] == created["id"]
    )
    plan_response = test_client.post(
        f"/manager/work-orders/{correction_order['id']}/plan",
        json={"production_type": "AUTOMATIC", "queue_position": 2},
    )
    assert plan_response.status_code == 200

    advance_to_packing(test_client, correction_order["id"])
    child_complete = complete_packing_request(
        test_client,
        correction_order["id"],
        counted_quantity=2,
        ok_quantity=2,
        correction_quantity=0,
    )
    parent_detail = test_client.get(f"/work-orders/{created['id']}")
    child_detail = test_client.get(f"/work-orders/{correction_order['id']}")

    assert child_complete.status_code == 200
    assert parent_detail.json()["process_status"] == {"value": "READY", "label": "Gotowe"}
    assert parent_detail.json()["status"] == {"value": "FINISHED", "label": "Skończone"}
    assert parent_detail.json()["completed_quantity"] == 10
    assert child_detail.json()["process_status"] == {"value": "READY", "label": "Gotowe"}
    assert child_detail.json()["completed_quantity"] == 2


def test_fully_packed_order_reopen_returns_clear_validation_error(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Reopen blocked after full pack", queue_position=1)
    advance_to_packing(test_client, created["id"])
    test_client.post(f"/process/work-orders/{created['id']}/stages/PACKING/finish")

    response = test_client.post(f"/process/work-orders/{created['id']}/stages/PACKING/reopen")

    assert response.status_code == 409
    assert response.json()["detail"] == "Cannot reopen process stages because the work order has no active quantity remaining."


def test_original_order_cannot_reopen_production_after_correction_split(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Correction split done", queue_position=1)
    advance_to_packing(test_client, created["id"])
    complete_packing_request(test_client, created["id"], counted_quantity=100, ok_quantity=90, correction_quantity=10)

    response = test_client.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/reopen")

    assert response.status_code == 409
    assert response.json()["detail"] == "Cannot reopen process stages because the work order has no active quantity remaining."


def test_duplicate_packing_completion_returns_controlled_success_without_second_child(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="API duplicate packing completion", queue_position=1)
    advance_to_packing(test_client, created["id"])

    first_response = complete_packing_request(
        test_client,
        created["id"],
        counted_quantity=100,
        ok_quantity=90,
        correction_quantity=10,
    )
    second_response = complete_packing_request(
        test_client,
        created["id"],
        counted_quantity=100,
        ok_quantity=90,
        correction_quantity=10,
    )
    detail = test_client.get(f"/work-orders/{created['id']}")
    correction_orders = [
        item
        for item in test_client.get("/manager/work-orders/unplanned").json()
        if item["parent_order"]["id"] == created["id"]
    ]

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert detail.json()["completed_quantity"] == 0
    assert detail.json()["current_active_quantity"] == 0
    assert len(correction_orders) == 1


def test_duplicate_decoral_stage_finish_returns_controlled_success_without_double_counting(test_client: TestClient) -> None:
    created = create_planned_work_order(
        test_client,
        title="API duplicate decoral finish",
        queue_position=1,
        production_type="MANUAL",
        coating_type="DECORAL",
        total_quantity=10,
    )
    advance_to_packing(test_client, created["id"])
    complete_packing_request(
        test_client,
        created["id"],
        counted_quantity=10,
        ok_quantity=10,
        correction_quantity=0,
    )

    start_response = test_client.post(f"/process/work-orders/{created['id']}/stages/DECORAL_PRODUCTION/start")
    first_response = test_client.post(f"/process/work-orders/{created['id']}/stages/DECORAL_PRODUCTION/finish")
    second_response = test_client.post(f"/process/work-orders/{created['id']}/stages/DECORAL_PRODUCTION/finish")
    detail = test_client.get(f"/work-orders/{created['id']}")

    assert start_response.status_code == 200
    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert detail.json()["completed_quantity"] == 10
    assert detail.json()["current_active_quantity"] == 0
    assert detail.json()["process_status"] == {"value": "READY", "label": "Gotowe"}


def test_reopen_finished_decoral_tracked_batch_returns_409_and_leaves_quantities_unchanged(test_client: TestClient) -> None:
    created = create_planned_work_order(
        test_client,
        title="API reject reopen finished decoral batch",
        queue_position=1,
        production_type="MANUAL",
        coating_type="DECORAL",
        total_quantity=10,
    )
    advance_to_packing(test_client, created["id"])
    split_response = complete_packing_request(
        test_client,
        created["id"],
        counted_quantity=10,
        ok_quantity=7,
        correction_quantity=3,
    )

    assert split_response.status_code == 200

    batch_id = split_response.json()["batch_id"]
    test_client.post(f"/process/work-orders/{created['id']}/batches/{batch_id}/stages/DECORAL_PRODUCTION/start")
    test_client.post(f"/process/work-orders/{created['id']}/batches/{batch_id}/stages/DECORAL_PRODUCTION/finish")

    before_parent = test_client.get(f"/work-orders/{created['id']}").json()
    correction_order = next(
        item
        for item in test_client.get("/manager/work-orders/unplanned").json()
        if item["parent_order"]["id"] == created["id"]
    )

    response = test_client.post(
        f"/process/work-orders/{created['id']}/batches/{batch_id}/stages/DECORAL_PRODUCTION/reopen"
    )

    after_parent = test_client.get(f"/work-orders/{created['id']}").json()
    after_correction = test_client.get(f"/work-orders/{correction_order['id']}").json()

    assert response.status_code == 409
    assert response.json()["detail"] == "Finished tracked batches cannot be reopened."
    assert after_parent["completed_quantity"] == before_parent["completed_quantity"] == 7
    assert after_parent["current_active_quantity"] == before_parent["current_active_quantity"] == 0
    assert after_parent["process_status"] == before_parent["process_status"]
    assert after_correction["parent_order"]["id"] == created["id"]


def test_reopen_finished_correction_child_tracked_batch_returns_409_and_parent_ready_unchanged(test_client: TestClient) -> None:
    created = create_planned_work_order(
        test_client,
        title="API reject reopen finished correction child batch",
        queue_position=1,
        production_type="MANUAL",
        coating_type="DECORAL",
        total_quantity=10,
    )
    advance_to_packing(test_client, created["id"])
    root_split = complete_packing_request(
        test_client,
        created["id"],
        counted_quantity=10,
        ok_quantity=7,
        correction_quantity=3,
    )
    assert root_split.status_code == 200

    first_correction = next(
        item
        for item in test_client.get("/manager/work-orders/unplanned").json()
        if item["parent_order"]["id"] == created["id"]
    )
    plan_first = test_client.post(
        f"/manager/work-orders/{first_correction['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 2},
    )
    assert plan_first.status_code == 200

    root_batch_id = root_split.json()["batch_id"]
    test_client.post(f"/process/work-orders/{created['id']}/batches/{root_batch_id}/stages/DECORAL_PRODUCTION/start")
    test_client.post(f"/process/work-orders/{created['id']}/batches/{root_batch_id}/stages/DECORAL_PRODUCTION/finish")

    advance_to_packing(test_client, first_correction["id"])
    child_split = complete_packing_request(
        test_client,
        first_correction["id"],
        counted_quantity=3,
        ok_quantity=2,
        correction_quantity=1,
    )
    assert child_split.status_code == 200

    second_correction = next(
        item
        for item in test_client.get("/manager/work-orders/unplanned").json()
        if item["parent_order"]["id"] == first_correction["id"]
    )
    plan_second = test_client.post(
        f"/manager/work-orders/{second_correction['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 3},
    )
    assert plan_second.status_code == 200

    child_batch_id = child_split.json()["batch_id"]
    test_client.post(f"/process/work-orders/{first_correction['id']}/batches/{child_batch_id}/stages/DECORAL_PRODUCTION/start")
    test_client.post(f"/process/work-orders/{first_correction['id']}/batches/{child_batch_id}/stages/DECORAL_PRODUCTION/finish")

    advance_to_packing(test_client, second_correction["id"])
    leaf_complete = complete_packing_request(
        test_client,
        second_correction["id"],
        counted_quantity=1,
        ok_quantity=1,
        correction_quantity=0,
    )
    assert leaf_complete.status_code == 200
    test_client.post(f"/process/work-orders/{second_correction['id']}/stages/DECORAL_PRODUCTION/start")
    test_client.post(f"/process/work-orders/{second_correction['id']}/stages/DECORAL_PRODUCTION/finish")

    before_parent = test_client.get(f"/work-orders/{created['id']}").json()
    before_child = test_client.get(f"/work-orders/{first_correction['id']}").json()

    response = test_client.post(
        f"/process/work-orders/{first_correction['id']}/batches/{child_batch_id}/stages/DECORAL_PRODUCTION/reopen"
    )

    after_parent = test_client.get(f"/work-orders/{created['id']}").json()
    after_child = test_client.get(f"/work-orders/{first_correction['id']}").json()

    assert response.status_code == 409
    assert response.json()["detail"] == "Finished tracked batches cannot be reopened."
    assert before_parent["process_status"] == {"value": "READY", "label": "Gotowe"}
    assert after_parent["process_status"] == before_parent["process_status"]
    assert after_parent["completed_quantity"] == before_parent["completed_quantity"] == 10
    assert after_parent["current_active_quantity"] == before_parent["current_active_quantity"] == 0
    assert after_child["completed_quantity"] == before_child["completed_quantity"]
    assert after_child["current_active_quantity"] == before_child["current_active_quantity"]


def test_packing_complete_rejects_invalid_quantity_sum(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Packing invalid", queue_position=1)
    advance_to_packing(test_client, created["id"])

    response = complete_packing_request(test_client, created["id"], counted_quantity=100, ok_quantity=60, correction_quantity=50)

    assert response.status_code == 409


def test_packing_complete_requires_counted_quantity(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Packing missing counted", queue_position=1)
    advance_to_packing(test_client, created["id"])

    response = test_client.post(
        f"/process/work-orders/{created['id']}/packing/complete",
        json={"ok_quantity": 100, "correction_quantity": 0},
    )

    assert response.status_code == 422


def test_packing_complete_rejects_when_split_does_not_match_counted_quantity(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Packing counted mismatch", queue_position=1)
    advance_to_packing(test_client, created["id"])

    response = complete_packing_request(test_client, created["id"], counted_quantity=96, ok_quantity=90, correction_quantity=5)

    assert response.status_code == 409
    assert response.json()["detail"] == "Packing quantities must add up to the counted quantity."


def test_packing_complete_rejects_when_counted_quantity_is_lower_than_planned(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Packing counted low", queue_position=1)
    advance_to_packing(test_client, created["id"])

    response = complete_packing_request(test_client, created["id"], counted_quantity=96, ok_quantity=90, correction_quantity=6)
    detail = test_client.get(f"/work-orders/{created['id']}")

    assert response.status_code == 409
    assert response.json()["detail"] == "Policzona ilość musi odpowiadać rzeczywistej ilości z przygotowania powierzchni."
    assert detail.json()["current_active_quantity"] == 100
    assert detail.json()["correction_orders"] == []


def test_packing_complete_rejects_when_counted_quantity_is_higher_than_planned(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Packing counted high", queue_position=1)
    advance_to_packing(test_client, created["id"])

    response = complete_packing_request(test_client, created["id"], counted_quantity=104, ok_quantity=100, correction_quantity=4)

    assert response.status_code == 409
    assert response.json()["detail"] == "Policzona ilość musi odpowiadać rzeczywistej ilości z przygotowania powierzchni."


def test_packing_complete_accepts_valid_quantity_split_without_phantom_ok(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Packing counted valid", queue_position=1)
    advance_to_packing(test_client, created["id"])

    response = complete_packing_request(test_client, created["id"], counted_quantity=100, ok_quantity=90, correction_quantity=10)
    detail = test_client.get(f"/work-orders/{created['id']}")
    correction_order = next(
        item
        for item in test_client.get("/manager/work-orders/unplanned").json()
        if item["parent_order"]["id"] == created["id"]
    )

    assert response.status_code == 200
    assert response.json()["stage_status"] == {
        "stage": "PACKING",
        "status": {"value": "DONE", "label": "Zakończone"},
    }
    assert detail.json()["total_quantity"] == 100
    assert detail.json()["completed_quantity"] == 0
    assert detail.json()["current_active_quantity"] == 0
    assert detail.json()["process_status"] == {"value": "WAITING_FOR_CORRECTIONS", "label": "Czeka na poprawki"}
    assert detail.json()["waiting_ok_quantity"] == 90
    assert detail.json()["pending_correction_quantity"] == 10
    assert detail.json()["total_progress_quantity"] == 90
    assert correction_order["total_quantity"] == 10


def test_decoral_packing_rejects_counted_quantity_lower_than_planned(test_client: TestClient) -> None:
    created = create_planned_work_order(
        test_client,
        title="Decoral counted low",
        queue_position=1,
        production_type="MANUAL",
        coating_type="DECORAL",
    )
    start_surface_preparation(test_client, created["id"])
    test_client.post(f"/process/work-orders/{created['id']}/stages/SURFACE_PREPARATION/finish")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/start")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/finish")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PACKING/start")

    response = complete_packing_request(test_client, created["id"], counted_quantity=96, ok_quantity=96, correction_quantity=0)
    detail = test_client.get(f"/work-orders/{created['id']}")

    assert response.status_code == 409
    assert response.json()["detail"] == "Policzona ilość musi odpowiadać rzeczywistej ilości z przygotowania powierzchni."
    assert detail.json()["completed_quantity"] == 0
    assert detail.json()["current_active_quantity"] == 100
    assert detail.json()["process_status"] == {"value": "PACKING", "label": "Pakowanie"}


def test_packing_stage_list_includes_counted_quantity_difference(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Packing difference", queue_position=1)
    advance_to_packing(test_client, created["id"])

    response = test_client.get("/process/stages/PACKING/work-orders")

    assert response.status_code == 200
    item = next(item for item in response.json() if item["id"] == created["id"])
    assert item["planned_quantity"] == 100
    assert item["counted_quantity"] == 100
    assert item["quantity_difference"] == 0


def test_reopen_stage_moves_done_back_to_in_progress(test_client: TestClient) -> None:
    created = create_planned_work_order(test_client, title="Reopen me", queue_position=1)
    start_surface_preparation(test_client, created["id"])
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