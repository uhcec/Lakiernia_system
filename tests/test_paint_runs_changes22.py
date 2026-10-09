"""CHANGES #22/#23 — automatic paint consumption is entered once per paint run, split by m².

Owner decisions (2026-10-09): orders with the same paint hung back-to-back on the automatic line form
one run; consumption is entered after the run's orders finished hanging and split onto the orders by
m²; entry is write-once; correction rounds join runs like ordinary orders. #23: only the LAST order of
an open run waits — its submitted packing is parked until the consumption is entered, then completes —
and while parked it frees the packing station and the automatic line (the line keeps running).
"""

import pytest
from fastapi.testclient import TestClient

from app.process.paint_runs import allocate_by_area
from tests.test_process_api import advance_to_hanging, complete_packing_request, ensure_paint_stock


AUTOMAT = {"X-Station-Id": "AUTOMATIC_PRODUCTION"}
WHITE = {"ral_code": "RAL 9016", "paint_producer": "Tiger", "paint_code": "T-9016"}
GREY = {"ral_code": "RAL 7016", "paint_producer": "AkzoNobel", "paint_code": "P-7016"}


def create_automatic_order(
    test_client: TestClient,
    *,
    title: str,
    paint: dict,
    area_m2: float,
    total_quantity: int = 10,
) -> dict:
    payload = {
        "title": title,
        "coating_type": "RAL",
        "total_quantity": total_quantity,
        "customer_name": "ACME",
        **paint,
        "received_date": "2026-05-25",
        "planned_pickup_date": "2026-06-01",
        "total_area_m2": area_m2,
        "profiles_to_count": True,
        "accessories_to_count": True,
    }
    created = test_client.post("/work-orders", json=payload)
    assert created.status_code == 201, created.text
    planned = test_client.post(f"/manager/work-orders/{created.json()['id']}/plan", json={"production_type": "AUTOMATIC"})
    assert planned.status_code == 200, planned.text
    return created.json()


def hang(test_client: TestClient, work_order_id: int, *, finish: bool = True, pack: bool = True) -> None:
    """Hang an order; by default also pack it all-OK, which frees the automatic line for the next one."""
    advance_to_hanging(test_client, work_order_id)
    started = test_client.post(f"/process/work-orders/{work_order_id}/stages/HANGING/start")
    assert started.status_code == 200, started.text
    if not finish:
        return
    finished = test_client.post(f"/process/work-orders/{work_order_id}/stages/HANGING/finish")
    assert finished.status_code == 200, finished.text
    if pack:
        active = test_client.get(f"/work-orders/{work_order_id}").json()["current_active_quantity"]
        packed = complete_packing_request(
            test_client,
            work_order_id,
            counted_quantity=active,
            ok_quantity=active,
            correction_quantity=0,
            close_paint_runs=False,
        )
        assert packed.status_code == 200, packed.text


def status_of(test_client: TestClient, work_order_id: int) -> str:
    return test_client.get(f"/work-orders/{work_order_id}").json()["process_status"]["value"]


def open_runs(test_client: TestClient) -> list[dict]:
    response = test_client.get("/process/paint-runs/open")
    assert response.status_code == 200
    return response.json()["runs"]


def record(test_client: TestClient, run_id: int, kg: float, headers: dict | None = None):
    return test_client.post(f"/process/paint-runs/{run_id}/consumption", json={"consumed_kg": kg}, headers=headers or AUTOMAT)


def test_same_paint_back_to_back_forms_one_run_and_kg_splits_by_area(test_client: TestClient) -> None:
    ensure_paint_stock(test_client, **WHITE, target_quantity_kg=50.0)
    first = create_automatic_order(test_client, title="Biały 1", paint=WHITE, area_m2=30.0)
    second = create_automatic_order(test_client, title="Biały 2", paint=WHITE, area_m2=10.0)
    hang(test_client, first["id"])
    hang(test_client, second["id"])

    [run] = open_runs(test_client)
    assert [member["work_order_id"] for member in run["members"]] == [first["id"], second["id"]]
    assert run["total_area_m2"] == 40.0
    assert run["is_current"] is True

    response = record(test_client, run["id"], 12.0)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["consumed_kg"] == 12.0
    assert [member["allocated_kg"] for member in body["members"]] == [9.0, 3.0]
    assert open_runs(test_client) == []
    # Each order reports its m² share; stock went down once by the whole run.
    assert test_client.get(f"/work-orders/{first['id']}").json()["consumed_paint_quantity_kg"] == 9.0
    assert test_client.get(f"/work-orders/{second['id']}").json()["consumed_paint_quantity_kg"] == 3.0
    lookup = test_client.get("/paints/lookup", params=WHITE).json()
    assert lookup["current_quantity_kg"] == 38.0
    movements = test_client.get(f"/paints/{lookup['paint_id']}/movements").json()["items"]
    consumption = [movement for movement in movements if movement["movement_type"]["value"] == "AUTOMATIC_CONSUMPTION"]
    assert len(consumption) == 1
    assert consumption[0]["quantity_delta_kg"] == -12.0
    assert consumption[0]["work_order_id"] is None


def test_paint_change_starts_a_new_run_and_flags_the_previous_one(test_client: TestClient) -> None:
    white = create_automatic_order(test_client, title="Biały", paint=WHITE, area_m2=20.0)
    grey = create_automatic_order(test_client, title="Grafit", paint=GREY, area_m2=20.0)
    hang(test_client, white["id"])
    # Nothing blocks the next paint even though the white run has no consumption yet (owner: alarm only).
    hang(test_client, grey["id"])

    runs = open_runs(test_client)
    assert [run["ral_code"] for run in runs] == ["RAL 9016", "RAL 7016"]
    assert runs[0]["is_current"] is False  # paint already changed → overdue
    assert runs[1]["is_current"] is True


def test_same_paint_after_a_closed_run_starts_a_new_run(test_client: TestClient) -> None:
    ensure_paint_stock(test_client, **WHITE, target_quantity_kg=50.0)
    first = create_automatic_order(test_client, title="Biały A", paint=WHITE, area_m2=20.0)
    second = create_automatic_order(test_client, title="Biały B", paint=WHITE, area_m2=20.0)
    hang(test_client, first["id"])
    [run] = open_runs(test_client)
    assert record(test_client, run["id"], 5.0).status_code == 200

    hang(test_client, second["id"])

    [new_run] = open_runs(test_client)
    assert new_run["id"] != run["id"]
    assert [member["work_order_id"] for member in new_run["members"]] == [second["id"]]


def test_consumption_is_refused_while_an_order_of_the_run_is_still_hanging(test_client: TestClient) -> None:
    ensure_paint_stock(test_client, **WHITE, target_quantity_kg=50.0)
    order = create_automatic_order(test_client, title="Biały w trakcie", paint=WHITE, area_m2=20.0)
    hang(test_client, order["id"], finish=False)
    [run] = open_runs(test_client)
    assert run["hanging_in_progress"] is True

    response = record(test_client, run["id"], 5.0)

    assert response.status_code == 409
    assert response.json()["detail"] == "Najpierw zakończ zawieszanie wszystkich zleceń z tej grupy, potem wpisz zużycie farby."


def test_consumption_is_write_once(test_client: TestClient) -> None:
    ensure_paint_stock(test_client, **WHITE, target_quantity_kg=50.0)
    order = create_automatic_order(test_client, title="Biały raz", paint=WHITE, area_m2=20.0)
    hang(test_client, order["id"])
    [run] = open_runs(test_client)

    assert record(test_client, run["id"], 5.0).status_code == 200
    second = record(test_client, run["id"], 6.0)

    assert second.status_code == 409
    assert "już zapisane" in second.json()["detail"]
    assert test_client.get("/paints/lookup", params=WHITE).json()["current_quantity_kg"] == 45.0


def test_undoing_a_hanging_start_takes_the_order_out_of_its_open_run(test_client: TestClient) -> None:
    order = create_automatic_order(test_client, title="Biały cofnięty", paint=WHITE, area_m2=20.0)
    hang(test_client, order["id"], finish=False)
    assert len(open_runs(test_client)) == 1

    undo = test_client.post(f"/process/work-orders/{order['id']}/stages/HANGING/reopen")

    assert undo.status_code == 200, undo.text
    assert open_runs(test_client) == []  # the emptied run is deleted


def test_only_the_last_order_of_a_run_waits_for_the_consumption(test_client: TestClient) -> None:
    # Owner's example: 4 orders in one paint — 1-3 close normally, the 4th waits for the painter's entry.
    ensure_paint_stock(test_client, **WHITE, target_quantity_kg=50.0)
    orders = [create_automatic_order(test_client, title=f"Biały {n}", paint=WHITE, area_m2=10.0) for n in range(1, 5)]
    for order in orders:
        hang(test_client, order["id"])

    assert [status_of(test_client, order["id"]) for order in orders[:3]] == ["READY", "READY", "READY"]
    assert status_of(test_client, orders[3]["id"]) != "READY"
    packing_card = next(
        row for row in test_client.get("/process/stages/PACKING/work-orders").json() if row["id"] == orders[3]["id"]
    )
    assert packing_card["can_complete_packing"] is False
    assert packing_card["packing_blocked_reason"].startswith("Spakowane — ostatnie zlecenie grupy farby RAL 9016")

    [run] = open_runs(test_client)
    assert record(test_client, run["id"], 8.0).status_code == 200

    # The parked packing completes with the packer's numbers — nobody re-enters anything.
    detail = test_client.get(f"/work-orders/{orders[3]['id']}").json()
    assert detail["process_status"]["value"] == "READY"
    assert detail["completed_quantity"] == 10


def test_a_parked_order_frees_the_line_so_the_next_paint_keeps_hanging(test_client: TestClient) -> None:
    white = create_automatic_order(test_client, title="Biały ostatni", paint=WHITE, area_m2=20.0)
    grey = create_automatic_order(test_client, title="Grafit dalej", paint=GREY, area_m2=20.0)
    hang(test_client, white["id"])  # packing submitted → parked (last of the white run)

    # Before #23 the white order would hold the automatic line until packed; now grey finishes hanging.
    hang(test_client, grey["id"], pack=False)

    assert status_of(test_client, white["id"]) != "READY"
    grey_card = next(row for row in test_client.get("/process/stages/PACKING/work-orders").json() if row["id"] == grey["id"])
    assert grey_card["is_being_packed"] is True  # the station went to grey, not to the parked white


def test_a_parked_order_closes_as_soon_as_a_same_paint_order_joins(test_client: TestClient) -> None:
    first = create_automatic_order(test_client, title="Biały przerwa 1", paint=WHITE, area_m2=20.0)
    second = create_automatic_order(test_client, title="Biały przerwa 2", paint=WHITE, area_m2=20.0)
    hang(test_client, first["id"])  # nothing else white hanging yet → parked
    assert status_of(test_client, first["id"]) != "READY"

    hang(test_client, second["id"], finish=False)  # same paint joins → first is no longer the last

    assert status_of(test_client, first["id"]) == "READY"


def test_freed_packing_goes_to_the_order_waiting_longest(test_client: TestClient) -> None:
    # Owner's live test 2026-10-09 deadlocked here: the station freed by A went to C (just started
    # hanging) instead of B (already waiting), so B could not pack and C could not finish hanging.
    a, b, c = (create_automatic_order(test_client, title=f"Kolejka {n}", paint=WHITE, area_m2=10.0) for n in "ABC")
    for order in (a, b, c):
        advance_to_hanging(test_client, order["id"])
    test_client.post(f"/process/work-orders/{a['id']}/stages/HANGING/start")
    test_client.post(f"/process/work-orders/{a['id']}/stages/HANGING/finish")
    test_client.post(f"/process/work-orders/{b['id']}/stages/HANGING/start")
    pack_a = complete_packing_request(test_client, a["id"], counted_quantity=10, ok_quantity=10, correction_quantity=0, close_paint_runs=False)
    assert pack_a.status_code == 200, pack_a.text
    assert test_client.post(f"/process/work-orders/{b['id']}/stages/HANGING/finish").status_code == 200
    test_client.post(f"/process/work-orders/{c['id']}/stages/HANGING/start")

    pack_b = complete_packing_request(test_client, b["id"], counted_quantity=10, ok_quantity=10, correction_quantity=0, close_paint_runs=False)

    assert pack_b.status_code == 200, pack_b.text  # no override needed any more
    assert status_of(test_client, b["id"]) == "READY"
    assert test_client.post(f"/process/work-orders/{c['id']}/stages/HANGING/finish").status_code == 200


def test_open_run_shows_the_paint_stock(test_client: TestClient) -> None:
    ensure_paint_stock(test_client, **WHITE, target_quantity_kg=0.0)
    order = create_automatic_order(test_client, title="Biały bez stanu", paint=WHITE, area_m2=20.0)
    hang(test_client, order["id"], pack=False)

    [run] = open_runs(test_client)

    assert run["paint_stock_kg"] == 0.0


def test_insufficient_stock_gives_a_polish_reason_and_records_nothing(test_client: TestClient) -> None:
    ensure_paint_stock(test_client, **WHITE, target_quantity_kg=50.0)
    order = create_automatic_order(test_client, title="Biały brak", paint=WHITE, area_m2=20.0)
    hang(test_client, order["id"])
    ensure_paint_stock(test_client, **WHITE, target_quantity_kg=2.0)
    [run] = open_runs(test_client)

    response = record(test_client, run["id"], 5.0)

    assert response.status_code == 409
    assert response.json()["detail"].startswith("Za mało farby na stanie magazynu")
    assert open_runs(test_client)[0]["closed_at"] is None


def test_only_the_automatic_production_station_records_consumption(test_client: TestClient) -> None:
    ensure_paint_stock(test_client, **WHITE, target_quantity_kg=50.0)
    order = create_automatic_order(test_client, title="Biały stanowisko", paint=WHITE, area_m2=20.0)
    hang(test_client, order["id"])
    [run] = open_runs(test_client)

    response = record(test_client, run["id"], 5.0, headers={"X-Station-Id": "HANGING"})

    assert response.status_code == 403


def test_next_in_queue_hint_tells_whether_the_run_continues(test_client: TestClient) -> None:
    first = create_automatic_order(test_client, title="Biały 1", paint=WHITE, area_m2=20.0)
    create_automatic_order(test_client, title="Biały 2", paint=WHITE, area_m2=20.0)
    hang(test_client, first["id"])

    [run] = open_runs(test_client)
    assert run["next_in_queue_same_paint"] is True


def test_a_correction_round_joins_a_run_and_rolls_up_on_the_order(test_client: TestClient) -> None:
    ensure_paint_stock(test_client, **WHITE, target_quantity_kg=50.0)
    order = create_automatic_order(test_client, title="Biały poprawka", paint=WHITE, area_m2=20.0)
    hang(test_client, order["id"], pack=False)
    [first_run] = open_runs(test_client)
    assert record(test_client, first_run["id"], 4.0).status_code == 200
    split = complete_packing_request(test_client, order["id"], counted_quantity=10, ok_quantity=8, correction_quantity=2)
    assert split.status_code == 200, split.text

    # The 2 returned pieces are re-planned and re-hung: a new run, weighted by 2 pieces of 2 m² each.
    test_client.post(f"/manager/work-orders/{order['id']}/plan", json={"production_type": "AUTOMATIC"})
    hang(test_client, order["id"])
    [second_run] = open_runs(test_client)
    assert second_run["members"][0]["area_m2"] == 4.0
    assert record(test_client, second_run["id"], 1.0).status_code == 200

    assert test_client.get(f"/work-orders/{order['id']}").json()["consumed_paint_quantity_kg"] == 5.0


@pytest.mark.parametrize(
    ("consumed", "areas", "expected"),
    [
        (12.0, [30.0, 10.0], [9.0, 3.0]),
        (10.0, [1.0, 1.0, 1.0], [3.333, 3.333, 3.334]),
        (6.0, [0.0, 0.0], [3.0, 3.0]),  # no usable m² → even split
    ],
)
def test_allocate_by_area(consumed: float, areas: list[float], expected: list[float]) -> None:
    shares = allocate_by_area(consumed, areas)
    assert shares == pytest.approx(expected)
    assert sum(shares) == pytest.approx(consumed)
