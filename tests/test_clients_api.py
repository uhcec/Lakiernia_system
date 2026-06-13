from fastapi.testclient import TestClient

from tests.test_work_orders_api import create_work_order

OFFICE = {"X-Station-Id": "OFFICE"}


def test_create_client_returns_zero_orders(test_client: TestClient) -> None:
    response = test_client.post(
        "/clients",
        json={"company_name": "Kowalski Sp. z o.o.", "contact_phone": "600100200", "nip": "1234563218"},
        headers=OFFICE,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["company_name"] == "Kowalski Sp. z o.o."
    assert body["contact_phone"] == "600100200"
    assert body["nip"] == "1234563218"
    assert body["order_count"] == 0


def test_create_client_rejects_duplicate_name_case_insensitive(test_client: TestClient) -> None:
    first = test_client.post("/clients", json={"company_name": "ACME"}, headers=OFFICE)
    assert first.status_code == 201

    duplicate = test_client.post("/clients", json={"company_name": "acme"}, headers=OFFICE)
    assert duplicate.status_code == 409


def test_create_client_rejected_from_wrong_station(test_client: TestClient) -> None:
    response = test_client.post(
        "/clients",
        json={"company_name": "Nieuprawniony"},
        headers={"X-Station-Id": "PACKING"},
    )
    assert response.status_code == 403


def test_list_clients_supports_search(test_client: TestClient) -> None:
    test_client.post("/clients", json={"company_name": "Stalbud"}, headers=OFFICE)
    test_client.post("/clients", json={"company_name": "Drewmax"}, headers=OFFICE)

    response = test_client.get("/clients", params={"search": "stal"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["company_name"] == "Stalbud"


def test_client_detail_lists_orders_matched_by_company_name(test_client: TestClient) -> None:
    created = test_client.post(
        "/clients",
        json={"company_name": "ACME", "contact_phone": "111222333"},
        headers=OFFICE,
    )
    client_id = created.json()["id"]

    order_response = create_work_order(test_client, customer_name="ACME", title="Zlecenie ACME")
    assert order_response.status_code == 201

    # Order for a different company must not appear in this client's history.
    other = create_work_order(test_client, customer_name="Inny Klient", title="Obce zlecenie")
    assert other.status_code == 201

    detail = test_client.get(f"/clients/{client_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["contact_phone"] == "111222333"
    assert len(body["orders"]) == 1
    assert body["orders"][0]["title"] == "Zlecenie ACME"
    assert body["orders"][0]["status"]["value"]

    list_response = test_client.get("/clients")
    acme = next(item for item in list_response.json()["items"] if item["company_name"] == "ACME")
    assert acme["order_count"] == 1


def test_update_client_changes_phone_and_name(test_client: TestClient) -> None:
    created = test_client.post("/clients", json={"company_name": "Stara Nazwa"}, headers=OFFICE)
    client_id = created.json()["id"]

    response = test_client.patch(
        f"/clients/{client_id}",
        json={"company_name": "Nowa Nazwa", "contact_phone": "555666777", "nip": "5260001246"},
        headers=OFFICE,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["company_name"] == "Nowa Nazwa"
    assert body["contact_phone"] == "555666777"
    assert body["nip"] == "5260001246"


def test_delete_client_returns_no_content(test_client: TestClient) -> None:
    created = test_client.post("/clients", json={"company_name": "Do usunięcia"}, headers=OFFICE)
    client_id = created.json()["id"]

    response = test_client.delete(f"/clients/{client_id}", headers=OFFICE)
    assert response.status_code == 204

    detail = test_client.get(f"/clients/{client_id}")
    assert detail.status_code == 404
