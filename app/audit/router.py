import csv
from datetime import datetime
from io import StringIO
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.audit.repository import AuditRepository
from app.audit.schemas import AuditEventListResponse, AuditEventRead, build_audit_event_read
from app.database.session import get_db_session
from app.shared.enums import StationId
from app.shared.exceptions import ResourceNotFoundError
from app.work_orders.repository import WorkOrderRepository

router = APIRouter(prefix="/audit", tags=["audit"])


def get_audit_repository(session: Annotated[Session, Depends(get_db_session)]) -> AuditRepository:
    return AuditRepository(session)


def get_work_order_repository(session: Annotated[Session, Depends(get_db_session)]) -> WorkOrderRepository:
    return WorkOrderRepository(session)


@router.get("/events", response_model=AuditEventListResponse)
def list_audit_events(
    audit_repository: Annotated[AuditRepository, Depends(get_audit_repository)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    work_order_id: Annotated[int | None, Query(ge=1)] = None,
    event_type: Annotated[str | None, Query(max_length=100)] = None,
    station_id: Annotated[StationId | None, Query()] = None,
    request_id: Annotated[str | None, Query(max_length=128)] = None,
    target_type: Annotated[str | None, Query(max_length=64)] = None,
    target_id: Annotated[int | None, Query(ge=1)] = None,
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
) -> AuditEventListResponse:
    events = audit_repository.list_events(
        limit=limit,
        offset=offset,
        work_order_id=work_order_id,
        event_type=event_type,
        station_id=station_id,
        request_id=request_id,
        target_type=target_type,
        target_id=target_id,
        created_from=created_from,
        created_to=created_to,
    )
    return AuditEventListResponse(
        items=[build_audit_event_read(event) for event in events],
        limit=limit,
        offset=offset,
    )


@router.get("/events/export.csv")
def export_audit_events_csv(
    audit_repository: Annotated[AuditRepository, Depends(get_audit_repository)],
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
    offset: Annotated[int, Query(ge=0)] = 0,
    work_order_id: Annotated[int | None, Query(ge=1)] = None,
    event_type: Annotated[str | None, Query(max_length=100)] = None,
    station_id: Annotated[StationId | None, Query()] = None,
    request_id: Annotated[str | None, Query(max_length=128)] = None,
    target_type: Annotated[str | None, Query(max_length=64)] = None,
    target_id: Annotated[int | None, Query(ge=1)] = None,
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
) -> Response:
    events = audit_repository.list_events(
        limit=limit,
        offset=offset,
        work_order_id=work_order_id,
        event_type=event_type,
        station_id=station_id,
        request_id=request_id,
        target_type=target_type,
        target_id=target_id,
        created_from=created_from,
        created_to=created_to,
    )
    return Response(
        content=_build_audit_csv(events),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="audit-events.csv"'},
    )


@router.get("/work-orders/{work_order_id}/events", response_model=list[AuditEventRead])
def list_work_order_audit_events(
    work_order_id: int,
    audit_repository: Annotated[AuditRepository, Depends(get_audit_repository)],
    work_order_repository: Annotated[WorkOrderRepository, Depends(get_work_order_repository)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AuditEventRead]:
    if work_order_repository.get_by_id(work_order_id) is None:
        raise ResourceNotFoundError(f"Work order {work_order_id} not found.")

    return [
        build_audit_event_read(event)
        for event in audit_repository.list_for_work_order(work_order_id, limit=limit, offset=offset)
    ]


def _build_audit_csv(events) -> str:
    output = StringIO()
    fieldnames = [
        "id",
        "created_at",
        "event_type",
        "station_id",
        "request_id",
        "work_order_id",
        "target_type",
        "target_id",
        "summary",
        "details_json",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for event in events:
        writer.writerow(
            {
                "id": event.id,
                "created_at": event.created_at.isoformat(),
                "event_type": event.event_type,
                "station_id": event.station_id.value,
                "request_id": event.request_id or "",
                "work_order_id": event.work_order_id or "",
                "target_type": event.target_type or "",
                "target_id": event.target_id or "",
                "summary": event.summary,
                "details_json": event.details_json or "",
            }
        )
    return output.getvalue()