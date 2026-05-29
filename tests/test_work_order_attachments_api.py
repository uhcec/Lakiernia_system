from io import BytesIO

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.core.config import get_work_order_attachments_path
from app.shared.exceptions import ResourceNotFoundError
from app.work_orders.models import WorkOrderAttachment
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import WorkOrderCreate
from app.work_orders.service import WorkOrderService


def build_create_payload(**overrides: object) -> dict:
    payload = {
        "title": "Zlecenie z załącznikiem",
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
    return payload


def create_work_order(test_client: TestClient, **overrides: object) -> dict:
    response = test_client.post("/work-orders", json=build_create_payload(**overrides))
    assert response.status_code == 201
    return response.json()


def upload_pdf(
    test_client: TestClient,
    work_order_id: int,
    *,
    filename: str = "specyfikacja.pdf",
    content: bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF",
    content_type: str = "application/pdf",
    attachment_type: str | None = None,
    description: str | None = None,
):
    data: dict[str, str] = {}
    if attachment_type is not None:
        data["attachment_type"] = attachment_type
    if description is not None:
        data["description"] = description

    return test_client.post(
        f"/work-orders/{work_order_id}/attachments",
        data=data,
        files={"file": (filename, BytesIO(content), content_type)},
    )


def test_upload_pdf_attachment(test_client: TestClient) -> None:
    created = create_work_order(test_client)

    response = upload_pdf(
        test_client,
        created["id"],
        attachment_type="SPEC",
        description="Główna specyfikacja",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["work_order_id"] == created["id"]
    assert body["original_filename"] == "specyfikacja.pdf"
    assert body["content_type"] == "application/pdf"
    assert body["file_size"] > 0
    assert body["attachment_type"] == "SPEC"
    assert body["description"] == "Główna specyfikacja"
    assert body["storage_path"].endswith(".pdf")


def test_reject_non_pdf_attachment(test_client: TestClient) -> None:
    created = create_work_order(test_client)

    response = upload_pdf(
        test_client,
        created["id"],
        filename="notatka.txt",
        content=b"plain text",
        content_type="text/plain",
    )

    assert response.status_code == 415
    assert response.json()["detail"] == "Dozwolone są tylko pliki PDF."


def test_reject_fake_pdf_with_application_pdf_content_type(test_client: TestClient) -> None:
    created = create_work_order(test_client)

    response = upload_pdf(
        test_client,
        created["id"],
        filename="fake.pdf",
        content=b"not-a-real-pdf",
        content_type="application/pdf",
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Przesłany plik nie jest prawidłowym PDF."

    list_response = test_client.get(f"/work-orders/{created['id']}/attachments")
    assert list_response.status_code == 200
    assert list_response.json() == []


def test_accept_pdf_with_real_header(test_client: TestClient) -> None:
    created = create_work_order(test_client)

    response = upload_pdf(
        test_client,
        created["id"],
        filename="real-header.pdf",
        content=b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF",
        content_type="application/pdf",
        attachment_type="SPEC",
        description="Zweryfikowany PDF",
    )

    assert response.status_code == 201
    assert response.json()["original_filename"] == "real-header.pdf"
    assert response.json()["attachment_type"] == "SPEC"
    assert response.json()["description"] == "Zweryfikowany PDF"


def test_list_attachments(test_client: TestClient) -> None:
    created = create_work_order(test_client)
    first = upload_pdf(test_client, created["id"], filename="a.pdf", attachment_type="A")
    second = upload_pdf(test_client, created["id"], filename="b.pdf", attachment_type="B")
    assert first.status_code == 201
    assert second.status_code == 201

    response = test_client.get(f"/work-orders/{created['id']}/attachments")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    filenames = {item["original_filename"] for item in body}
    assert filenames == {"a.pdf", "b.pdf"}


def test_download_attachment(test_client: TestClient) -> None:
    created = create_work_order(test_client)
    uploaded = upload_pdf(test_client, created["id"], filename="instrukcja.pdf")
    attachment_id = uploaded.json()["id"]

    response = test_client.get(f"/work-orders/{created['id']}/attachments/{attachment_id}/download")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "instrukcja.pdf" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF-1.4")


def test_delete_attachment(test_client: TestClient) -> None:
    created = create_work_order(test_client)
    uploaded = upload_pdf(test_client, created["id"], filename="usun.pdf")
    attachment_id = uploaded.json()["id"]

    delete_response = test_client.delete(f"/work-orders/{created['id']}/attachments/{attachment_id}")
    list_response = test_client.get(f"/work-orders/{created['id']}/attachments")
    download_response = test_client.get(f"/work-orders/{created['id']}/attachments/{attachment_id}/download")

    assert delete_response.status_code == 204
    assert list_response.status_code == 200
    assert list_response.json() == []
    assert download_response.status_code == 404


def test_cannot_access_attachment_from_another_order(test_client: TestClient) -> None:
    first_order = create_work_order(test_client, title="Pierwsze")
    second_order = create_work_order(test_client, title="Drugie")
    uploaded = upload_pdf(test_client, first_order["id"], filename="tajne.pdf")
    attachment_id = uploaded.json()["id"]

    list_response = test_client.get(f"/work-orders/{second_order['id']}/attachments")
    download_response = test_client.get(f"/work-orders/{second_order['id']}/attachments/{attachment_id}/download")
    delete_response = test_client.delete(f"/work-orders/{second_order['id']}/attachments/{attachment_id}")

    assert list_response.status_code == 200
    assert list_response.json() == []
    assert download_response.status_code == 404
    assert delete_response.status_code == 404


def test_download_rejects_attachment_storage_path_outside_root(db_session: Session) -> None:
    service = WorkOrderService(WorkOrderRepository(db_session))
    created = service.create_work_order(WorkOrderCreate.model_validate(build_create_payload()))
    root_path = get_work_order_attachments_path()
    outside_path = root_path.parent / "outside.pdf"
    outside_path.write_bytes(b"%PDF-1.4")

    attachment = WorkOrderAttachment(
        work_order_id=created.id,
        original_filename="outside.pdf",
        stored_filename="outside.pdf",
        storage_path="../outside.pdf",
        content_type="application/pdf",
        file_size=8,
    )
    db_session.add(attachment)
    db_session.commit()

    with pytest.raises(ResourceNotFoundError):
        service.get_attachment_download(created.id, attachment.id)


def test_delete_missing_or_escaped_attachment_file_removes_db_row_without_touching_outside_file(db_session: Session) -> None:
    service = WorkOrderService(WorkOrderRepository(db_session))
    created = service.create_work_order(WorkOrderCreate.model_validate(build_create_payload()))
    root_path = get_work_order_attachments_path()
    outside_path = root_path.parent / "outside-delete.pdf"
    outside_path.write_bytes(b"%PDF-1.4")

    missing_file_attachment = WorkOrderAttachment(
        work_order_id=created.id,
        original_filename="missing.pdf",
        stored_filename="missing.pdf",
        storage_path=f"{created.id}/missing.pdf",
        content_type="application/pdf",
        file_size=8,
    )
    escaped_file_attachment = WorkOrderAttachment(
        work_order_id=created.id,
        original_filename="outside-delete.pdf",
        stored_filename="outside-delete.pdf",
        storage_path="../outside-delete.pdf",
        content_type="application/pdf",
        file_size=8,
    )
    db_session.add_all([missing_file_attachment, escaped_file_attachment])
    db_session.commit()
    missing_file_attachment_id = missing_file_attachment.id
    escaped_file_attachment_id = escaped_file_attachment.id

    service.delete_attachment(created.id, missing_file_attachment_id)
    service.delete_attachment(created.id, escaped_file_attachment_id)

    assert db_session.get(WorkOrderAttachment, missing_file_attachment_id) is None
    assert db_session.get(WorkOrderAttachment, escaped_file_attachment_id) is None
    assert outside_path.exists()