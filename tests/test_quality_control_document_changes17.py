"""Regression tests for CHANGES #17: the QC card's Excel-COM → PDF conversion is a deliberate
Windows+Excel hosting constraint (owner D1/D6, 2026-07-11) — but on a host without Excel (the
Linux dev VPS) the endpoint used to die with a raw 500 (`ModuleNotFoundError: pythoncom` in the
worker). It must answer with a controlled Polish 503 instead."""

from __future__ import annotations

import app.work_orders.service as work_orders_service_module


def build_create_payload(title: str) -> dict:
    return {
        "title": title,
        "coating_type": "RAL",
        "total_quantity": 5,
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


def create_order(client) -> int:
    response = client.post("/work-orders", json=build_create_payload("QC document order"))
    assert response.status_code == 201, response.text
    return response.json()["id"]


class _UnavailableConverter:
    """What _get_excel_pdf_converter yields on a host without Windows/Excel/pywin32."""

    def convert(self, xlsx_path, pdf_path, timeout: float = 60.0) -> None:
        raise RuntimeError(
            "Generowanie dokumentu wymaga systemu Windows z zainstalowanym pakietem Excel i biblioteką pywin32."
        )


class _CrashingConverter:
    """A raw COM failure mid-conversion (Excel crashed, file locked) — an arbitrary exception."""

    def convert(self, xlsx_path, pdf_path, timeout: float = 60.0) -> None:
        raise ValueError("COM error 0x800A03EC")


def test_qc_document_returns_controlled_503_when_excel_unavailable(test_client, monkeypatch):
    order_id = create_order(test_client)
    monkeypatch.setattr(work_orders_service_module, "_get_excel_pdf_converter", lambda: _UnavailableConverter())

    response = test_client.get(f"/work-orders/{order_id}/quality-control-document")

    assert response.status_code == 503, response.text
    detail = response.json()["detail"]
    # The converter's Polish operator message is surfaced, never a raw traceback.
    assert "Windows" in detail and "Excel" in detail


def test_qc_document_wraps_raw_com_errors_in_polish_503(test_client, monkeypatch):
    order_id = create_order(test_client)
    monkeypatch.setattr(work_orders_service_module, "_get_excel_pdf_converter", lambda: _CrashingConverter())

    response = test_client.get(f"/work-orders/{order_id}/quality-control-document")

    assert response.status_code == 503, response.text
    detail = response.json()["detail"]
    assert "karty kontroli jakości" in detail
    assert "COM error" not in detail  # English internals never reach the operator
