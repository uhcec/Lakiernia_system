import pytest
from sqlalchemy.orm import Session

from app.audit.context import parse_station_id
from app.audit.models import AuditEvent
from app.shared.enums import StationId
from app.shared.exceptions import InvalidStationIdentityError


def test_station_header_parser_accepts_known_values_and_normalizes_separators() -> None:
    assert parse_station_id("PACKING") == StationId.PACKING
    assert parse_station_id("manual-production") == StationId.MANUAL_PRODUCTION
    assert parse_station_id("  surface_preparation  ") == StationId.SURFACE_PREPARATION


def test_station_header_parser_defaults_missing_value_to_unknown() -> None:
    assert parse_station_id(None) == StationId.UNKNOWN
    assert parse_station_id("   ") == StationId.UNKNOWN


def test_station_header_parser_rejects_invalid_value() -> None:
    with pytest.raises(InvalidStationIdentityError) as exc_info:
        parse_station_id("warehouse")

    assert str(exc_info.value) == "Invalid station identity: warehouse."


def test_audit_event_persists_station_identity(db_session: Session) -> None:
    event = AuditEvent(
        event_type="work_order.created",
        station_id=StationId.OFFICE,
        target_type="work_order",
        target_id=123,
        summary="Created work order WO-2026-1001.",
        details_json='{"order_number":"WO-2026-1001"}',
    )

    db_session.add(event)
    db_session.commit()

    persisted = db_session.get(AuditEvent, event.id)

    assert persisted is not None
    assert persisted.station_id == StationId.OFFICE
    assert persisted.event_type == "work_order.created"
    assert persisted.target_type == "work_order"
    assert persisted.created_at is not None