import pytest
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


def assert_work_order_fields_unchanged(
    test_client: TestClient,
    work_order_id: int,
    *,
    profiles_quantity: int | None,
    profiles_to_count: bool,
    accessories_quantity: int | None,
    accessories_to_count: bool,
    customer_name: str,
    notes: str | None,
) -> None:
    detail_response = test_client.get(f"/work-orders/{work_order_id}")

    assert detail_response.status_code == 200
    assert detail_response.json()["profiles_quantity"] == profiles_quantity
    assert detail_response.json()["profiles_to_count"] is profiles_to_count
    assert detail_response.json()["accessories_quantity"] == accessories_quantity
    assert detail_response.json()["accessories_to_count"] is accessories_to_count
    assert detail_response.json()["customer_name"] == customer_name
    assert detail_response.json()["notes"] == notes


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
    correction_reason_category: str | None = None,
    correction_reason_note: str | None = None,
) -> None:
    payload = {
        "counted_quantity": counted_quantity,
        "ok_quantity": ok_quantity,
        "correction_quantity": correction_quantity,
    }
    if correction_quantity > 0:
        payload["correction_reason_category"] = correction_reason_category or "niedomalowanie"
        if correction_reason_note is not None:
            payload["correction_reason_note"] = correction_reason_note
    test_client.post(f"/process/work-orders/{work_order_id}/packing/complete", json=payload)


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
        external_order_number="EXT-2026/15",
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
    assert body["external_order_number"] == "EXT-2026/15"
    assert body["is_released_to_client"] is False
    assert body["released_to_client_at"] is None
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


def test_create_work_order_rejects_invalid_station_header(test_client: TestClient) -> None:
    response = test_client.post(
        "/work-orders",
        json=build_create_payload(),
        headers={"X-Station-Id": "warehouse"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid station identity: warehouse."}


def test_create_work_order_without_title_uses_order_number_as_fallback(test_client: TestClient) -> None:
    payload = build_create_payload(total_quantity=10)
    payload.pop("title")

    response = test_client.post("/work-orders", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["order_number"].startswith("WO-")
    assert body["title"] == body["order_number"]


def test_create_work_order_with_missing_optional_fields(test_client: TestClient) -> None:
    response = create_work_order(
        test_client,
        title="Optional fields omitted",
        planned_pickup_date=None,
        total_area_m2=None,
    )

    assert response.status_code == 201
    assert response.json()["external_order_number"] is None
    assert response.json()["planned_pickup_date"] is None
    assert response.json()["total_area_m2"] is None


def test_external_order_number_can_be_updated_and_cleared(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="External number", external_order_number="CLIENT-1").json()

    update_response = test_client.patch(
        f"/work-orders/{created['id']}",
        json={"external_order_number": "CLIENT-2"},
    )
    clear_response = test_client.patch(
        f"/work-orders/{created['id']}",
        json={"external_order_number": None},
    )

    assert update_response.status_code == 200
    assert update_response.json()["external_order_number"] == "CLIENT-2"
    assert clear_response.status_code == 200
    assert clear_response.json()["external_order_number"] is None


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


def test_creating_przemalowanka_ocynk_work_order_exposes_type_markers(test_client: TestClient) -> None:
    response = create_work_order(
        test_client,
        title="Przemalowanka Ocynk",
        coating_type="DECORAL",
        work_order_kind="PRZEMALOWANKA",
        is_ocynk=True,
    )

    body = response.json()

    assert response.status_code == 201
    assert body["work_order_kind"] == {"value": "PRZEMALOWANKA", "label": "Przemalowanka"}
    assert body["is_ocynk"] is True
    assert body["is_correction"] is False
    assert body["parent_order"] is None
    assert body["queue_namespace"] == {"value": "MAIN", "label": "Main"}
    assert [stage["stage"]["value"] for stage in body["stage_states"]] == [
        "HANGING",
        "PRODUCTION",
        "PACKING",
        "DECORAL_PRODUCTION",
    ]


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


@pytest.mark.parametrize(
    ("create_overrides", "patch_payload"),
    [
        ({"profiles_to_count": True, "profiles_quantity": None}, {"profiles_to_count": False}),
        ({"profiles_to_count": False, "profiles_quantity": 5}, {"profiles_quantity": None}),
        ({"profiles_to_count": False, "profiles_quantity": 5}, {"profiles_to_count": True}),
        ({"profiles_to_count": True, "profiles_quantity": None}, {"profiles_quantity": 5}),
        ({"accessories_to_count": True, "accessories_quantity": None}, {"accessories_to_count": False}),
        ({"accessories_to_count": False, "accessories_quantity": 7}, {"accessories_quantity": None}),
        ({"accessories_to_count": False, "accessories_quantity": 7}, {"accessories_to_count": True}),
        ({"accessories_to_count": True, "accessories_quantity": None}, {"accessories_quantity": 7}),
    ],
)
def test_patch_rejects_invalid_merged_counting_state(
    test_client: TestClient,
    create_overrides: dict[str, object],
    patch_payload: dict[str, object],
) -> None:
    created = create_work_order(test_client, title="Invalid merged patch", **create_overrides).json()

    response = test_client.patch(f"/work-orders/{created['id']}", json=patch_payload)

    assert response.status_code == 422
    assert_work_order_fields_unchanged(
        test_client,
        created["id"],
        profiles_quantity=created["profiles_quantity"],
        profiles_to_count=created["profiles_to_count"],
        accessories_quantity=created["accessories_quantity"],
        accessories_to_count=created["accessories_to_count"],
        customer_name=created["customer_name"],
        notes=created["notes"],
    )


def test_patch_rejects_blank_customer_name_after_stripping(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Blank customer patch", customer_name="Original customer").json()

    response = test_client.patch(
        f"/work-orders/{created['id']}",
        json={"customer_name": "   "},
    )

    assert response.status_code == 422
    assert_work_order_fields_unchanged(
        test_client,
        created["id"],
        profiles_quantity=created["profiles_quantity"],
        profiles_to_count=created["profiles_to_count"],
        accessories_quantity=created["accessories_quantity"],
        accessories_to_count=created["accessories_to_count"],
        customer_name=created["customer_name"],
        notes=created["notes"],
    )


def test_valid_partial_patch_preserves_counting_consistency(test_client: TestClient) -> None:
    created = create_work_order(
        test_client,
        title="Valid partial patch",
        profiles_quantity=5,
        profiles_to_count=False,
        accessories_quantity=None,
        accessories_to_count=True,
        customer_name="Original customer",
    ).json()

    response = test_client.patch(
        f"/work-orders/{created['id']}",
        json={"notes": "Updated note", "customer_name": "Updated customer"},
    )

    assert response.status_code == 200
    assert response.json()["notes"] == "Updated note"
    assert response.json()["customer_name"] == "Updated customer"
    assert response.json()["profiles_quantity"] == 5
    assert response.json()["profiles_to_count"] is False
    assert response.json()["accessories_quantity"] is None
    assert response.json()["accessories_to_count"] is True


def test_rejected_patch_leaves_previous_values_unchanged(test_client: TestClient) -> None:
    created = create_work_order(
        test_client,
        title="Rejected patch rollback",
        profiles_quantity=5,
        profiles_to_count=False,
        accessories_quantity=7,
        accessories_to_count=False,
        customer_name="Stable customer",
        notes="Stable note",
    ).json()

    response = test_client.patch(
        f"/work-orders/{created['id']}",
        json={"profiles_to_count": True, "notes": "Should not persist"},
    )

    assert response.status_code == 422
    assert_work_order_fields_unchanged(
        test_client,
        created["id"],
        profiles_quantity=5,
        profiles_to_count=False,
        accessories_quantity=7,
        accessories_to_count=False,
        customer_name="Stable customer",
        notes="Stable note",
    )


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


def test_patch_cannot_clear_incomplete_arrival_flag(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Forbidden incomplete patch", is_incomplete_on_arrival=True).json()

    response = test_client.patch(
        f"/work-orders/{created['id']}",
        json={"is_incomplete_on_arrival": False},
    )
    detail_response = test_client.get(f"/work-orders/{created['id']}")

    assert response.status_code == 422
    assert detail_response.status_code == 200
    assert detail_response.json()["is_incomplete_on_arrival"] is True
    assert detail_response.json()["status"] == {"value": "INCOMPLETE", "label": "Nie kompletne"}


def test_patch_cannot_set_incomplete_arrival_flag_on_complete_order(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Forbidden incomplete set", is_incomplete_on_arrival=False).json()

    response = test_client.patch(
        f"/work-orders/{created['id']}",
        json={"is_incomplete_on_arrival": True},
    )
    detail_response = test_client.get(f"/work-orders/{created['id']}")

    assert response.status_code == 422
    assert detail_response.status_code == 200
    assert detail_response.json()["is_incomplete_on_arrival"] is False
    assert detail_response.json()["process_status"] == {"value": "TO_BE_PLANNED", "label": "Do zaplanowania"}


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

    assert response.status_code == 409
    assert response.json()["detail"] == "Work order status is derived from process status and cannot be changed manually."


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
    original_item = next(item for item in response.json()["items"] if item["id"] == created["id"])
    correction_item = next(item for item in response.json()["items"] if item["is_correction"] is True)

    assert response.status_code == 200
    assert original_item["total_quantity"] == 100
    assert original_item["completed_quantity"] == 0
    assert original_item["current_active_quantity"] == 0
    assert original_item["waiting_ok_quantity"] == 98
    assert original_item["pending_correction_quantity"] == 2
    assert original_item["total_progress_quantity"] == 98
    assert original_item["process_status"] == {"value": "WAITING_FOR_CORRECTIONS", "label": "Czeka na poprawki"}
    assert original_item["status"] == {"value": "IN_PROGRESS", "label": "W trakcie"}
    assert correction_item["total_quantity"] == 2
    assert correction_item["status"] == {"value": "ENTERED", "label": "Wprowadzone"}
    assert correction_item["parent_order"]["id"] == created["id"]


def test_list_work_orders_can_filter_by_process_status(test_client: TestClient) -> None:
    entered = test_client.post("/work-orders", json=build_create_payload(title="Entered order", total_quantity=15)).json()
    incomplete = test_client.post(
        "/work-orders",
        json=build_create_payload(title="Incomplete order", total_quantity=20, is_incomplete_on_arrival=True),
    ).json()

    response = test_client.get("/work-orders", params={"process_status": "TO_BE_PLANNED"})

    body = response.json()

    assert response.status_code == 200
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == entered["id"]
    assert body["items"][0]["status"] == {"value": "ENTERED", "label": "Wprowadzone"}
    assert incomplete["id"] not in [item["id"] for item in body["items"]]


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


def test_manual_status_transition_is_rejected(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Transition rejected", coating_type="RAL").json()

    response = test_client.post(
        f"/work-orders/{created['id']}/status-transitions",
        json={"target_status": "ASSIGNED"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Work order status is derived from process status and cannot be changed manually."


def test_missing_work_order_transition_returns_404(test_client: TestClient) -> None:
    response = test_client.post(
        "/work-orders/999/status-transitions",
        json={"target_status": "ASSIGNED"},
    )

    assert response.status_code == 404


def test_status_is_derived_from_process_status_for_active_order(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Derived active status", coating_type="RAL").json()
    test_client.post(
        f"/manager/work-orders/{created['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 1},
    )
    start_surface_preparation(test_client, created["id"])

    response = test_client.get(f"/work-orders/{created['id']}")

    assert response.status_code == 200
    assert response.json()["process_status"] == {"value": "SURFACE_PREPARATION", "label": "Przygotowanie"}
    assert response.json()["status"] == {"value": "IN_PROGRESS", "label": "W trakcie"}


def test_status_is_derived_from_process_status_for_ready_order(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Derived ready status", coating_type="RAL").json()
    finish_ral_work_order(test_client, created["id"])

    response = test_client.get(f"/work-orders/{created['id']}")

    assert response.status_code == 200
    assert response.json()["process_status"] == {"value": "READY", "label": "Gotowe"}
    assert response.json()["status"] == {"value": "FINISHED", "label": "Skończone"}


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
    assert detail_response.json()["status"] == {"value": "ENTERED", "label": "Wprowadzone"}
    assert detail_response.json()["is_incomplete_on_arrival"] is False
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["process_status"] == {"value": "TO_BE_PLANNED", "label": "Do zaplanowania"}


def test_after_packing_done_process_status_is_gotowe(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Ready order", coating_type="RAL").json()
    finish_ral_work_order(test_client, created["id"])

    response = test_client.get(f"/work-orders/{created['id']}")

    assert response.status_code == 200
    assert response.json()["process_status"] == {"value": "READY", "label": "Gotowe"}


def test_ready_work_order_release_status_can_be_marked_and_cleared(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Release ready", coating_type="RAL").json()
    finish_ral_work_order(test_client, created["id"])

    release_response = test_client.patch(
        f"/work-orders/{created['id']}/release-status",
        json={"is_released_to_client": True},
        headers={"X-Station-Id": "OFFICE"},
    )
    clear_response = test_client.patch(
        f"/work-orders/{created['id']}/release-status",
        json={"is_released_to_client": False},
        headers={"X-Station-Id": "MANAGER"},
    )

    assert release_response.status_code == 200
    assert release_response.json()["process_status"] == {"value": "READY", "label": "Gotowe"}
    assert release_response.json()["is_released_to_client"] is True
    assert release_response.json()["released_to_client_at"] is not None
    assert clear_response.status_code == 200
    assert clear_response.json()["is_released_to_client"] is False
    assert clear_response.json()["released_to_client_at"] is None

    audit_response = test_client.get(f"/audit/work-orders/{created['id']}/events")
    release_events = [event for event in audit_response.json() if event["event_type"] == "work_order.release_status_updated"]
    assert [event["station_id"] for event in release_events] == ["OFFICE", "MANAGER"]
    assert release_events[0]["details"]["is_released_to_client"] is True
    assert release_events[0]["details"]["released_to_client_at"] is not None
    assert release_events[1]["details"] == {"is_released_to_client": False, "released_to_client_at": None}


def test_active_work_order_cannot_be_marked_released(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Release active", coating_type="RAL").json()

    response = test_client.patch(
        f"/work-orders/{created['id']}/release-status",
        json={"is_released_to_client": True},
        headers={"X-Station-Id": "OFFICE"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Only READY work orders can be marked as released to client."


def test_wrong_station_cannot_update_release_status(test_client: TestClient) -> None:
    created = create_work_order(test_client, title="Release wrong station", coating_type="RAL").json()
    finish_ral_work_order(test_client, created["id"])

    response = test_client.patch(
        f"/work-orders/{created['id']}/release-status",
        json={"is_released_to_client": True},
        headers={"X-Station-Id": "PACKING"},
    )

    assert response.status_code == 403


def test_work_order_detail_returns_parent_and_correction_orders(test_client: TestClient) -> None:
    created = create_work_order(
        test_client,
        title="Correction history",
        coating_type="RAL",
        total_quantity=100,
        external_order_number="CLIENT-CORR-1",
    ).json()
    test_client.post(f"/manager/work-orders/{created['id']}/plan", json={"production_type": "MANUAL", "queue_position": 1})
    for stage in ["SURFACE_PREPARATION", "HANGING", "PRODUCTION"]:
        if stage == "SURFACE_PREPARATION":
            start_surface_preparation(test_client, created["id"])
        else:
            test_client.post(f"/process/work-orders/{created['id']}/stages/{stage}/start")
        test_client.post(f"/process/work-orders/{created['id']}/stages/{stage}/finish")
    test_client.post(f"/process/work-orders/{created['id']}/stages/PACKING/start")
    complete_packing_request(
        test_client,
        created["id"],
        counted_quantity=100,
        ok_quantity=90,
        correction_quantity=10,
        correction_reason_category="inne",
        correction_reason_note="opis od pakowania",
    )
    correction_order = next(
        item
        for item in test_client.get("/manager/work-orders/unplanned").json()
        if item["parent_order"]["id"] == created["id"]
    )

    response = test_client.get(f"/work-orders/{created['id']}")
    correction_response = test_client.get(f"/work-orders/{correction_order['id']}")

    assert response.status_code == 200
    assert response.json()["is_correction"] is False
    assert response.json()["parent_order"] is None
    assert len(response.json()["correction_orders"]) == 1
    assert response.json()["correction_orders"][0]["id"] == correction_order["id"]
    assert response.json()["correction_orders"][0]["total_quantity"] == 10
    assert response.json()["correction_orders"][0]["external_order_number"] == "CLIENT-CORR-1"
    assert response.json()["correction_orders"][0]["correction_reason_category"] == "inne"
    assert response.json()["correction_orders"][0]["correction_reason_note"] == "opis od pakowania"
    assert correction_response.status_code == 200
    assert correction_response.json()["is_correction"] is True
    assert correction_response.json()["external_order_number"] == "CLIENT-CORR-1"
    assert correction_response.json()["correction_reason_category"] == "inne"
    assert correction_response.json()["correction_reason_note"] == "opis od pakowania"
    assert correction_response.json()["parent_order"]["id"] == created["id"]
    assert correction_response.json()["correction_orders"] == []