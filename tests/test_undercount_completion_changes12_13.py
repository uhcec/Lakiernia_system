"""Pin tests for CHANGES #12/#13 (independent review 2026-07-11, §1.1).

These tests PIN THE CURRENT (broken) BEHAVIOUR of the undercount completion path so the fix
has an exact before/after diff. When the #12+#13 fix lands, the asserts marked ``# PIN`` get
flipped to the intended behaviour (DECISIONS.md 2026-07-11 — D5: redefine the order to the
counted amount with an audit trail; slot released; 409 instead of a raw IntegrityError).

Current behaviour being pinned:

- #12  A quantity-clean undercounted completion (prep counts 3 of 5, packing packs 3 OK)
       shows READY via the all-stages-DONE fall-through but never finalizes: total_quantity
       is not redefined, the queue slot is never released, no leak flag is raised.
- #12b An undercounted completion WITH a correction round DOES finalize (correction children
       satisfy _can_finalize_work_order), but the #10 leak tripwire then FALSE-flags the
       owner-legitimate undercount and force-closes 3 -> 5.
- #13  Planning another order into the zombie-held queue slot passes the availability check
       (READY holders are treated as releasable but nothing releases them) and dies on the
       partial unique index with a raw IntegrityError (HTTP 500), because session.flush()
       sits outside the IntegrityError -> 409 handler in assign_plan / update_queue_position.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError


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


def run_undercounted_manual_flow_to_packing(client, work_order_id: int, *, counted_quantity: int) -> None:
    """MANUAL route with prep counting fewer pieces than ordered (the owner-blessed undercount)."""
    start = client.post(
        f"/process/work-orders/{work_order_id}/stages/SURFACE_PREPARATION/start",
        json={"counted_quantity": counted_quantity},
    )
    assert start.status_code == 200, start.text
    finish = client.post(f"/process/work-orders/{work_order_id}/stages/SURFACE_PREPARATION/finish")
    assert finish.status_code == 200, finish.text
    assert client.post(f"/process/work-orders/{work_order_id}/stages/PRODUCTION/start").status_code == 200
    assert client.post(f"/process/work-orders/{work_order_id}/stages/PRODUCTION/finish").status_code == 200
    assert client.post(f"/process/work-orders/{work_order_id}/stages/PACKING/start").status_code == 200


def get_detail(client, work_order_id: int) -> dict:
    response = client.get(f"/work-orders/{work_order_id}")
    assert response.status_code == 200
    return response.json()


def get_direct_correction_children(client, parent_id: int) -> list[dict]:
    response = client.get("/manager/work-orders/unplanned")
    assert response.status_code == 200
    return [
        item
        for item in response.json()
        if item["is_correction"] and item["parent_order"] and item["parent_order"]["id"] == parent_id
    ]


def test_clean_undercount_shows_ready_but_never_finalizes_CHANGES12_pin(test_client):
    """5 ordered / 3 counted / 3 packed OK -> 'Gotowe' at 3/5, slot held, nothing redefined."""
    created = create_planned_order(test_client, "Undercount clean 3 of 5", total_quantity=5, queue_position=1)
    run_undercounted_manual_flow_to_packing(test_client, created["id"], counted_quantity=3)

    complete = test_client.post(
        f"/process/work-orders/{created['id']}/packing/complete",
        json={"counted_quantity": 3, "ok_quantity": 3, "correction_quantity": 0},
    )
    assert complete.status_code == 200, complete.text

    detail = get_detail(test_client, created["id"])
    # Display says done — the all-stages-DONE fall-through (app/process/service.py get_display_status).
    assert detail["process_status"]["value"] == "READY"
    # PIN (#12): finalization never ran — the order is a permanent zombie.
    assert detail["total_quantity"] == 5  # PIN: D5 says this becomes 3 (redefined to counted)
    assert detail["completed_quantity"] == 3  # PIN: finalize will set == total (3 after redefinition)
    assert detail["queue_position"] == 1  # PIN: finalize must release the slot (CHANGES #3)
    assert detail["quantity_leak_flagged"] is False  # legit undercount — must stay unflagged after fix too


def test_undercount_with_ral_correction_round_never_finalizes_CHANGES12_pin(test_client):
    """RAL: a packing correction is a replan-in-place round on the SAME order (no child order).
    5 ordered / 3 counted / 2 OK + 1 correction; the correction round completes -> the order
    ends at 3/5 like the clean case: READY display, never finalized, slot held."""
    created = create_planned_order(test_client, "Undercount RAL correction round", total_quantity=5, queue_position=1)
    order_id = created["id"]
    run_undercounted_manual_flow_to_packing(test_client, order_id, counted_quantity=3)

    complete = test_client.post(
        f"/process/work-orders/{order_id}/packing/complete",
        json={
            "counted_quantity": 3,
            "ok_quantity": 2,
            "correction_quantity": 1,
            "correction_profiles_quantity": 1,
            "correction_accessories_quantity": 0,
            "correction_reason_category": "niedomalowanie",
        },
    )
    assert complete.status_code == 200, complete.text

    # Replan-in-place: the order went back to planning with an active 1-piece correction batch.
    detail = get_detail(test_client, order_id)
    assert detail["process_status"]["value"] == "TO_BE_PLANNED"
    assert detail["completed_quantity"] == 2
    replan = test_client.post(
        f"/manager/work-orders/{order_id}/plan",
        json={"production_type": "MANUAL", "queue_position": 1},
    )
    assert replan.status_code == 200, replan.text

    # The correction batch returns at PRODUCTION (surface prep is done for the round).
    assert test_client.post(f"/process/work-orders/{order_id}/stages/PRODUCTION/start").status_code == 200
    assert test_client.post(f"/process/work-orders/{order_id}/stages/PRODUCTION/finish").status_code == 200
    assert test_client.post(f"/process/work-orders/{order_id}/stages/PACKING/start").status_code == 200
    round_complete = test_client.post(
        f"/process/work-orders/{order_id}/packing/complete",
        json={"counted_quantity": 1, "ok_quantity": 1, "correction_quantity": 0},
    )
    assert round_complete.status_code == 200, round_complete.text

    detail = get_detail(test_client, order_id)
    assert detail["process_status"]["value"] == "READY"
    # PIN (#12): same zombie as the clean case — all counted pieces are done (2 + 1 == 3) but
    # completed != ordered total and there are no correction children, so finalize never runs.
    assert detail["total_quantity"] == 5  # PIN: D5 says this becomes 3
    assert detail["completed_quantity"] == 3  # PIN: finalize will set == total (3 after redefinition)
    assert detail["queue_position"] == 1  # PIN: finalize must release the slot
    assert detail["quantity_leak_flagged"] is False


def test_undercount_with_decoral_child_false_flags_leak_CHANGES12_pin(test_client):
    """DECORAL: a packing correction creates a CHILD order, so _can_finalize_work_order passes via
    the correction-children arm — finalize DOES run, but the #10 leak tripwire then false-flags
    the owner-legitimate intake undercount and force-closes 3 -> 5."""
    payload = {**build_create_payload("Undercount Decoral child", total_quantity=5), "coating_type": "DECORAL"}
    create_response = test_client.post("/work-orders", json=payload)
    assert create_response.status_code == 201, create_response.text
    parent_id = create_response.json()["id"]
    plan_response = test_client.post(
        f"/manager/work-orders/{parent_id}/plan",
        json={"production_type": "MANUAL", "queue_position": 1},
    )
    assert plan_response.status_code == 200, plan_response.text
    run_undercounted_manual_flow_to_packing(test_client, parent_id, counted_quantity=3)

    split = test_client.post(
        f"/process/work-orders/{parent_id}/packing/complete",
        json={
            "counted_quantity": 3,
            "ok_quantity": 2,
            "correction_quantity": 1,
            "correction_profiles_quantity": 1,
            "correction_accessories_quantity": 0,
            "correction_reason_category": "niedomalowanie",
        },
    )
    assert split.status_code == 200, split.text
    ok_batch_id = split.json()["batch_id"]

    children = get_direct_correction_children(test_client, parent_id)
    assert len(children) == 1
    child_id = children[0]["id"]

    # Parent's OK pieces run Decoral.
    start_ok = test_client.post(f"/process/work-orders/{parent_id}/batches/{ok_batch_id}/stages/DECORAL_PRODUCTION/start")
    assert start_ok.status_code == 200, start_ok.text
    finish_ok = test_client.post(f"/process/work-orders/{parent_id}/batches/{ok_batch_id}/stages/DECORAL_PRODUCTION/finish")
    assert finish_ok.status_code == 200, finish_ok.text

    # Child correction order runs its round (prep is marked DONE at planning) and completes.
    plan_child = test_client.post(
        f"/manager/work-orders/{child_id}/plan",
        json={"production_type": "MANUAL", "queue_position": 2},
    )
    assert plan_child.status_code == 200, plan_child.text
    assert test_client.post(f"/process/work-orders/{child_id}/stages/PRODUCTION/start").status_code == 200
    assert test_client.post(f"/process/work-orders/{child_id}/stages/PRODUCTION/finish").status_code == 200
    assert test_client.post(f"/process/work-orders/{child_id}/stages/PACKING/start").status_code == 200
    child_complete = test_client.post(
        f"/process/work-orders/{child_id}/packing/complete",
        json={"counted_quantity": 1, "ok_quantity": 1, "correction_quantity": 0},
    )
    assert child_complete.status_code == 200, child_complete.text

    # The corrected piece returns to the parent's Decoral as a fresh batch — finish that too.
    board = test_client.get("/process/stages/DECORAL_PRODUCTION/work-orders")
    assert board.status_code == 200
    returned = next(
        (row for row in board.json() if row["id"] == parent_id and row["stage_status"]["status"]["value"] != "DONE"),
        None,
    )
    assert returned is not None, "expected the returned correction piece as a fresh Decoral batch"
    returned_batch_id = returned["batch_id"]
    start_returned = test_client.post(
        f"/process/work-orders/{parent_id}/batches/{returned_batch_id}/stages/DECORAL_PRODUCTION/start"
    )
    assert start_returned.status_code == 200, start_returned.text
    finish_returned = test_client.post(
        f"/process/work-orders/{parent_id}/batches/{returned_batch_id}/decoral-production/complete",
        json={"ok_quantity": 1, "correction_quantity": 0},
    )
    assert finish_returned.status_code == 200, finish_returned.text

    detail = get_detail(test_client, parent_id)
    assert detail["process_status"]["value"] == "READY"
    # PIN (#12): finalize runs (children exist) but the leak tripwire treats the intake
    # undercount as a leak: flags it and force-closes to the ordered total.
    # After the fix: total redefined to 3, completed == 3, NO leak flag.
    assert detail["total_quantity"] == 5  # PIN: D5 says this becomes 3
    assert detail["completed_quantity"] == 5  # PIN: forced to (old) total by the tripwire
    assert detail["quantity_leak_flagged"] is True  # PIN: false alarm — must be False after fix
    # Finalize ran on this path, so the slot IS released (contrast with the zombie pins).
    assert detail["queue_position"] is None


def test_planning_into_zombie_slot_raises_raw_integrity_error_CHANGES13_pin(test_client):
    """The zombie's slot passes the READY-skipping availability check, then the flush dies on the
    partial unique index OUTSIDE the IntegrityError -> 409 handler (raw 500)."""
    created = create_planned_order(test_client, "Zombie slot holder", total_quantity=5, queue_position=1)
    run_undercounted_manual_flow_to_packing(test_client, created["id"], counted_quantity=3)
    complete = test_client.post(
        f"/process/work-orders/{created['id']}/packing/complete",
        json={"counted_quantity": 3, "ok_quantity": 3, "correction_quantity": 0},
    )
    assert complete.status_code == 200, complete.text
    assert get_detail(test_client, created["id"])["queue_position"] == 1  # zombie holds slot 1

    second = test_client.post("/work-orders", json=build_create_payload("Wants slot 1", total_quantity=4))
    assert second.status_code == 201
    # PIN (#13): raw IntegrityError escapes to the transport (an HTTP 500 in production).
    # After the fix this must be a controlled 409 — or a 200 once the zombie path is gone (#12).
    with pytest.raises(IntegrityError):
        test_client.post(
            f"/manager/work-orders/{second.json()['id']}/plan",
            json={"production_type": "MANUAL", "queue_position": 1},
        )


def test_queue_position_update_into_zombie_slot_raises_raw_integrity_error_CHANGES13_pin(test_client):
    """Same flush-outside-handler shape on the queue-position PATCH (manager drag/move)."""
    created = create_planned_order(test_client, "Zombie slot holder 2", total_quantity=5, queue_position=1)
    run_undercounted_manual_flow_to_packing(test_client, created["id"], counted_quantity=3)
    complete = test_client.post(
        f"/process/work-orders/{created['id']}/packing/complete",
        json={"counted_quantity": 3, "ok_quantity": 3, "correction_quantity": 0},
    )
    assert complete.status_code == 200, complete.text

    mover = create_planned_order(test_client, "Wants to move onto slot 1", total_quantity=4, queue_position=2)
    # PIN (#13): raw IntegrityError instead of a controlled 409.
    with pytest.raises(IntegrityError):
        test_client.patch(
            f"/manager/work-orders/{mover['id']}/queue-position",
            json={"queue_position": 1},
        )
