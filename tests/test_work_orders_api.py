from fastapi.testclient import TestClient


def test_create_work_order(test_client: TestClient) -> None:
    response = test_client.post(
        "/work-orders",
        json={
            "title": "New generic work order",
            "description": "Initial intake",
            "customer_name": "ACME",
            "due_date": "2026-06-15",
            "notes": "Handle carefully",
        },
    )

    body = response.json()

    assert response.status_code == 201
    assert body["id"] == 1
    assert body["order_number"].startswith("WO-")
    assert body["title"] == "New generic work order"
    assert body["description"] == "Initial intake"
    assert body["customer_name"] == "ACME"
    assert body["due_date"] == "2026-06-15"
    assert body["notes"] == "Handle carefully"
    assert body["created_at"]
    assert body["updated_at"]


def test_created_work_order_defaults_to_entered_with_polish_label(test_client: TestClient) -> None:
    response = test_client.post("/work-orders", json={"title": "Status default"})

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
    created = test_client.post("/work-orders", json={"title": "Single lookup"}).json()

    response = test_client.get(f"/work-orders/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["order_number"] == created["order_number"]


def test_update_work_order_title(test_client: TestClient) -> None:
    created = test_client.post("/work-orders", json={"title": "Original title"}).json()

    response = test_client.patch(
        f"/work-orders/{created['id']}",
        json={"title": "Updated title"},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Updated title"


def test_update_work_order_notes_only(test_client: TestClient) -> None:
    created = test_client.post("/work-orders", json={"title": "Original", "notes": "Old note"}).json()

    response = test_client.patch(
        f"/work-orders/{created['id']}",
        json={"notes": "Updated note"},
    )

    assert response.status_code == 200
    assert response.json()["notes"] == "Updated note"


def test_partial_update_does_not_erase_unspecified_fields(test_client: TestClient) -> None:
    created = test_client.post(
        "/work-orders",
        json={
            "title": "Keep fields",
            "description": "Original description",
            "customer_name": "Original customer",
        },
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
    created = test_client.post("/work-orders", json={"title": "Forbidden status"}).json()

    response = test_client.patch(
        f"/work-orders/{created['id']}",
        json={"status": "FINISHED"},
    )

    assert response.status_code == 422


def test_attempting_to_update_order_number_fails_validation(test_client: TestClient) -> None:
    created = test_client.post("/work-orders", json={"title": "Forbidden order number"}).json()

    response = test_client.patch(
        f"/work-orders/{created['id']}",
        json={"order_number": "WO-2026-9999"},
    )

    assert response.status_code == 422


def test_update_response_includes_polish_status_label(test_client: TestClient) -> None:
    created = test_client.post("/work-orders", json={"title": "Polish status after update"}).json()

    response = test_client.patch(
        f"/work-orders/{created['id']}",
        json={"notes": "Updated business field"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == {"value": "ENTERED", "label": "Wprowadzone"}


def test_status_transition_still_works_after_patch_update(test_client: TestClient) -> None:
    created = test_client.post("/work-orders", json={"title": "Patch then transition"}).json()
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
    test_client.post("/work-orders", json={"title": "First"})
    test_client.post("/work-orders", json={"title": "Second"})

    response = test_client.get("/work-orders")

    body = response.json()

    assert response.status_code == 200
    assert body["total"] == 2
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert len(body["items"]) == 2


def test_list_work_orders_can_filter_by_status(test_client: TestClient) -> None:
    test_client.post("/work-orders", json={"title": "Entered order"})

    response = test_client.get("/work-orders", params={"status": "ENTERED"})

    body = response.json()

    assert response.status_code == 200
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["status"] == {"value": "ENTERED", "label": "Wprowadzone"}


def test_missing_title_returns_validation_error(test_client: TestClient) -> None:
    response = test_client.post("/work-orders", json={})

    assert response.status_code == 422


def test_entered_to_assigned_transition_succeeds(test_client: TestClient) -> None:
    created = test_client.post("/work-orders", json={"title": "Transition 1"}).json()

    response = test_client.post(
        f"/work-orders/{created['id']}/status-transitions",
        json={"target_status": "ASSIGNED"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == {"value": "ASSIGNED", "label": "Przypisane"}


def test_assigned_to_in_progress_transition_succeeds(test_client: TestClient) -> None:
    created = test_client.post("/work-orders", json={"title": "Transition 2"}).json()
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
    created = test_client.post("/work-orders", json={"title": "Transition 3"}).json()
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
    created = test_client.post("/work-orders", json={"title": "Invalid 1"}).json()

    response = test_client.post(
        f"/work-orders/{created['id']}/status-transitions",
        json={"target_status": "IN_PROGRESS"},
    )

    assert response.status_code == 409


def test_entered_to_finished_transition_fails(test_client: TestClient) -> None:
    created = test_client.post("/work-orders", json={"title": "Invalid 2"}).json()

    response = test_client.post(
        f"/work-orders/{created['id']}/status-transitions",
        json={"target_status": "FINISHED"},
    )

    assert response.status_code == 409


def test_assigned_to_finished_transition_fails(test_client: TestClient) -> None:
    created = test_client.post("/work-orders", json={"title": "Invalid 3"}).json()
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
    created = test_client.post("/work-orders", json={"title": "Invalid 4"}).json()
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
    created = test_client.post("/work-orders", json={"title": "Polish label"}).json()

    response = test_client.post(
        f"/work-orders/{created['id']}/status-transitions",
        json={"target_status": "ASSIGNED"},
    )

    assert response.status_code == 200
    assert response.json()["status"]["label"] == "Przypisane"