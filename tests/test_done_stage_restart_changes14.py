"""Pin tests for CHANGES #14 (independent review 2026-07-11, §1.2).

Pins the CURRENT (broken) behaviour: a DONE stage can be restarted while a downstream stage is
already IN_PROGRESS, and restarting SURFACE_PREPARATION overwrites the counted quantity (the
"actual received" ground truth). Packing then validates against the NEW count and closes the
order terminally inconsistent (2/5 completed, batch deactivated, no leak flag, queue slot held).

When the #14 guard lands, the restart-with-downstream-progress assert flips to a 409; the
no-downstream-progress test must KEEP passing (a legitimate recount before production starts
is allowed — the guard must not overreach).
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


def get_detail(client, work_order_id: int) -> dict:
    response = client.get(f"/work-orders/{work_order_id}")
    assert response.status_code == 200
    return response.json()


def stage_statuses(detail: dict) -> dict[str, str]:
    return {stage["stage"]["value"]: stage["status"]["value"] for stage in detail["stage_states"]}


def test_done_prep_restart_while_packing_active_rewrites_count_CHANGES14_pin(test_client):
    """Full corruption chain: prep DONE at 5 -> packing IN_PROGRESS -> prep restarted at 2 ->
    packing closes at 2/5 -> unfixable zombie."""
    created = create_planned_order(test_client, "Done restart mid-packing", total_quantity=5, queue_position=1)
    order_id = created["id"]

    start = test_client.post(
        f"/process/work-orders/{order_id}/stages/SURFACE_PREPARATION/start",
        json={"counted_quantity": 5},
    )
    assert start.status_code == 200, start.text
    assert test_client.post(f"/process/work-orders/{order_id}/stages/SURFACE_PREPARATION/finish").status_code == 200
    assert test_client.post(f"/process/work-orders/{order_id}/stages/PRODUCTION/start").status_code == 200
    assert test_client.post(f"/process/work-orders/{order_id}/stages/PRODUCTION/finish").status_code == 200
    assert test_client.post(f"/process/work-orders/{order_id}/stages/PACKING/start").status_code == 200

    # PIN (#14): with PACKING already IN_PROGRESS, restarting the DONE SURFACE_PREPARATION
    # succeeds and OVERWRITES the counted quantity 5 -> 2. After the fix this must be a 409
    # (re-touching a finished stage while downstream is active is the correction flow's job).
    restart = test_client.post(
        f"/process/work-orders/{order_id}/stages/SURFACE_PREPARATION/start",
        json={"counted_quantity": 2},
    )
    assert restart.status_code == 200, restart.text  # PIN: must become 409

    # Packing validates against the REWRITTEN count and closes the order at 2/5.
    complete = test_client.post(
        f"/process/work-orders/{order_id}/packing/complete",
        json={"counted_quantity": 2, "ok_quantity": 2, "correction_quantity": 0},
    )
    assert complete.status_code == 200, complete.text  # PIN: unreachable once restart 409s

    detail = get_detail(test_client, order_id)
    statuses = stage_statuses(detail)
    # PIN: terminally inconsistent zombie — packing DONE while prep sits IN_PROGRESS,
    # 2/5 credited, no leak flag, queue slot held forever, unfixable from the UI.
    assert detail["total_quantity"] == 5
    assert detail["completed_quantity"] == 2
    assert detail["quantity_leak_flagged"] is False
    assert detail["queue_position"] == 1
    assert statuses["PACKING"] == "DONE"
    assert statuses["SURFACE_PREPARATION"] == "IN_PROGRESS"


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
