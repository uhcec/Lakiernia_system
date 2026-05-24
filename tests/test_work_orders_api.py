from fastapi.testclient import TestClient


def create_work_order(test_client: TestClient, **overrides: object):
    payload = {"title": "Domyślne zlecenie", "coating_type": "RAL", "total_quantity": 100}
    payload.update(overrides)
    return test_client.post("/work-orders", json=payload)


def finish_ral_work_order(test_client: TestClient, work_order_id: int) -> None:
    test_client.post(f"/manager/work-orders/{work_order_id}/plan", json={"production_type": "MANUAL", "queue_position": 1})
    for stage in ["SURFACE_PREPARATION", "HANGING", "PRODUCTION", "PACKING"]:
        test_client.post(f"/process/work-orders/{work_order_id}/stages/{stage}/start")
        test_client.post(f"/process/work-orders/{work_order_id}/stages/{stage}/finish")


def test_create_work_order(test_client: TestClient) -> None:
    response = create_work_order(
        test_client,
        title="New generic work order",
        coating_type="RAL",
        description="Initial intake",
        customer_name="ACME",
        due_date="2026-06-15",
        notes="Handle carefully",
        total_quantity=250,
    )

    body = response.json()

    assert response.status_code == 201
    assert body["id"] == 1
    assert body["order_number"].startswith("WO-")
    assert body["title"] == "New generic work order"
    assert body["total_quantity"] == 250
    assert body["completed_quantity"] == 0
    assert body["current_active_quantity"] == 250
    assert body["description"] == "Initial intake"
    assert body["customer_name"] == "ACME"
    assert body["coating_type"] == {"value": "RAL", "label": "RAL"}
    assert body["due_date"] == "2026-06-15"
    assert body["notes"] == "Handle carefully"
    assert body["process_status"] == {"value": "TO_BE_PLANNED", "label": "Do zaplanowania"}
    assert body["created_at"]
    assert body["updated_at"]


def test_creating_without_coating_type_fails(test_client: TestClient) -> None:
    response = test_client.post("/work-orders", json={"title": "Missing coating", "total_quantity": 10})

    assert response.status_code == 422


def test_creating_ral_work_order_works(test_client: TestClient) -> None:
    response = create_work_order(test_client, title="RAL order", coating_type="RAL")

    assert response.status_code == 201
    assert response.json()["coating_type"] == {"value": "RAL", "label": "RAL"}


def test_creating_decoral_work_order_works(test_client: TestClient) -> None:
    response = create_work_order(test_client, title="Decoral order", coating_type="DECORAL")

    assert response.status_code == 201
    assert response.json()["coating_type"] == {"value": "DECORAL", "label": "Decoral"}


def test_created_work_order_defaults_to_entered_with_polish_label(test_client: TestClient) -> None:
    response = create_work_order(test_client, title="Status default", coating_type="RAL")

    body = response.json()

    assert response.status_code == 201
    assert body["status"] == {"value": "ENTERED", "label": "Wprowadzone"}


def test_client_cannot_set_initial_status(test_client: TestClient) -> None:
    response = test_client.post(
        "/work-orders",
        json={
            "title": "Rejected status override",
            "status": "FINISHED",
        },
    )

    assert response.status_code == 422


def test_get_work_order_by_id(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Single lookup", coating_type="RAL").json()

    response = test_client.get(f"/work-orders/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["order_number"] == created["order_number"]
    assert response.json()["total_quantity"] == 100
    assert response.json()["completed_quantity"] == 0
    assert response.json()["current_active_quantity"] == 100
    assert response.json()["batches"] == [
        {
            "id": 1,
            "quantity": 100,
            "type": {"value": "MAIN", "label": "Partia główna"},
            "parent_batch_id": None,
            "is_active": True,
            "is_finished": False,
            "created_at": response.json()["batches"][0]["created_at"],
        }
    ]
    assert response.json()["process_status"] == {"value": "TO_BE_PLANNED", "label": "Do zaplanowania"}


def test_update_work_order_title(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Original title", coating_type="RAL").json()

    response = test_client.patch(
        f"/work-orders/{created['id']}",
        json={"title": "Updated title"},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Updated title"


def test_update_work_order_notes_only(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Original", coating_type="RAL", notes="Old note").json()

    response = test_client.patch(
        f"/work-orders/{created['id']}",
        json={"notes": "Updated note"},
    )

    assert response.status_code == 200
    assert response.json()["notes"] == "Updated note"


def test_partial_update_does_not_erase_unspecified_fields(test_client: TestClient) -> None:
    created = create_work_order(
        test_client,
        title="Keep fields",
        coating_type="RAL",
        description="Original description",
        customer_name="Original customer",
    ).json()

    response = test_client.patch(
        f"/work-orders/{created['id']}",
        json={"notes": "Only notes changed"},
    )

    body = response.json()

    assert response.status_code == 200
    assert body["title"] == "Keep fields"
    assert body["description"] == "Original description"
    assert body["customer_name"] == "Original customer"
    assert body["notes"] == "Only notes changed"


def test_update_missing_work_order_returns_404(test_client: TestClient) -> None:
    response = test_client.patch("/work-orders/999", json={"title": "Missing"})

    assert response.status_code == 404


def test_attempting_to_update_status_fails_validation(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Forbidden status", coating_type="RAL").json()

    response = test_client.patch(
        f"/work-orders/{created['id']}",
        json={"status": "FINISHED"},
    )

    assert response.status_code == 422


def test_attempting_to_update_order_number_fails_validation(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Forbidden order number", coating_type="RAL").json()

    response = test_client.patch(
        f"/work-orders/{created['id']}",
        json={"order_number": "WO-2026-9999"},
    )

    assert response.status_code == 422


def test_update_response_includes_polish_status_label(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Polish status after update", coating_type="RAL").json()

    response = test_client.patch(
        f"/work-orders/{created['id']}",
        json={"notes": "Updated business field"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == {"value": "ENTERED", "label": "Wprowadzone"}


def test_status_transition_still_works_after_patch_update(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Patch then transition", coating_type="RAL").json()
    test_client.patch(
        f"/work-orders/{created['id']}",
        json={"notes": "Updated before transition"},
    )

    response = test_client.post(
        f"/work-orders/{created['id']}/status-transitions",
        json={"target_status": "ASSIGNED"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == {"value": "ASSIGNED", "label": "Przypisane"}


def test_list_work_orders(test_client: TestClient) -> None:
    test_client.post("/work-orders", json={"title": "First", "coating_type": "RAL", "total_quantity": 10})
    test_client.post("/work-orders", json={"title": "Second", "coating_type": "RAL", "total_quantity": 20})

    response = test_client.get("/work-orders")

    body = response.json()

    assert response.status_code == 200
    assert body["total"] == 2
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert len(body["items"]) == 2
    assert body["items"][0]["total_quantity"] == 10
    assert body["items"][0]["completed_quantity"] == 0
    assert body["items"][0]["process_status"] == {"value": "TO_BE_PLANNED", "label": "Do zaplanowania"}


def test_list_work_orders_includes_quantity_progress_fields(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Progress list", coating_type="RAL", total_quantity=100).json()
    test_client.post(f"/manager/work-orders/{created['id']}/plan", json={"production_type": "MANUAL", "queue_position": 1})
    for stage in ["SURFACE_PREPARATION", "HANGING", "PRODUCTION"]:
        test_client.post(f"/process/work-orders/{created['id']}/stages/{stage}/start")
        test_client.post(f"/process/work-orders/{created['id']}/stages/{stage}/finish")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PACKING/start")
    test_client.post(
        f"/process/work-orders/{created['id']}/packing/complete",
        json={"ok_quantity": 98, "correction_quantity": 2},
    )

    response = test_client.get("/work-orders")

    assert response.status_code == 200
    assert response.json()["items"][0]["total_quantity"] == 100
    assert response.json()["items"][0]["completed_quantity"] == 98
    assert response.json()["items"][0]["current_active_quantity"] == 2


def test_list_work_orders_can_filter_by_status(test_client: TestClient) -> None:
    test_client.post("/work-orders", json={"title": "Entered order", "coating_type": "RAL", "total_quantity": 15})

    response = test_client.get("/work-orders", params={"status": "ENTERED"})

    body = response.json()

    assert response.status_code == 200
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["status"] == {"value": "ENTERED", "label": "Wprowadzone"}


def test_missing_title_returns_validation_error(test_client: TestClient) -> None:
    response = test_client.post("/work-orders", json={"total_quantity": 10})

    assert response.status_code == 422


def test_create_work_order_defaults_total_quantity_to_one_for_compatibility(test_client: TestClient) -> None:
    response = test_client.post("/work-orders", json={"title": "Legacy payload", "coating_type": "RAL"})

    assert response.status_code == 201
    assert response.json()["total_quantity"] == 1
    assert response.json()["current_active_quantity"] == 1


def test_entered_to_assigned_transition_succeeds(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Transition 1", coating_type="RAL").json()

    response = test_client.post(
        f"/work-orders/{created['id']}/status-transitions",
        json={"target_status": "ASSIGNED"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == {"value": "ASSIGNED", "label": "Przypisane"}


def test_assigned_to_in_progress_transition_succeeds(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Transition 2", coating_type="RAL").json()
    test_client.post(
        f"/work-orders/{created['id']}/status-transitions",
        json={"target_status": "ASSIGNED"},
    )

    response = test_client.post(
        f"/work-orders/{created['id']}/status-transitions",
        json={"target_status": "IN_PROGRESS"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == {"value": "IN_PROGRESS", "label": "W trakcie"}


def test_in_progress_to_finished_transition_succeeds(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Transition 3", coating_type="RAL").json()
    test_client.post(
        f"/work-orders/{created['id']}/status-transitions",
        json={"target_status": "ASSIGNED"},
    )
    test_client.post(
        f"/work-orders/{created['id']}/status-transitions",
        json={"target_status": "IN_PROGRESS"},
    )

    response = test_client.post(
        f"/work-orders/{created['id']}/status-transitions",
        json={"target_status": "FINISHED", "comment": "Completed"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == {"value": "FINISHED", "label": "Skończone"}


def test_entered_to_in_progress_transition_fails(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Invalid 1", coating_type="RAL").json()

    response = test_client.post(
        f"/work-orders/{created['id']}/status-transitions",
        json={"target_status": "IN_PROGRESS"},
    )

    assert response.status_code == 409


def test_entered_to_finished_transition_fails(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Invalid 2", coating_type="RAL").json()

    response = test_client.post(
        f"/work-orders/{created['id']}/status-transitions",
        json={"target_status": "FINISHED"},
    )

    assert response.status_code == 409


def test_assigned_to_finished_transition_fails(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Invalid 3", coating_type="RAL").json()
    test_client.post(
        f"/work-orders/{created['id']}/status-transitions",
        json={"target_status": "ASSIGNED"},
    )

    response = test_client.post(
        f"/work-orders/{created['id']}/status-transitions",
        json={"target_status": "FINISHED"},
    )

    assert response.status_code == 409


def test_finished_to_assigned_transition_fails(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Invalid 4", coating_type="RAL").json()
    test_client.post(
        f"/work-orders/{created['id']}/status-transitions",
        json={"target_status": "ASSIGNED"},
    )
    test_client.post(
        f"/work-orders/{created['id']}/status-transitions",
        json={"target_status": "IN_PROGRESS"},
    )
    test_client.post(
        f"/work-orders/{created['id']}/status-transitions",
        json={"target_status": "FINISHED"},
    )

    response = test_client.post(
        f"/work-orders/{created['id']}/status-transitions",
        json={"target_status": "ASSIGNED"},
    )

    assert response.status_code == 409


def test_missing_work_order_transition_returns_404(test_client: TestClient) -> None:
    response = test_client.post(
        "/work-orders/999/status-transitions",
        json={"target_status": "ASSIGNED"},
    )

    assert response.status_code == 404


def test_transition_response_includes_polish_status_label(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Polish label", coating_type="RAL").json()

    response = test_client.post(
        f"/work-orders/{created['id']}/status-transitions",
        json={"target_status": "ASSIGNED"},
    )

    assert response.status_code == 200
    assert response.json()["status"]["label"] == "Przypisane"


def test_detail_and_list_include_process_status(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Process status", coating_type="RAL").json()

    detail_response = test_client.get(f"/work-orders/{created['id']}")
    list_response = test_client.get("/work-orders")

    assert detail_response.status_code == 200
    assert detail_response.json()["process_status"] == {"value": "TO_BE_PLANNED", "label": "Do zaplanowania"}
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["process_status"] == {"value": "TO_BE_PLANNED", "label": "Do zaplanowania"}


def test_after_packing_done_process_status_is_gotowe(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Ready order", coating_type="RAL").json()
    finish_ral_work_order(test_client, created["id"])

    response = test_client.get(f"/work-orders/{created['id']}")

    assert response.status_code == 200
    assert response.json()["process_status"] == {"value": "READY", "label": "Gotowe"}


def test_work_order_detail_returns_batches_in_created_order_with_main_and_correction(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Batch history", coating_type="RAL", total_quantity=100).json()
    test_client.post(f"/manager/work-orders/{created['id']}/plan", json={"production_type": "MANUAL", "queue_position": 1})
    for stage in ["SURFACE_PREPARATION", "HANGING", "PRODUCTION"]:
        test_client.post(f"/process/work-orders/{created['id']}/stages/{stage}/start")
        test_client.post(f"/process/work-orders/{created['id']}/stages/{stage}/finish")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PACKING/start")
    test_client.post(
        f"/process/work-orders/{created['id']}/packing/complete",
        json={"ok_quantity": 90, "correction_quantity": 10},
    )
    test_client.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/start")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/finish")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PACKING/start")
    test_client.post(
        f"/process/work-orders/{created['id']}/packing/complete",
        json={"ok_quantity": 8, "correction_quantity": 2},
    )

    response = test_client.get(f"/work-orders/{created['id']}")

    assert response.status_code == 200
    assert [batch["type"]["value"] for batch in response.json()["batches"]] == ["MAIN", "CORRECTION", "CORRECTION"]
    assert [batch["quantity"] for batch in response.json()["batches"]] == [100, 10, 2]
    assert [batch["parent_batch_id"] for batch in response.json()["batches"]] == [None, response.json()["batches"][0]["id"], response.json()["batches"][1]["id"]]
    assert response.json()["batches"][0]["is_finished"] is True
    assert response.json()["batches"][1]["is_finished"] is True
    assert response.json()["batches"][2]["is_active"] is True
    assert response.json()["batches"][2]["is_finished"] is False