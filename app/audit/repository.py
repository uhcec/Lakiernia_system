from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.models import AuditEvent
from app.shared.request_context import get_current_request_id


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, event: AuditEvent) -> AuditEvent:
        if event.request_id is None:
            event.request_id = get_current_request_id()
        self.session.add(event)
        self.session.flush()
        self.session.refresh(event)
        return event

    def list_for_work_order(self, work_order_id: int, *, limit: int, offset: int = 0) -> Sequence[AuditEvent]:
        statement = (
            select(AuditEvent)
            .where(AuditEvent.work_order_id == work_order_id)
            .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
            .offset(offset)
            .limit(limit)
        )
        return self.session.scalars(statement).all()