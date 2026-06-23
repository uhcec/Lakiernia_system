from fastapi.testclient import TestClient

from tests.test_work_orders_api import create_work_order

OFFICE = {"X-Station-Id": "OFFICE"}


def _create_foil(test_client: TestClient, **overrides: object):
    payload = {"name": "Złoty dąb", "code": "FOIL-001", "supplier": "Decoral S.p.A."}
    payload.update(overrides)
    return test_client.post("/foils", json=payload, headers=OFFICE)


def test_create_foil_returns_zero_usage(test_client: TestClient) -> None:
    response = _create_foil(test_client, notes="Drobny słój")
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Złoty dąb"
    assert body["code"] == "FOIL-001"
    assert body["supplier"] == "Decoral S.p.A."
    assert body["notes"] == "Drobny słój"
    assert body["usage_count"] == 0


def test_create_foil_rejects_duplicate_code_case_insensitive(test_client: TestClient) -> None:
    assert _create_foil(test_client, code="FOIL-7").status_code == 201
    duplicate = _create_foil(test_client, name="Inna", code="foil-7")
    assert duplicate.status_code == 409


def test_create_foil_rejected_from_wrong_station(test_client: TestClient) -> None:
    response = test_client.post(
        "/foils",
        json={"name": "Nieuprawniona", "code": "X1"},
        headers={"X-Station-Id": "PACKING"},
    )
    assert response.status_code == 403


def test_list_foils_supports_search_by_name_and_code(test_client: TestClient) -> None:
    _create_foil(test_client, name="Orzech", code="ORZ-1")
    _create_foil(test_client, name="Mahoń", code="MAH-1")

    by_name = test_client.get("/foils", params={"search": "orze"})
    assert by_name.status_code == 200
    assert [item["code"] for item in by_name.json()["items"]] == ["ORZ-1"]

    by_code = test_client.get("/foils", params={"search": "MAH"})
    assert [item["name"] for item in by_code.json()["items"]] == ["Mahoń"]


def test_update_and_delete_foil(test_client: TestClient) -> None:
    foil_id = _create_foil(test_client).json()["id"]

    updated = test_client.patch(
        f"/foils/{foil_id}",
        json={"name": "Złoty dąb premium", "supplier": "Nowy dostawca"},
        headers=OFFICE,
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Złoty dąb premium"
    assert updated.json()["supplier"] == "Nowy dostawca"

    deleted = test_client.delete(f"/foils/{foil_id}", headers=OFFICE)
    assert deleted.status_code == 204
    assert test_client.get(f"/foils/{foil_id}").status_code == 404


def test_decoral_work_order_stores_and_shows_foil(test_client: TestClient) -> None:
    foil_id = _create_foil(test_client).json()["id"]

    order = create_work_order(test_client, coating_type="DECORAL", decoral_foil_id=foil_id)
    assert order.status_code == 201
    body = order.json()
    assert body["decoral_foil"] == {"id": foil_id, "name": "Złoty dąb", "code": "FOIL-001"}

    # Usage count rolls up on the registry.
    foil = test_client.get(f"/foils/{foil_id}").json()
    assert foil["usage_count"] == 1


def test_foil_rejected_on_ral_order(test_client: TestClient) -> None:
    foil_id = _create_foil(test_client).json()["id"]

    response = create_work_order(test_client, coating_type="RAL", decoral_foil_id=foil_id)
    assert response.status_code == 422


def test_unknown_foil_rejected_on_decoral_order(test_client: TestClient) -> None:
    response = create_work_order(test_client, coating_type="DECORAL", decoral_foil_id=999999)
    assert response.status_code == 422
