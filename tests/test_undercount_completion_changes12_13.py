"""Regression tests for CHANGES #12/#13 (independent review 2026-07-11, §1.1; owner decision D5).

The pinned-before behaviour (commit 12d75ff) was: a quantity-clean undercounted completion
(prep counts 3 of 5, all 3 packed OK) showed READY via the all-stages-DONE display fall-through
but never finalized — total_quantity untouched, queue slot held forever, and planning into that
slot died on the partial unique index with a raw IntegrityError (HTTP 500) because the flush sat
outside the IntegrityError -> 409 handler.

Fixed behaviour (DECISIONS.md 2026-07-11 — D5):

- #12  A settled intake undercount finalizes: the order is REDEFINED to the counted amount
       ("becomes a 3-piece order"), the original ordered quantity is preserved in the
       ``work_order.total_quantity_redefined`` audit event, the queue slot is released, and
       the #10 leak tripwire does NOT false-flag it — on all three coating routes (clean RAL,
       RAL correction round, DECORAL correction child).
- #13  The freed slot is immediately plannable; a legacy zombie (a READY order still holding a
       position, written before this fix) is self-healed by the availability check; and the
       flush-level IntegrityError now maps to a 409 like the commit-level one.
"""

from __future__ import annotations

from sqlalchemy import select

from app.work_orders.models import WorkOrder
from tests.chaos.harness import ChaosEnvironment


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


def assert_redefinition_audit_event(client, work_order_id: int, *, ordered: int, arrived: int) -> None:
    response = client.get(f"/audit/work-orders/{work_order_id}/events")
    assert response.status_code == 200
    events = [event for event in response.json() if event["event_type"] == "work_order.total_quantity_redefined"]
    assert len(events) == 1, f"expected exactly one redefinition audit event, got {len(events)}"
    assert f"ordered {ordered}, arrived {arrived}" in events[0]["summary"]


def assert_finalized_at_counted(client, work_order_id: int, *, ordered: int, counted: int) -> None:
    """The D5 contract: redefined to the counted amount, slot released, no false leak flag,
    ordered-vs-arrived preserved in the audit trail."""
    detail = get_detail(client, work_order_id)
    assert detail["process_status"]["value"] == "READY"
    assert detail["total_quantity"] == counted
    assert detail["completed_quantity"] == counted
    assert detail["queue_position"] is None
    assert detail["quantity_leak_flagged"] is False
    assert_redefinition_audit_event(client, work_order_id, ordered=ordered, arrived=counted)


def test_clean_undercount_finalizes_redefined_to_counted_CHANGES12(test_client):
    """5 ordered / 3 counted / 3 packed OK -> a 3-piece order: finalized, slot released, audited."""
    created = create_planned_order(test_client, "Undercount clean 3 of 5", total_quantity=5, queue_position=1)
    run_undercounted_manual_flow_to_packing(test_client, created["id"], counted_quantity=3)

    complete = test_client.post(
        f"/process/work-orders/{created['id']}/packing/complete",
        json={"counted_quantity": 3, "ok_quantity": 3, "correction_quantity": 0},
    )
    assert complete.status_code == 200, complete.text

    assert_finalized_at_counted(test_client, created["id"], ordered=5, counted=3)


def test_undercount_with_ral_correction_round_finalizes_redefined_CHANGES12(test_client):
    """RAL: a packing correction is a replan-in-place round on the SAME order (no child order).
    5 ordered / 3 counted / 2 OK + 1 correction; the correction round completes -> the order
    finalizes as a 3-piece order exactly like the clean case."""
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

    assert_finalized_at_counted(test_client, order_id, ordered=5, counted=3)


def test_undercount_with_decoral_child_finalizes_redefined_no_false_leak_CHANGES12(test_client):
    """DECORAL: a packing correction creates a CHILD order, so finalize runs via the
    correction-children arm — the redefinition must land BEFORE the #10 leak tripwire so the
    owner-legitimate intake undercount is not false-flagged and force-closed 3 -> 5."""
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

    assert_finalized_at_counted(test_client, parent_id, ordered=5, counted=3)


def test_slot_released_by_undercount_completion_is_plannable_CHANGES13(test_client):
    """The end-to-end #13 repro, fixed at the root: the undercounted completion releases its slot,
    so planning the next order into that position simply succeeds (no 500, no 409)."""
    created = create_planned_order(test_client, "Former zombie slot holder", total_quantity=5, queue_position=1)
    run_undercounted_manual_flow_to_packing(test_client, created["id"], counted_quantity=3)
    complete = test_client.post(
        f"/process/work-orders/{created['id']}/packing/complete",
        json={"counted_quantity": 3, "ok_quantity": 3, "correction_quantity": 0},
    )
    assert complete.status_code == 200, complete.text
    assert get_detail(test_client, created["id"])["queue_position"] is None

    second = test_client.post("/work-orders", json=build_create_payload("Wants slot 1", total_quantity=4))
    assert second.status_code == 201
    plan_second = test_client.post(
        f"/manager/work-orders/{second.json()['id']}/plan",
        json={"production_type": "MANUAL", "queue_position": 1},
    )
    assert plan_second.status_code == 200, plan_second.text
    assert get_detail(test_client, second.json()["id"])["queue_position"] == 1


def test_legacy_zombie_slot_is_self_healed_on_plan_CHANGES13(tmp_path):
    """A READY order still holding a position (data written BEFORE the #12 fix) must not 500 the
    manager: the availability check now releases the zombie's slot for real (audited) and the
    plan proceeds. Fabricates the legacy state directly in the DB — the API can no longer produce it."""
    env = ChaosEnvironment(tmp_path / "legacy_zombie.db")
    try:
        client = env.create_actor_client("LegacyZombie")
        created = create_planned_order(client, "Legacy zombie", total_quantity=5, queue_position=1)
        run_undercounted_manual_flow_to_packing(client, created["id"], counted_quantity=5)
        complete = client.post(
            f"/process/work-orders/{created['id']}/packing/complete",
            json={"counted_quantity": 5, "ok_quantity": 5, "correction_quantity": 0},
        )
        assert complete.status_code == 200, complete.text
        assert get_detail(client, created["id"])["queue_position"] is None

        # Reinstate the pre-#12 zombie shape: READY but still holding (MANUAL, position 1).
        session = env.create_session()
        try:
            zombie = session.scalars(select(WorkOrder).where(WorkOrder.id == created["id"])).one()
            zombie.queue_position = 1
            session.commit()
        finally:
            session.close()

        second = client.post("/work-orders", json=build_create_payload("Heals the zombie slot", total_quantity=4))
        assert second.status_code == 201
        plan_second = client.post(
            f"/manager/work-orders/{second.json()['id']}/plan",
            json={"production_type": "MANUAL", "queue_position": 1},
        )
        assert plan_second.status_code == 200, plan_second.text  # was: raw IntegrityError (500)

        assert get_detail(client, second.json()["id"])["queue_position"] == 1
        assert get_detail(client, created["id"])["queue_position"] is None
        audit = client.get(f"/audit/work-orders/{created['id']}/events")
        assert audit.status_code == 200
        heal_events = [e for e in audit.json() if e["event_type"] == "manager.stale_queue_slot_released"]
        assert len(heal_events) == 1
    finally:
        env.close()


def test_queue_position_update_onto_zombie_slot_self_heals_CHANGES13(tmp_path):
    """Same legacy-zombie shape on the queue-position PATCH (manager drag/move) — 200, not a 500."""
    env = ChaosEnvironment(tmp_path / "legacy_zombie_patch.db")
    try:
        client = env.create_actor_client("LegacyZombiePatch")
        created = create_planned_order(client, "Legacy zombie 2", total_quantity=5, queue_position=1)
        run_undercounted_manual_flow_to_packing(client, created["id"], counted_quantity=5)
        complete = client.post(
            f"/process/work-orders/{created['id']}/packing/complete",
            json={"counted_quantity": 5, "ok_quantity": 5, "correction_quantity": 0},
        )
        assert complete.status_code == 200, complete.text

        session = env.create_session()
        try:
            zombie = session.scalars(select(WorkOrder).where(WorkOrder.id == created["id"])).one()
            zombie.queue_position = 1
            session.commit()
        finally:
            session.close()

        mover = create_planned_order(client, "Moves onto zombie slot", total_quantity=4, queue_position=2)
        move = client.patch(
            f"/manager/work-orders/{mover['id']}/queue-position",
            json={"queue_position": 1},
        )
        assert move.status_code == 200, move.text  # was: raw IntegrityError (500)
        assert get_detail(client, mover["id"])["queue_position"] == 1
        assert get_detail(client, created["id"])["queue_position"] is None
    finally:
        env.close()
