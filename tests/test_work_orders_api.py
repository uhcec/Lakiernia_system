from fastapi.testclient import TestClient


def build_create_payload(**overrides: object) -> dict:
    payload = {
        "title": "Domyślne zlecenie",
        "coating_type": "RAL",
        "total_quantity": 100,
        "customer_name": "ACME",
        "ral_code": "RAL 7016",
        "paint_producer": "AkzoNobel",
        "received_date": "2026-05-25",
        "profiles_to_count": True,
        "accessories_to_count": True,
    }
    payload.update(overrides)
    if payload.get("profiles_quantity") is not None and "profiles_to_count" not in overrides:
        payload["profiles_to_count"] = False
    if payload.get("accessories_quantity") is not None and "accessories_to_count" not in overrides:
        payload["accessories_to_count"] = False
    return payload


def create_work_order(test_client: TestClient, **overrides: object):
    return test_client.post("/work-orders", json=build_create_payload(**overrides))


def start_surface_preparation(test_client: TestClient, work_order_id: int, counted_quantity: int | None = None) -> None:
    if counted_quantity is None:
        detail = test_client.get(f"/work-orders/{work_order_id}").json()
        counted_quantity = detail["current_active_quantity"]

    test_client.post(
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
) -> None:
    test_client.post(
        f"/process/work-orders/{work_order_id}/packing/complete",
        json={
            "counted_quantity": counted_quantity,
            "ok_quantity": ok_quantity,
            "correction_quantity": correction_quantity,
        },
    )


def finish_ral_work_order(test_client: TestClient, work_order_id: int) -> None:
    test_client.post(f"/manager/work-orders/{work_order_id}/plan", json={"production_type": "MANUAL", "queue_position": 1})
    for stage in ["SURFACE_PREPARATION", "HANGING", "PRODUCTION", "PACKING"]:
        if stage == "SURFACE_PREPARATION":
            start_surface_preparation(test_client, work_order_id)
        else:
            test_client.post(f"/process/work-orders/{work_order_id}/stages/{stage}/start")
        test_client.post(f"/process/work-orders/{work_order_id}/stages/{stage}/finish")


def test_create_work_order(test_client: TestClient) -> None:
    response = create_work_order(
        test_client,
        title="New generic work order",
        coating_type="RAL",
        description="Initial intake",
        customer_name="ACME",
        ral_code="RAL 9005",
        paint_producer="Tiger",
        received_date="2026-05-20",
        planned_pickup_date="2026-06-15",
        total_area_m2=42.5,
        profiles_quantity=12,
        accessories_quantity=8,
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
    assert body["ral_code"] == "RAL 9005"
    assert body["paint_producer"] == "Tiger"
    assert body["coating_type"] == {"value": "RAL", "label": "RAL"}
    assert body["received_date"] == "2026-05-20"
    assert body["planned_pickup_date"] == "2026-06-15"
    assert body["total_area_m2"] == 42.5
    assert body["is_incomplete_on_arrival"] is False
    assert body["profiles_quantity"] == 12
    assert body["profiles_to_count"] is False
    assert body["accessories_quantity"] == 8
    assert body["accessories_to_count"] is False
    assert body["notes"] == "Handle carefully"
    assert body["process_status"] == {"value": "TO_BE_PLANNED", "label": "Do zaplanowania"}
    assert body["created_at"]
    assert body["updated_at"]


def test_create_work_order_with_missing_optional_fields(test_client: TestClient) -> None:
    response = create_work_order(
        test_client,
        title="Optional fields omitted",
        planned_pickup_date=None,
        total_area_m2=None,
    )

    assert response.status_code == 201
    assert response.json()["planned_pickup_date"] is None
    assert response.json()["total_area_m2"] is None


def test_create_incomplete_work_order_sets_incomplete_status(test_client: TestClient) -> None:
    response = create_work_order(
        test_client,
        title="Incomplete on arrival",
        is_incomplete_on_arrival=True,
    )

    body = response.json()

    assert response.status_code == 201
    assert body["is_incomplete_on_arrival"] is True
    assert body["status"] == {"value": "INCOMPLETE", "label": "Nie kompletne"}
    assert body["process_status"] == {"value": "INCOMPLETE", "label": "Nie kompletne"}


def test_create_work_order_with_to_count_flags(test_client: TestClient) -> None:
    response = create_work_order(
        test_client,
        title="To count order",
        profiles_to_count=True,
        accessories_to_count=True,
        profiles_quantity=None,
        accessories_quantity=None,
    )

    assert response.status_code == 201
    assert response.json()["profiles_quantity"] is None
    assert response.json()["profiles_to_count"] is True
    assert response.json()["accessories_quantity"] is None
    assert response.json()["accessories_to_count"] is True


def test_creating_without_required_fields_fails(test_client: TestClient) -> None:
    payload = build_create_payload()
    payload.pop("customer_name")
    payload.pop("received_date")

    response = test_client.post("/work-orders", json=payload)

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
    assert body["process_status"] == {"value": "TO_BE_PLANNED", "label": "Do zaplanowania"}


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
    assert response.json()["received_date"] == "2026-05-25"
    assert response.json()["ral_code"] == "RAL 7016"
    assert response.json()["batches"] == [
        {
            "id": 1,
            "quantity": 100,
            "type": {"value": "MAIN", "label": "Partia główna"},
            "parent_batch_id": None,
            "is_active": True,
            "is_finished": False,
            "current_stage": None,
            "current_stage_status": None,
            "is_partial": False,
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
    test_client.post("/work-orders", json=build_create_payload(title="First", total_quantity=10))
    test_client.post("/work-orders", json=build_create_payload(title="Second", total_quantity=20))

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
        if stage == "SURFACE_PREPARATION":
            start_surface_preparation(test_client, created["id"])
        else:
            test_client.post(f"/process/work-orders/{created['id']}/stages/{stage}/start")
        test_client.post(f"/process/work-orders/{created['id']}/stages/{stage}/finish")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PACKING/start")
    complete_packing_request(test_client, created["id"], counted_quantity=100, ok_quantity=98, correction_quantity=2)

    response = test_client.get("/work-orders")

    assert response.status_code == 200
    assert response.json()["items"][0]["total_quantity"] == 100
    assert response.json()["items"][0]["completed_quantity"] == 98
    assert response.json()["items"][0]["current_active_quantity"] == 2


def test_list_work_orders_can_filter_by_status(test_client: TestClient) -> None:
    test_client.post("/work-orders", json=build_create_payload(title="Entered order", total_quantity=15))

    response = test_client.get("/work-orders", params={"status": "ENTERED"})

    body = response.json()

    assert response.status_code == 200
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["status"] == {"value": "ENTERED", "label": "Wprowadzone"}


def test_missing_title_returns_validation_error(test_client: TestClient) -> None:
    payload = build_create_payload(total_quantity=10)
    payload.pop("title")

    response = test_client.post("/work-orders", json=payload)

    assert response.status_code == 422


def test_profiles_and_accessories_require_quantity_or_to_count_flag(test_client: TestClient) -> None:
    response = test_client.post(
        "/work-orders",
        json=build_create_payload(
            title="Missing count info",
            profiles_to_count=False,
            accessories_to_count=False,
        ),
    )

    assert response.status_code == 422


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


def test_incomplete_order_can_be_marked_complete_arrival(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Incomplete to planning", is_incomplete_on_arrival=True).json()

    response = test_client.post(f"/work-orders/{created['id']}/mark-complete-arrival")

    assert response.status_code == 200
    assert response.json()["is_incomplete_on_arrival"] is False
    assert response.json()["status"] == {"value": "ENTERED", "label": "Wprowadzone"}
    assert response.json()["process_status"] == {"value": "TO_BE_PLANNED", "label": "Do zaplanowania"}


def test_normal_order_cannot_be_marked_complete_arrival(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Normal order", is_incomplete_on_arrival=False).json()

    response = test_client.post(f"/work-orders/{created['id']}/mark-complete-arrival")

    assert response.status_code == 409


def test_detail_and_list_include_process_status(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Process status", coating_type="RAL").json()

    detail_response = test_client.get(f"/work-orders/{created['id']}")
    list_response = test_client.get("/work-orders")

    assert detail_response.status_code == 200
    assert detail_response.json()["process_status"] == {"value": "TO_BE_PLANNED", "label": "Do zaplanowania"}
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["process_status"] == {"value": "TO_BE_PLANNED", "label": "Do zaplanowania"}


def test_mark_complete_arrival_updates_detail_and_list_process_status(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Arrival done", is_incomplete_on_arrival=True).json()

    test_client.post(f"/work-orders/{created['id']}/mark-complete-arrival")

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
        if stage == "SURFACE_PREPARATION":
            start_surface_preparation(test_client, created["id"])
        else:
            test_client.post(f"/process/work-orders/{created['id']}/stages/{stage}/start")
        test_client.post(f"/process/work-orders/{created['id']}/stages/{stage}/finish")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PACKING/start")
    complete_packing_request(test_client, created["id"], counted_quantity=100, ok_quantity=90, correction_quantity=10)
    test_client.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/start")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PRODUCTION/finish")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PACKING/start")
    complete_packing_request(test_client, created["id"], counted_quantity=10, ok_quantity=8, correction_quantity=2)

    response = test_client.get(f"/work-orders/{created['id']}")

    assert response.status_code == 200
    assert [batch["type"]["value"] for batch in response.json()["batches"]] == ["MAIN", "CORRECTION", "CORRECTION"]
    assert [batch["quantity"] for batch in response.json()["batches"]] == [100, 10, 2]
    assert [batch["parent_batch_id"] for batch in response.json()["batches"]] == [None, response.json()["batches"][0]["id"], response.json()["batches"][1]["id"]]
    assert response.json()["batches"][0]["is_finished"] is True
    assert response.json()["batches"][1]["is_finished"] is True
    assert response.json()["batches"][2]["is_active"] is True
    assert response.json()["batches"][2]["is_finished"] is False