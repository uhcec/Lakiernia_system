"""CHANGES #29 — several orders may hang at once (owner 2026-10-15).

A small order takes only part of a beam, so the hanging station starts the next order next to it. The
manager sets the limit N in "Ustawienia" (default 1 = the old rule). Orders hung together must share the
paint, and — owner choice (b) — orders hung together may also finish hanging together; an order started
after the line holder had finished hanging still waits for that holder's packing.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.shared import clock
from tests.test_paint_runs_changes22 import GREY, WHITE, create_automatic_order
from tests.test_process_api import advance_to_hanging, complete_packing_request, ensure_paint_stock

MANAGER = {"X-Station-Id": "MANAGER"}
HANGING = {"X-Station-Id": "HANGING"}


@pytest.fixture
def tick():
    """Step a frozen clock forward one minute per call, so start/finish order is unambiguous."""
    current = [datetime(2026, 10, 15, 8, 0, tzinfo=UTC)]
    clock.set_virtual_now(current[0])

    def advance() -> None:
        current[0] += timedelta(minutes=1)
        clock.set_virtual_now(current[0])

    yield advance
    clock.set_virtual_now(None)


def set_limit(test_client: TestClient, limit: int) -> None:
    response = test_client.put("/shop-settings", json={"hanging_max_active_orders": limit}, headers=MANAGER)
    assert response.status_code == 200, response.text


def order(test_client: TestClient, title: str, paint: dict = GREY) -> int:
    ensure_paint_stock(test_client, **paint, target_quantity_kg=100.0)
    created = create_automatic_order(test_client, title=title, paint=paint, area_m2=10.0)
    advance_to_hanging(test_client, created["id"])
    return created["id"]


def hanging_action(test_client: TestClient, work_order_id: int, action: str):
    return test_client.post(f"/process/work-orders/{work_order_id}/stages/HANGING/{action}")


def pack(test_client: TestClient, work_order_id: int):
    active = test_client.get(f"/work-orders/{work_order_id}").json()["current_active_quantity"]
    return complete_packing_request(
        test_client, work_order_id, counted_quantity=active, ok_quantity=active, correction_quantity=0
    )


def manager_block_reason(test_client: TestClient, work_order_id: int) -> str | None:
    items = test_client.get("/manager/work-orders").json()
    return next(item for item in items if item["id"] == work_order_id)["queue_blocked_reason"]


def test_settings_default_to_one_and_only_the_manager_changes_them(test_client: TestClient) -> None:
    assert test_client.get("/shop-settings", headers=HANGING).json() == {"hanging_max_active_orders": 1}

    forbidden = test_client.put("/shop-settings", json={"hanging_max_active_orders": 3}, headers=HANGING)
    assert forbidden.status_code == 403
    assert test_client.put("/shop-settings", json={"hanging_max_active_orders": 0}, headers=MANAGER).status_code == 422

    set_limit(test_client, 3)
    assert test_client.get("/shop-settings", headers=HANGING).json() == {"hanging_max_active_orders": 3}
    events = test_client.get("/audit/events", params={"event_type": "settings.updated"}).json()
    items = events["items"] if isinstance(events, dict) else events
    assert any(event["event_type"] == "settings.updated" for event in items)


def test_with_limit_two_two_same_paint_orders_hang_and_a_third_is_refused(test_client: TestClient, tick) -> None:
    set_limit(test_client, 2)
    first, second, third = (order(test_client, name) for name in ("A", "B", "C"))

    assert hanging_action(test_client, first, "start").status_code == 200
    tick()
    assert hanging_action(test_client, second, "start").status_code == 200
    tick()
    refused = hanging_action(test_client, third, "start")
    assert refused.status_code == 409
    assert refused.json()["detail"] == "Zawieszanie pełne: rozpoczęto już 2 zlecenia naraz (limit w Ustawieniach)."
    assert manager_block_reason(test_client, third) == "Zawieszanie zajęte"


def test_a_different_paint_cannot_hang_together(test_client: TestClient, tick) -> None:
    set_limit(test_client, 2)
    grey = order(test_client, "grey", GREY)
    white = order(test_client, "white", WHITE)

    assert hanging_action(test_client, grey, "start").status_code == 200
    tick()
    refused = hanging_action(test_client, white, "start")
    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        "Na zawieszaniu wisi inna farba (RAL 7016 · AkzoNobel · P-7016). "
        "Razem można wieszać tylko zlecenia z tą samą farbą."
    )
    assert manager_block_reason(test_client, white) == "Na zawieszaniu inna farba"


def test_orders_hung_together_finish_together_and_pack_one_after_another(test_client: TestClient, tick) -> None:
    set_limit(test_client, 2)
    first, second = order(test_client, "A"), order(test_client, "B")

    assert hanging_action(test_client, first, "start").status_code == 200
    tick()
    assert hanging_action(test_client, second, "start").status_code == 200
    tick()
    assert hanging_action(test_client, first, "finish").status_code == 200
    tick()
    # Owner (b): started while A was still hanging → may finish although A is not packed yet.
    assert hanging_action(test_client, second, "finish").status_code == 200
    tick()

    assert pack(test_client, first).status_code == 200
    tick()
    assert pack(test_client, second).status_code == 200
    for work_order_id in (first, second):
        assert test_client.get(f"/work-orders/{work_order_id}").json()["process_status"]["value"] in {"READY", "FINISHED"}


def test_an_order_started_after_the_holder_finished_still_waits_for_its_packing(test_client: TestClient, tick) -> None:
    set_limit(test_client, 2)
    first, second = order(test_client, "A"), order(test_client, "B")

    assert hanging_action(test_client, first, "start").status_code == 200
    tick()
    assert hanging_action(test_client, first, "finish").status_code == 200
    tick()
    assert hanging_action(test_client, second, "start").status_code == 200
    tick()
    blocked = hanging_action(test_client, second, "finish")
    assert blocked.status_code == 409
    assert blocked.json()["detail"].startswith("Linia automatu jest zajęta")

    assert pack(test_client, first).status_code == 200
    tick()
    assert hanging_action(test_client, second, "finish").status_code == 200


def test_a_rider_still_blocks_a_later_order_after_the_lock_holder_is_packed(test_client: TestClient, tick) -> None:
    set_limit(test_client, 2)
    first, second, third = (order(test_client, name) for name in ("A", "B", "C"))

    hanging_action(test_client, first, "start")
    tick()
    hanging_action(test_client, second, "start")
    tick()
    hanging_action(test_client, first, "finish")
    tick()
    assert hanging_action(test_client, second, "finish").status_code == 200  # B rides along with A
    tick()
    assert pack(test_client, first).status_code == 200
    tick()
    assert hanging_action(test_client, third, "start").status_code == 200
    tick()
    # B (hung with A, not with C) is still on the line unpacked → C waits for B.
    assert hanging_action(test_client, third, "finish").status_code == 409
    assert pack(test_client, second).status_code == 200
    tick()
    assert hanging_action(test_client, third, "finish").status_code == 200
