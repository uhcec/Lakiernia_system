import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.audit.models import AuditEvent
from app.shared.enums import StationId


class AuditEventActorRead(BaseModel):
    employee_id: int | None
    employee_name: str


class AuditEventRead(BaseModel):
    id: int
    event_type: str
    station_id: StationId
    work_order_id: int | None
    target_type: str | None
    target_id: int | None
    request_id: str | None
    summary: str
    details: dict[str, Any] | list[Any] | str | int | float | bool | None
    # Employees present at the station when the action happened (per-operator attribution).
    actors: list[AuditEventActorRead]
    created_at: datetime


class AuditEventListResponse(BaseModel):
    items: list[AuditEventRead]
    limit: int
    offset: int


def build_audit_event_read(event: AuditEvent) -> AuditEventRead:
    return AuditEventRead(
        id=event.id,
        event_type=event.event_type,
        station_id=event.station_id,
        work_order_id=event.work_order_id,
        target_type=event.target_type,
        target_id=event.target_id,
        request_id=event.request_id,
        summary=event.summary,
        details=_parse_details(event.details_json),
        actors=[
            AuditEventActorRead(employee_id=actor.employee_id, employee_name=actor.employee_name)
            for actor in event.actors
        ],
        created_at=event.created_at,
    )


def _parse_details(details_json: str | None):
    if details_json is None:
        return None
    try:
        return json.loads(details_json)
    except json.JSONDecodeError:
        return details_json
