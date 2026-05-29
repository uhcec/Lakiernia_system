from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.audit.repository import AuditRepository
from app.audit.schemas import AuditEventRead, build_audit_event_read
from app.database.session import get_db_session
from app.shared.exceptions import ResourceNotFoundError
from app.work_orders.repository import WorkOrderRepository

router = APIRouter(prefix="/audit", tags=["audit"])


def get_audit_repository(session: Annotated[Session, Depends(get_db_session)]) -> AuditRepository:
    return AuditRepository(session)


def get_work_order_repository(session: Annotated[Session, Depends(get_db_session)]) -> WorkOrderRepository:
    return WorkOrderRepository(session)


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