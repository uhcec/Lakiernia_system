"""WZ (wydanie z magazynu) document generation — validation, row building, numbering, cell mapping.

The final PDF step needs Excel/COM (Windows only) and is not exercised here; ``_render_wz_pdf`` is
stubbed so the office-facing logic (which orders are eligible, how lines are built, how the workbook is
filled, how WZ numbers are allocated) is testable on any platform.
"""
from datetime import date, datetime
from io import BytesIO
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.context import StationContext
from app.audit.models import AuditEvent
from app.process.enums import CoatingType, ProcessDisplayStatus
from app.shared import clock
from app.shared.enums import StationId
from app.shared.exceptions import (
    DocumentGenerationUnavailableError,
    InvalidWorkOrderDataError,
    ResourceNotFoundError,
)
from app.work_orders.models import WzNumberCounter
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import WorkOrderCreate, WzDocumentRequest
from app.work_orders.service import WorkOrderService
from app.work_orders.wz_number_allocator import WzNumberAllocator

OFFICE = StationContext(station_id=StationId.OFFICE)


def _service(db_session: Session) -> WorkOrderService:
    return WorkOrderService(WorkOrderRepository(db_session))


def _create_order(service: WorkOrderService, **overrides: object):
    payload = {
        "title": "Zlecenie",
        "coating_type": CoatingType.RAL,
        "total_quantity": 100,
        "customer_name": "ACME",
        "ral_code": "RAL 7016",
        "paint_code": "P-7016",
        "paint_producer": "AkzoNobel",
        "received_date": date(2026, 6, 1),
        "planned_pickup_date": date(2026, 6, 10),
        "total_area_m2": 24.0,
        "profiles_quantity": 60,
        "profiles_to_count": False,
        "accessories_quantity": 40,
        "accessories_to_count": False,
    }
    payload.update(overrides)
    created = service.create_work_order(
        WorkOrderCreate.model_validate(payload), station_context=OFFICE
    )
    return service.repository.get_by_id(created.id)


def _force_ready(service: WorkOrderService) -> None:
    """Treat every order as gotowe do wydania (bypasses driving the whole process to READY)."""
    service.process_service.get_display_status = lambda work_order: ProcessDisplayStatus.READY  # type: ignore[method-assign]


# --- WZ number allocator -------------------------------------------------------------------------

def test_wz_number_resets_per_year(db_session: Session) -> None:
    allocator = WzNumberAllocator(db_session)
    with patch.object(clock, "now", return_value=datetime(2026, 7, 11, 10, 0, 0)):
        assert [allocator.allocate() for _ in range(3)] == ["1/2026", "2/2026", "3/2026"]
    with patch.object(clock, "now", return_value=datetime(2027, 1, 2, 9, 0, 0)):
        assert allocator.allocate() == "1/2027"
    with patch.object(clock, "now", return_value=datetime(2026, 12, 31, 23, 0, 0)):
        assert allocator.allocate() == "4/2026"  # 2026 continues independently of 2027


# --- order reference (NR ZAMÓWIENIA cell) --------------------------------------------------------

def test_order_reference_includes_both_numbers(db_session: Session) -> None:
    service = _service(db_session)
    with_external = _create_order(service, external_order_number="Z-123")
    without_external = _create_order(service, external_order_number=None)
    assert service._wz_order_reference(with_external) == (
        f"Zam. klienta Z-123 (nasze {with_external.order_number})"
    )
    assert service._wz_order_reference(without_external) == without_external.order_number


# --- line groups ---------------------------------------------------------------------------------

def test_line_groups_split_profiles_and_accessories(db_session: Session) -> None:
    service = _service(db_session)
    order = _create_order(service, profiles_quantity=60, accessories_quantity=40)
    groups = service._build_wz_line_groups([order], baskets_count=None)
    assert groups[0]["rows"] == [("Profile", 60), ("Akcesoria", 40)]
    assert groups[0]["color"] == "RAL 7016"


def test_line_groups_skip_zero_and_fallback_to_elementy(db_session: Session) -> None:
    service = _service(db_session)
    only_profiles = _create_order(service, profiles_quantity=100, accessories_quantity=0)
    groups = service._build_wz_line_groups([only_profiles], baskets_count=None)
    assert groups[0]["rows"] == [("Profile", 100)]

    unknown_split = _create_order(
        service,
        total_quantity=70,
        profiles_quantity=None,
        profiles_to_count=True,
        accessories_quantity=None,
        accessories_to_count=True,
    )
    groups = service._build_wz_line_groups([unknown_split], baskets_count=None)
    assert groups[0]["rows"] == [("Elementy", 70)]


def test_line_groups_append_baskets_row(db_session: Session) -> None:
    service = _service(db_session)
    order = _create_order(service)
    groups = service._build_wz_line_groups([order], baskets_count=4)
    assert groups[-1] == {"color": None, "order_ref": None, "rows": [("Kosze dłużycowe", 4)]}
    # 0 / None baskets → no trailing row
    assert service._build_wz_line_groups([order], baskets_count=0)[-1]["rows"][0][0] != "Kosze dłużycowe"


# --- workbook cell mapping (no COM) --------------------------------------------------------------

def test_workbook_maps_header_and_lines(db_session: Session) -> None:
    service = _service(db_session)
    order = _create_order(service, customer_name="ACME", external_order_number="Z-9")
    groups = service._build_wz_line_groups([order], baskets_count=2)
    with patch.object(clock, "now", return_value=datetime(2026, 7, 11, 8, 0, 0)):
        wb = service._build_wz_workbook("ACME", "7/2026", groups)
    ws = wb.active
    assert ws["H1"].value == "ACME"          # Odbiorca
    assert ws["H4"].value == "7/2026"        # WZ number
    assert ws["E31"].value == "11.07.2026"   # date dd.mm.yyyy
    assert ws["H3"].value is None            # address left blank (handwritten)
    # rows 7 (Profile) + 8 (Akcesoria) share order group; row 9 = baskets
    assert (ws["C7"].value, ws["D7"].value, ws["F7"].value, ws["G7"].value) == (1, "Profile", "szt", 60)
    assert (ws["C8"].value, ws["D8"].value, ws["G8"].value) == (2, "Akcesoria", 40)
    assert ws["E7"].value == "RAL 7016"
    assert ws["H7"].value == f"Zam. klienta Z-9 (nasze {order.order_number})"
    assert (ws["D9"].value, ws["G9"].value) == ("Kosze dłużycowe", 2)
    # Kolor + NR ZAMÓWIENIA merged across the order's two rows
    merged = {str(m) for m in ws.merged_cells.ranges}
    assert "E7:E8" in merged and "H7:H8" in merged


# --- generate_wz_document: validation ------------------------------------------------------------

def test_generate_rejects_non_office_station(db_session: Session) -> None:
    service = _service(db_session)
    order = _create_order(service)
    _force_ready(service)
    with pytest.raises(Exception):
        service.generate_wz_document(
            WzDocumentRequest(work_order_ids=[order.id]),
            station_context=StationContext(station_id=StationId.HANGING),
        )


def test_schema_rejects_empty_selection() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        WzDocumentRequest(work_order_ids=[])


def test_collect_guards_empty_and_missing(db_session: Session) -> None:
    service = _service(db_session)
    _force_ready(service)
    with pytest.raises(InvalidWorkOrderDataError):
        service._collect_wz_orders([])
    with pytest.raises(ResourceNotFoundError):
        service.generate_wz_document(WzDocumentRequest(work_order_ids=[999]), station_context=OFFICE)


def test_generate_rejects_mixed_customers(db_session: Session) -> None:
    service = _service(db_session)
    a = _create_order(service, customer_name="ACME")
    b = _create_order(service, customer_name="Inny Klient")
    _force_ready(service)
    with pytest.raises(InvalidWorkOrderDataError):
        service.generate_wz_document(
            WzDocumentRequest(work_order_ids=[a.id, b.id]), station_context=OFFICE
        )


def test_generate_rejects_non_ready(db_session: Session) -> None:
    service = _service(db_session)
    ready = _create_order(service)
    not_ready = _create_order(service)
    service.process_service.get_display_status = (  # type: ignore[method-assign]
        lambda work_order: ProcessDisplayStatus.READY
        if work_order.id == ready.id
        else ProcessDisplayStatus.PACKING
    )
    with pytest.raises(InvalidWorkOrderDataError):
        service.generate_wz_document(
            WzDocumentRequest(work_order_ids=[ready.id, not_ready.id]), station_context=OFFICE
        )


def test_generate_rejects_over_capacity(db_session: Session) -> None:
    service = _service(db_session)
    order = _create_order(service)
    _force_ready(service)
    # 24 lines > 23-slot grid
    service._build_wz_line_groups = lambda orders, *, baskets_count: [  # type: ignore[method-assign]
        {"color": "RAL 7016", "order_ref": "x", "rows": [("Profile", 1)]} for _ in range(24)
    ]
    with pytest.raises(InvalidWorkOrderDataError):
        service.generate_wz_document(
            WzDocumentRequest(work_order_ids=[order.id]), station_context=OFFICE
        )


# --- generate_wz_document: success path (PDF render stubbed) --------------------------------------

def test_generate_allocates_number_commits_and_audits(db_session: Session) -> None:
    service = _service(db_session)
    order = _create_order(service, customer_name="ACME")
    _force_ready(service)
    rendered: dict = {}

    def fake_render(customer_name, wz_number, groups):
        rendered.update(customer_name=customer_name, wz_number=wz_number, groups=groups)
        return BytesIO(b"%PDF-1.4 fake")

    service._render_wz_pdf = fake_render  # type: ignore[method-assign]
    with patch.object(clock, "now", return_value=datetime(2026, 7, 11, 8, 0, 0)):
        buffer, filename = service.generate_wz_document(
            WzDocumentRequest(work_order_ids=[order.id], baskets_count=3), station_context=OFFICE
        )

    assert filename == "WZ_1_2026.pdf"
    assert buffer.getvalue() == b"%PDF-1.4 fake"
    assert rendered["wz_number"] == "1/2026"
    assert rendered["customer_name"] == "ACME"
    # counter persisted (committed)
    counter = db_session.execute(select(WzNumberCounter).where(WzNumberCounter.year == 2026)).scalar_one()
    assert counter.last_value == 1
    # audit event written; generation does NOT release the order
    event = db_session.execute(
        select(AuditEvent).where(AuditEvent.event_type == "work_order.wz_document_generated")
    ).scalar_one()
    assert event.details_json and "1/2026" in event.details_json
    assert order.released_to_client_at is None


def test_failed_render_does_not_consume_number(db_session: Session) -> None:
    service = _service(db_session)
    order = _create_order(service, customer_name="ACME")
    _force_ready(service)

    def boom(customer_name, wz_number, groups):
        raise RuntimeError("Excel missing")

    service._render_wz_pdf = boom  # type: ignore[method-assign]
    with patch.object(clock, "now", return_value=datetime(2026, 7, 11, 8, 0, 0)):
        # A failed render surfaces as a controlled 503 (like the QC card), and rolls the number back.
        with pytest.raises(DocumentGenerationUnavailableError):
            service.generate_wz_document(
                WzDocumentRequest(work_order_ids=[order.id]), station_context=OFFICE
            )
    # rollback → no counter row consumed
    counter = db_session.execute(
        select(WzNumberCounter).where(WzNumberCounter.year == 2026)
    ).scalar_one_or_none()
    assert counter is None or counter.last_value == 0


# --- API endpoint (route wiring + station gating; PDF render stubbed) ------------------------------

def _make_ready_and_stub_render(monkeypatch) -> None:
    from io import BytesIO as _BytesIO

    from app.process.service import ProcessService

    monkeypatch.setattr(
        ProcessService, "get_display_status", lambda self, work_order: ProcessDisplayStatus.READY
    )
    monkeypatch.setattr(
        WorkOrderService,
        "_render_wz_pdf",
        lambda self, customer_name, wz_number, groups: _BytesIO(b"%PDF-1.4 stub"),
    )


def test_wz_endpoint_returns_pdf_for_office(test_client, monkeypatch) -> None:
    from test_work_orders_api import create_work_order

    created = create_work_order(test_client, customer_name="ACME", profiles_quantity=10)
    assert created.status_code == 201
    order_id = created.json()["id"]
    _make_ready_and_stub_render(monkeypatch)

    with patch.object(clock, "now", return_value=datetime(2026, 7, 11, 8, 0, 0)):
        response = test_client.post(
            "/work-orders/wz-document",
            json={"work_order_ids": [order_id], "baskets_count": 3},
            headers={"X-Station-Id": "OFFICE"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "WZ_1_2026.pdf" in response.headers.get("content-disposition", "")
    assert response.content == b"%PDF-1.4 stub"


def test_wz_endpoint_rejects_non_office_station(test_client, monkeypatch) -> None:
    from test_work_orders_api import create_work_order

    created = create_work_order(test_client, customer_name="ACME", profiles_quantity=10)
    order_id = created.json()["id"]
    _make_ready_and_stub_render(monkeypatch)

    response = test_client.post(
        "/work-orders/wz-document",
        json={"work_order_ids": [order_id]},
        headers={"X-Station-Id": "HANGING"},
    )
    assert response.status_code >= 400
