from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.models import AuditEvent, AuditEventActor
from app.employees.models import StationPresence
from app.shared.enums import StationId
from app.shared.request_context import get_current_request_id


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, event: AuditEvent) -> AuditEvent:
        if event.request_id is None:
            event.request_id = get_current_request_id()
        self.session.add(event)
        self.session.flush()
        self._attribute_present_employees(event)
        self.session.refresh(event)
        return event

    def _attribute_present_employees(self, event: AuditEvent) -> None:
        # Per-operator attribution: stamp the action with whoever is currently checked in at its
        # station. SYSTEM/UNKNOWN (internal/seed) actions have no station roster, so they get none.
        if event.station_id in {StationId.SYSTEM, StationId.UNKNOWN}:
            return
        present = self.session.scalars(
            select(StationPresence).where(
                StationPresence.station_id == event.station_id,
                StationPresence.checked_out_at.is_(None),
            )
        ).all()
        for presence in present:
            self.session.add(
                AuditEventActor(
                    audit_event_id=event.id,
                    employee_id=presence.employee_id,
                    employee_name=presence.employee.full_name,
                )
            )
        if present:
            self.session.flush()

    def list_for_work_order(self, work_order_id: int, *, limit: int, offset: int = 0) -> Sequence[AuditEvent]:
        statement = (
            select(AuditEvent)
            .where(AuditEvent.work_order_id == work_order_id)
            .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
            .offset(offset)
            .limit(limit)
        )
        return self.session.scalars(statement).all()

    def list_events(
        self,
        *,
        limit: int,
        offset: int = 0,
        work_order_id: int | None = None,
        event_type: str | None = None,
        station_id: StationId | None = None,
        request_id: str | None = None,
        target_type: str | None = None,
        target_id: int | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> Sequence[AuditEvent]:
        statement = select(AuditEvent)

        if work_order_id is not None:
            statement = statement.where(AuditEvent.work_order_id == work_order_id)
        if event_type is not None:
            statement = statement.where(AuditEvent.event_type == event_type)
        if station_id is not None:
            statement = statement.where(AuditEvent.station_id == station_id)
        if request_id is not None:
            statement = statement.where(AuditEvent.request_id == request_id)
        if target_type is not None:
            statement = statement.where(AuditEvent.target_type == target_type)
        if target_id is not None:
            statement = statement.where(AuditEvent.target_id == target_id)
        if created_from is not None:
            statement = statement.where(AuditEvent.created_at >= created_from)
        if created_to is not None:
            statement = statement.where(AuditEvent.created_at <= created_to)

        statement = statement.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).offset(offset).limit(limit)
        return self.session.scalars(statement).all()
