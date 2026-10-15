"""CHANGES #24 (owner 2026-10-15): declared-vs-arrived quantity stays visible; overcount is added.

Pinned-before behaviour: an intake undercount (prep counts 10 of 14) redefined the order to 10 at
finalize (D5) and the only trace of "14 declared" was an audit event — the read model's
``surface_preparation_quantity_difference`` was counted against the redefined total, so it dropped to
0 exactly when the order closed (live: order 0002, 2026-10-15). An overcount (prep counts 16 of 14)
was rejected outright ("Policzona ilość nie może przekraczać oczekiwanej aktywnej ilości").

Owner decisions 2026-10-15:
- show "MNIEJ/WIĘCEJ NIŻ ZGŁOSZONO: X z Y" until the office ticks it "wyjaśnione"; m² untouched;
- extra pieces are added to the order ("dokładamy do zlecenia") — the same rule, on the plus side;
- office and manager may tick (and untick) "wyjaśnione"; operators may not.
"""

from __future__ import annotations

from tests.test_undercount_completion_changes12_13 import (
    build_create_payload,
    get_detail,
    get_direct_correction_children,
)


def create_planned(client, title: str, *, total_quantity: int, profiles: int | None = None,
                   accessories: int | None = None, coating_type: str = "RAL") -> int:
    payload = {**build_create_payload(title, total_quantity=total_quantity), "coating_type": coating_type}
    if profiles is not None:
        payload.update(
            profiles_quantity=profiles,
            profiles_to_count=False,
            accessories_quantity=accessories,
            accessories_to_count=False,
        )
    created = client.post("/work-orders", json=payload)
    assert created.status_code == 201, created.text
    order_id = created.json()["id"]
    plan = client.post(f"/manager/work-orders/{order_id}/plan", json={"production_type": "MANUAL"})
    assert plan.status_code == 200, plan.text
    return order_id


def finish_prep(client, order_id: int, counted_quantity: int) -> None:
    start = client.post(f"/process/work-orders/{order_id}/stages/SURFACE_PREPARATION/start")
    assert start.status_code == 200, start.text
    finish = client.post(
        f"/process/work-orders/{order_id}/stages/SURFACE_PREPARATION/finish",
        json={"counted_quantity": counted_quantity},
    )
    assert finish.status_code == 200, finish.text


def run_to_packing(client, order_id: int) -> None:
    assert client.post(f"/process/work-orders/{order_id}/stages/PRODUCTION/start").status_code == 200
    assert client.post(f"/process/work-orders/{order_id}/stages/PRODUCTION/finish").status_code == 200
    assert client.post(f"/process/work-orders/{order_id}/stages/PACKING/start").status_code == 200


def pack_all_ok(client, order_id: int, quantity: int) -> None:
    complete = client.post(
        f"/process/work-orders/{order_id}/packing/complete",
        json={"counted_quantity": quantity, "ok_quantity": quantity, "correction_quantity": 0},
    )
    assert complete.status_code == 200, complete.text


def audit_events(client, order_id: int, event_type: str) -> list[dict]:
    response = client.get(f"/audit/work-orders/{order_id}/events")
    assert response.status_code == 200
    return [event for event in response.json() if event["event_type"] == event_type]


def test_undercount_difference_survives_finalize_CHANGES24(test_client):
    """The order-0002 shape: 12 profiles + 2 accessories declared, 10 arrive. The difference must
    still read -4 against the declared 14 after the D5 redefinition closes the order at 10."""
    order_id = create_planned(test_client, "Undercount stays visible", total_quantity=14, profiles=12, accessories=2)
    finish_prep(test_client, order_id, 10)

    in_production = get_detail(test_client, order_id)
    assert in_production["surface_preparation_quantity_difference"] == -4
    assert in_production["declared_quantity"] == 14

    run_to_packing(test_client, order_id)
    pack_all_ok(test_client, order_id, 10)

    detail = get_detail(test_client, order_id)
    assert detail["process_status"]["value"] == "READY"
    assert detail["total_quantity"] == 10  # D5 unchanged: the order becomes a 10-piece order
    assert detail["declared_quantity"] == 14
    assert detail["declared_profiles_quantity"] == 12
    assert detail["declared_accessories_quantity"] == 2
    assert detail["surface_preparation_counted_quantity"] == 10
    assert detail["surface_preparation_quantity_difference"] == -4  # was: 0 (vanished at close)
    assert detail["total_area_m2"] == 12.0  # m² untouched (owner)


def test_overcount_is_added_to_the_order_at_prep_finish_CHANGES24(test_client):
    """5 declared, 7 arrive: prep accepts 7 (was: 409), the order becomes a 7-piece order right at
    prep finish, and packing / completion run as a plain 7-piece order — no leak flag."""
    order_id = create_planned(test_client, "Overcount added", total_quantity=5)
    finish_prep(test_client, order_id, 7)

    after_prep = get_detail(test_client, order_id)
    assert after_prep["total_quantity"] == 7
    assert after_prep["current_active_quantity"] == 7
    assert after_prep["declared_quantity"] == 5
    assert after_prep["surface_preparation_quantity_difference"] == 2
    increased = audit_events(test_client, order_id, "work_order.total_quantity_increased")
    assert len(increased) == 1
    assert "declared 5, arrived 7" in increased[0]["summary"]

    run_to_packing(test_client, order_id)
    pack_all_ok(test_client, order_id, 7)

    detail = get_detail(test_client, order_id)
    assert detail["process_status"]["value"] == "READY"
    assert detail["total_quantity"] == 7
    assert detail["completed_quantity"] == 7
    assert detail["quantity_leak_flagged"] is False
    assert detail["queue_position"] is None
    assert detail["surface_preparation_quantity_difference"] == 2
    assert detail["total_area_m2"] == 12.0


def test_overcount_counted_at_prep_start_is_added_at_finish_CHANGES24(test_client):
    """The count may be entered when prep starts; the order grows when prep finishes."""
    order_id = create_planned(test_client, "Overcount at start", total_quantity=5)
    start = test_client.post(
        f"/process/work-orders/{order_id}/stages/SURFACE_PREPARATION/start",
        json={"counted_quantity": 6},
    )
    assert start.status_code == 200, start.text
    assert get_detail(test_client, order_id)["total_quantity"] == 5
    finish = test_client.post(f"/process/work-orders/{order_id}/stages/SURFACE_PREPARATION/finish")
    assert finish.status_code == 200, finish.text
    assert get_detail(test_client, order_id)["total_quantity"] == 6


def test_overcount_category_split_follows_undercount_policy_CHANGES24(test_client):
    """Single-category declaration keeps its category; a mixed one falls back to "to count".
    The declared split stays on the order either way."""
    single_id = create_planned(test_client, "Overcount single category", total_quantity=5, profiles=5, accessories=0)
    finish_prep(test_client, single_id, 8)
    single = get_detail(test_client, single_id)
    assert (single["profiles_quantity"], single["accessories_quantity"]) == (8, 0)
    assert (single["declared_profiles_quantity"], single["declared_accessories_quantity"]) == (5, 0)

    mixed_id = create_planned(test_client, "Overcount mixed categories", total_quantity=5, profiles=3, accessories=2)
    finish_prep(test_client, mixed_id, 8)
    mixed = get_detail(test_client, mixed_id)
    assert mixed["profiles_quantity"] is None and mixed["profiles_to_count"] is True
    assert mixed["accessories_quantity"] is None and mixed["accessories_to_count"] is True
    assert (mixed["declared_profiles_quantity"], mixed["declared_accessories_quantity"]) == (3, 2)


def test_overcount_with_ral_correction_round_finalizes_CHANGES24(test_client):
    """5 declared, 7 arrive, 5 OK + 2 to correct: the RAL replan-in-place round completes and the
    order closes as a 7-piece order."""
    order_id = create_planned(test_client, "Overcount RAL correction", total_quantity=5)
    finish_prep(test_client, order_id, 7)
    run_to_packing(test_client, order_id)
    split = test_client.post(
        f"/process/work-orders/{order_id}/packing/complete",
        json={
            "counted_quantity": 7,
            "ok_quantity": 5,
            "correction_quantity": 2,
            "correction_profiles_quantity": 2,
            "correction_accessories_quantity": 0,
            "correction_reason_category": "niedomalowanie",
        },
    )
    assert split.status_code == 200, split.text
    assert get_detail(test_client, order_id)["completed_quantity"] == 5

    replan = test_client.post(f"/manager/work-orders/{order_id}/plan", json={"production_type": "MANUAL", "queue_position": 1})
    assert replan.status_code == 200, replan.text
    run_to_packing(test_client, order_id)
    pack_all_ok(test_client, order_id, 2)

    detail = get_detail(test_client, order_id)
    assert detail["process_status"]["value"] == "READY"
    assert (detail["total_quantity"], detail["completed_quantity"]) == (7, 7)
    assert detail["quantity_leak_flagged"] is False
    assert detail["surface_preparation_quantity_difference"] == 2


def test_overcount_with_decoral_child_finalizes_CHANGES24(test_client):
    """DECORAL: 5 declared, 7 arrive, 6 OK + 1 correction child; everything returns through the
    single Decoral pass and the root closes as a 7-piece order."""
    parent_id = create_planned(test_client, "Overcount Decoral child", total_quantity=5, coating_type="DECORAL")
    finish_prep(test_client, parent_id, 7)
    run_to_packing(test_client, parent_id)
    split = test_client.post(
        f"/process/work-orders/{parent_id}/packing/complete",
        json={
            "counted_quantity": 7,
            "ok_quantity": 6,
            "correction_quantity": 1,
            "correction_profiles_quantity": 1,
            "correction_accessories_quantity": 0,
            "correction_reason_category": "niedomalowanie",
        },
    )
    assert split.status_code == 200, split.text
    ok_batch_id = split.json()["batch_id"]
    assert test_client.post(
        f"/process/work-orders/{parent_id}/batches/{ok_batch_id}/stages/DECORAL_PRODUCTION/start"
    ).status_code == 200
    assert test_client.post(
        f"/process/work-orders/{parent_id}/batches/{ok_batch_id}/stages/DECORAL_PRODUCTION/finish"
    ).status_code == 200

    children = get_direct_correction_children(test_client, parent_id)
    assert len(children) == 1
    child_id = children[0]["id"]
    assert children[0]["surface_preparation_quantity_difference"] is None  # corrections skip prep: no badge
    plan_child = test_client.post(f"/manager/work-orders/{child_id}/plan", json={"production_type": "MANUAL", "queue_position": 2})
    assert plan_child.status_code == 200, plan_child.text
    run_to_packing(test_client, child_id)
    pack_all_ok(test_client, child_id, 1)

    board = test_client.get("/process/stages/DECORAL_PRODUCTION/work-orders")
    returned = next(
        row for row in board.json() if row["id"] == parent_id and row["stage_status"]["status"]["value"] != "DONE"
    )
    assert test_client.post(
        f"/process/work-orders/{parent_id}/batches/{returned['batch_id']}/stages/DECORAL_PRODUCTION/start"
    ).status_code == 200
    finish_returned = test_client.post(
        f"/process/work-orders/{parent_id}/batches/{returned['batch_id']}/decoral-production/complete",
        json={"ok_quantity": 1, "correction_quantity": 0},
    )
    assert finish_returned.status_code == 200, finish_returned.text

    detail = get_detail(test_client, parent_id)
    assert detail["process_status"]["value"] == "READY"
    assert (detail["total_quantity"], detail["completed_quantity"]) == (7, 7)
    assert detail["quantity_leak_flagged"] is False
    assert detail["declared_quantity"] == 5


def test_recount_after_overcount_keeps_first_declaration_CHANGES24(test_client):
    """Grown 5 -> 7, then prep is reopened and recounted at 6 (a typo fixed before downstream
    started): the order closes at 6 via the D5 undercount path and the client's 5 is still the
    declaration — a later redefinition never overwrites it."""
    order_id = create_planned(test_client, "Overcount recount", total_quantity=5)
    finish_prep(test_client, order_id, 7)
    reopen = test_client.post(f"/process/work-orders/{order_id}/stages/SURFACE_PREPARATION/reopen")
    assert reopen.status_code == 200, reopen.text
    refinish = test_client.post(
        f"/process/work-orders/{order_id}/stages/SURFACE_PREPARATION/finish",
        json={"counted_quantity": 6},
    )
    assert refinish.status_code == 200, refinish.text
    run_to_packing(test_client, order_id)
    pack_all_ok(test_client, order_id, 6)

    detail = get_detail(test_client, order_id)
    assert detail["process_status"]["value"] == "READY"
    assert (detail["total_quantity"], detail["completed_quantity"]) == (6, 6)
    assert detail["declared_quantity"] == 5
    assert detail["surface_preparation_quantity_difference"] == 1
    assert detail["quantity_leak_flagged"] is False


def test_matching_count_changes_nothing_CHANGES24(test_client):
    order_id = create_planned(test_client, "Exact count", total_quantity=5)
    finish_prep(test_client, order_id, 5)
    detail = get_detail(test_client, order_id)
    assert detail["surface_preparation_quantity_difference"] == 0
    assert detail["declared_quantity"] == 5
    assert audit_events(test_client, order_id, "work_order.total_quantity_increased") == []
    tick = test_client.patch(f"/work-orders/{order_id}/quantity-discrepancy", json={"is_resolved": True})
    assert tick.status_code == 409, tick.text  # nothing to explain


def test_discrepancy_resolution_tick_and_untick_CHANGES24(test_client):
    order_id = create_planned(test_client, "Tick explained", total_quantity=14)
    finish_prep(test_client, order_id, 10)

    for station in ("SURFACE_PREPARATION", "PACKING", "MANUAL_PRODUCTION"):
        denied = test_client.patch(
            f"/work-orders/{order_id}/quantity-discrepancy",
            json={"is_resolved": True},
            headers={"X-Station-Id": station},
        )
        assert denied.status_code == 403, (station, denied.text)

    manager = test_client.patch(
        f"/work-orders/{order_id}/quantity-discrepancy",
        json={"is_resolved": True},
        headers={"X-Station-Id": "MANAGER"},
    )
    assert manager.status_code == 200, manager.text
    assert manager.json()["quantity_discrepancy_resolved_by"] == "MANAGER"
    assert manager.json()["quantity_discrepancy_resolved_at"] is not None
    # The difference itself is untouched — the detail line stays.
    assert manager.json()["surface_preparation_quantity_difference"] == -4

    untick = test_client.patch(
        f"/work-orders/{order_id}/quantity-discrepancy",
        json={"is_resolved": False},
        headers={"X-Station-Id": "OFFICE"},
    )
    assert untick.status_code == 200, untick.text
    assert untick.json()["quantity_discrepancy_resolved_at"] is None
    assert untick.json()["quantity_discrepancy_resolved_by"] is None

    office = test_client.patch(
        f"/work-orders/{order_id}/quantity-discrepancy",
        json={"is_resolved": True},
        headers={"X-Station-Id": "OFFICE"},
    )
    assert office.status_code == 200, office.text
    assert office.json()["quantity_discrepancy_resolved_by"] == "OFFICE"
    assert len(audit_events(test_client, order_id, "work_order.quantity_discrepancy_resolution_updated")) == 3


def run_plain_decoral_pass(client, order_id: int) -> None:
    assert client.post(f"/process/work-orders/{order_id}/stages/DECORAL_PRODUCTION/start").status_code == 200
    finish = client.post(f"/process/work-orders/{order_id}/stages/DECORAL_PRODUCTION/finish")
    assert finish.status_code == 200, finish.text


def test_decoral_undercount_credits_only_arrived_pieces_CHANGES25(test_client):
    """CHANGES #25 (found 2026-10-15): 5 declared, 3 arrive, 3 packed OK. The Decoral pass credited the
    batch's DECLARED size, closing READY 5/5 with 3 real pieces (no D5 redefinition, no leak flag).
    It must credit the 3 that arrived and finalize as a 3-piece order through the D5 path."""
    order_id = create_planned(test_client, "Decoral undercount", total_quantity=5, coating_type="DECORAL")
    finish_prep(test_client, order_id, 3)
    run_to_packing(test_client, order_id)
    pack_all_ok(test_client, order_id, 3)
    run_plain_decoral_pass(test_client, order_id)

    detail = get_detail(test_client, order_id)
    assert detail["process_status"]["value"] == "READY"
    assert (detail["total_quantity"], detail["completed_quantity"]) == (3, 3)  # was: (5, 5)
    assert detail["quantity_leak_flagged"] is False
    assert detail["declared_quantity"] == 5
    assert detail["surface_preparation_quantity_difference"] == -2
    assert len(audit_events(test_client, order_id, "work_order.total_quantity_redefined")) == 1


def test_decoral_undercount_with_stat_only_correction_CHANGES25(test_client):
    """Same, with a correction fixed on the spot (stat-only): it folds into OK and the order still
    closes at the 3 pieces that arrived."""
    order_id = create_planned(test_client, "Decoral undercount stat-only", total_quantity=5, coating_type="DECORAL")
    finish_prep(test_client, order_id, 3)
    run_to_packing(test_client, order_id)
    complete = test_client.post(
        f"/process/work-orders/{order_id}/packing/complete",
        json={
            "counted_quantity": 3,
            "ok_quantity": 2,
            "correction_quantity": 1,
            "correction_profiles_quantity": 1,
            "correction_accessories_quantity": 0,
            "correction_reason_category": "niedomalowanie",
            "stat_only_correction": True,
        },
    )
    assert complete.status_code == 200, complete.text
    run_plain_decoral_pass(test_client, order_id)

    detail = get_detail(test_client, order_id)
    assert detail["process_status"]["value"] == "READY"
    assert (detail["total_quantity"], detail["completed_quantity"]) == (3, 3)
    assert detail["quantity_leak_flagged"] is False


def test_recount_up_after_undercount_restores_the_batch_CHANGES25(test_client):
    """Prep counted 3 of 5 (typo), was reopened and recounted at 5 before downstream started: the
    order is a plain 5-piece order again — nothing redefined, no difference."""
    order_id = create_planned(test_client, "Undercount typo fixed", total_quantity=5, coating_type="DECORAL")
    finish_prep(test_client, order_id, 3)
    assert get_detail(test_client, order_id)["current_active_quantity"] == 3
    reopen = test_client.post(f"/process/work-orders/{order_id}/stages/SURFACE_PREPARATION/reopen")
    assert reopen.status_code == 200, reopen.text
    refinish = test_client.post(
        f"/process/work-orders/{order_id}/stages/SURFACE_PREPARATION/finish",
        json={"counted_quantity": 5},
    )
    assert refinish.status_code == 200, refinish.text
    run_to_packing(test_client, order_id)
    pack_all_ok(test_client, order_id, 5)
    run_plain_decoral_pass(test_client, order_id)

    detail = get_detail(test_client, order_id)
    assert (detail["total_quantity"], detail["completed_quantity"]) == (5, 5)
    assert detail["surface_preparation_quantity_difference"] == 0
    assert detail["declared_quantity"] == 5
    assert audit_events(test_client, order_id, "work_order.total_quantity_redefined") == []
