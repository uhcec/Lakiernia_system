"""Regression tests for CHANGES #14 (independent review 2026-07-11, §1.2).

The pinned-before behaviour (commits 12d75ff / 0119a9e): with PACKING already IN_PROGRESS, a
DONE SURFACE_PREPARATION could be restarted, silently rewriting the counted quantity ("actual
received" ground truth); packing then validated against the rewritten count and — after the #12
fix — the rewrite even impersonated a settled intake undercount and closed the order redefined.

Fixed behaviour:

- A DONE stage refuses start/reopen while ANY downstream stage is IN_PROGRESS or DONE (409,
  Polish operator message) — SPEC §3 names the correction flow as the legitimate re-entry.
- A recount restart with NO downstream progress keeps working (the guard must not overreach).
- The escape hatch: an office/manager (or admin) can administratively reset a genuinely stuck
  order back to the start of its route — audited, refused for correction-entangled orders,
  forbidden to operators (owner decision 2026-07-11: manager/admin/office).
"""

from __future__ import annotations


def build_create_payload(title: str, *, total_quantity: int = 5) -> dict:
    return {
        "title": title,
        "coating_type": "RAL",
        "total_quantity": total_quantity,
        "customer_name": "ACME",
        "ral_code": "RAL 7016",
        "paint_code": "P-7016",
        "paint_producer": "AkzoNobel",
        "received_date": "2026-07-01",
        "planned_pickup_date": "2026-07-15",
        "total_area_m2": 12.0,
        "profiles_to_count": True,
        "accessories_to_count": True,
    }


def create_planned_order(client, title: str, *, total_quantity: int = 5, queue_position: int = 1) -> dict:
    create_response = client.post("/work-orders", json=build_create_payload(title, total_quantity=total_quantity))
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()
    plan_response = client.post(
        f"/manager/work-orders/{created['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": queue_position},
    )
    assert plan_response.status_code == 200, plan_response.text
    return created


def drive_to_packing_in_progress(client, order_id: int, *, counted_quantity: int = 5) -> None:
    start = client.post(
        f"/process/work-orders/{order_id}/stages/SURFACE_PREPARATION/start",
        json={"counted_quantity": counted_quantity},
    )
    assert start.status_code == 200, start.text
    assert client.post(f"/process/work-orders/{order_id}/stages/SURFACE_PREPARATION/finish").status_code == 200
    assert client.post(f"/process/work-orders/{order_id}/stages/PRODUCTION/start").status_code == 200
    assert client.post(f"/process/work-orders/{order_id}/stages/PRODUCTION/finish").status_code == 200
    assert client.post(f"/process/work-orders/{order_id}/stages/PACKING/start").status_code == 200


def get_detail(client, work_order_id: int) -> dict:
    response = client.get(f"/work-orders/{work_order_id}")
    assert response.status_code == 200
    return response.json()


def stage_statuses(detail: dict) -> dict[str, str]:
    return {stage["stage"]["value"]: stage["status"]["value"] for stage in detail["stage_states"]}


def test_done_prep_restart_while_packing_active_is_rejected_CHANGES14(test_client):
    """The §1.2 corruption chain is cut at its first link: the restart itself gets a 409 and the
    recorded count survives untouched."""
    created = create_planned_order(test_client, "Done restart mid-packing", total_quantity=5, queue_position=1)
    order_id = created["id"]
    drive_to_packing_in_progress(test_client, order_id, counted_quantity=5)

    restart = test_client.post(
        f"/process/work-orders/{order_id}/stages/SURFACE_PREPARATION/start",
        json={"counted_quantity": 2},
    )
    assert restart.status_code == 409, restart.text
    assert "Nie można cofnąć zakończonego etapu" in restart.json()["detail"]

    # The count was NOT rewritten: packing still validates against the original 5 and completes clean.
    complete = test_client.post(
        f"/process/work-orders/{order_id}/packing/complete",
        json={"counted_quantity": 5, "ok_quantity": 5, "correction_quantity": 0},
    )
    assert complete.status_code == 200, complete.text
    detail = get_detail(test_client, order_id)
    assert detail["total_quantity"] == 5
    assert detail["completed_quantity"] == 5
    assert detail["queue_position"] is None


def test_done_production_reopen_while_packing_active_is_rejected_CHANGES14(test_client):
    """Same guard on the reopen route (DONE -> IN_PROGRESS via /reopen)."""
    created = create_planned_order(test_client, "Reopen production mid-packing", total_quantity=5, queue_position=1)
    order_id = created["id"]
    drive_to_packing_in_progress(test_client, order_id, counted_quantity=5)

    reopen = test_client.post(f"/process/work-orders/{order_id}/stages/PRODUCTION/reopen")
    assert reopen.status_code == 409, reopen.text
    assert "Nie można cofnąć zakończonego etapu" in reopen.json()["detail"]


def test_done_prep_restart_with_no_downstream_progress_is_allowed(test_client):
    """A recount BEFORE production starts is legitimate and must survive the #14 guard:
    prep DONE at 3, operator realizes the truck had 4, restarts, recounts, finishes at 4."""
    created = create_planned_order(test_client, "Legit recount before production", total_quantity=5, queue_position=1)
    order_id = created["id"]

    start = test_client.post(
        f"/process/work-orders/{order_id}/stages/SURFACE_PREPARATION/start",
        json={"counted_quantity": 3},
    )
    assert start.status_code == 200, start.text
    assert test_client.post(f"/process/work-orders/{order_id}/stages/SURFACE_PREPARATION/finish").status_code == 200

    restart = test_client.post(
        f"/process/work-orders/{order_id}/stages/SURFACE_PREPARATION/start",
        json={"counted_quantity": 4},
    )
    assert restart.status_code == 200, restart.text
    assert test_client.post(f"/process/work-orders/{order_id}/stages/SURFACE_PREPARATION/finish").status_code == 200

    detail = get_detail(test_client, order_id)
    assert stage_statuses(detail)["SURFACE_PREPARATION"] == "DONE"


def test_administrative_reset_restarts_route_from_scratch_CHANGES14(test_client):
    """The escape hatch: a mid-flight order is reset to 'planned, nothing started' — stage rows
    NOT_STARTED, counts cleared, fresh active MAIN batch at the ordered total, audit event written —
    and the floor can run the whole route again to a clean completion."""
    created = create_planned_order(test_client, "Stuck order reset", total_quantity=5, queue_position=1)
    order_id = created["id"]
    drive_to_packing_in_progress(test_client, order_id, counted_quantity=3)

    reset = test_client.post(f"/work-orders/{order_id}/administrative-reset")
    assert reset.status_code == 200, reset.text

    detail = get_detail(test_client, order_id)
    statuses = stage_statuses(detail)
    assert set(statuses.values()) == {"NOT_STARTED"}
    assert detail["completed_quantity"] == 0
    assert detail["current_active_quantity"] == 5
    assert detail["quantity_leak_flagged"] is False
    assert detail["queue_position"] == 1  # the plan survives the reset

    audit = test_client.get(f"/audit/work-orders/{order_id}/events")
    assert audit.status_code == 200
    reset_events = [e for e in audit.json() if e["event_type"] == "work_order.administrative_reset"]
    assert len(reset_events) == 1

    # The route runs again end-to-end and completes clean at the full ordered quantity.
    drive_to_packing_in_progress(test_client, order_id, counted_quantity=5)
    complete = test_client.post(
        f"/process/work-orders/{order_id}/packing/complete",
        json={"counted_quantity": 5, "ok_quantity": 5, "correction_quantity": 0},
    )
    assert complete.status_code == 200, complete.text
    detail = get_detail(test_client, order_id)
    assert detail["process_status"]["value"] == "READY"
    assert detail["completed_quantity"] == 5
    assert detail["queue_position"] is None


def test_administrative_reset_station_permissions_CHANGES14(test_client):
    """Owner decision 2026-07-11: manager, admin and office may reset; operators may not."""
    created = create_planned_order(test_client, "Reset permissions", total_quantity=5, queue_position=1)
    order_id = created["id"]
    drive_to_packing_in_progress(test_client, order_id, counted_quantity=5)

    operator = test_client.post(
        f"/work-orders/{order_id}/administrative-reset",
        headers={"X-Station-Id": "SURFACE_PREPARATION"},
    )
    assert operator.status_code == 403, operator.text

    packing_operator = test_client.post(
        f"/work-orders/{order_id}/administrative-reset",
        headers={"X-Station-Id": "PACKING"},
    )
    assert packing_operator.status_code == 403, packing_operator.text

    manager = test_client.post(
        f"/work-orders/{order_id}/administrative-reset",
        headers={"X-Station-Id": "MANAGER"},
    )
    assert manager.status_code == 200, manager.text

    # Office (and the admin default identity, exercised by the other tests) may reset too.
    drive_to_packing_in_progress(test_client, order_id, counted_quantity=5)
    office = test_client.post(
        f"/work-orders/{order_id}/administrative-reset",
        headers={"X-Station-Id": "OFFICE"},
    )
    assert office.status_code == 200, office.text


def test_administrative_reset_refuses_correction_entangled_orders_CHANGES14(test_client):
    """Quantity is split across a correction chain — a blind reset would break conservation, so
    both the parent (with a child) and the child itself are refused."""
    payload = {**build_create_payload("Reset refuses corrections", total_quantity=5), "coating_type": "DECORAL"}
    create_response = test_client.post("/work-orders", json=payload)
    assert create_response.status_code == 201
    parent_id = create_response.json()["id"]
    assert (
        test_client.post(
            f"/manager/work-orders/{parent_id}/plan",
            json={"production_type": "MANUAL", "queue_position": 1},
        ).status_code
        == 200
    )
    drive_to_packing_in_progress(test_client, parent_id, counted_quantity=5)
    split = test_client.post(
        f"/process/work-orders/{parent_id}/packing/complete",
        json={
            "counted_quantity": 5,
            "ok_quantity": 4,
            "correction_quantity": 1,
            "correction_profiles_quantity": 1,
            "correction_accessories_quantity": 0,
            "correction_reason_category": "niedomalowanie",
        },
    )
    assert split.status_code == 200, split.text

    unplanned = test_client.get("/manager/work-orders/unplanned")
    child_id = next(
        item["id"]
        for item in unplanned.json()
        if item["is_correction"] and item["parent_order"] and item["parent_order"]["id"] == parent_id
    )

    parent_reset = test_client.post(f"/work-orders/{parent_id}/administrative-reset")
    assert parent_reset.status_code == 409, parent_reset.text
    child_reset = test_client.post(f"/work-orders/{child_id}/administrative-reset")
    assert child_reset.status_code == 409, child_reset.text
