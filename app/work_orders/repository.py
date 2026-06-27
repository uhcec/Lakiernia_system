from collections.abc import Sequence
from datetime import date

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.work_orders.models import WorkOrder, WorkOrderAttachment


class WorkOrderRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, work_order: WorkOrder) -> WorkOrder:
        self.session.add(work_order)
        self.session.flush()
        self.session.refresh(work_order)
        return work_order

    def get_by_id(self, work_order_id: int) -> WorkOrder | None:
        statement = (
            select(WorkOrder)
            .options(
                selectinload(WorkOrder.stage_states),
                selectinload(WorkOrder.quantity_batches),
                selectinload(WorkOrder.parent_order),
                selectinload(WorkOrder.correction_orders),
                selectinload(WorkOrder.attachments),
            )
            .where(WorkOrder.id == work_order_id)
        )
        return self.session.scalar(statement)

    def list(self, *, limit: int, offset: int, external_order_number_query: str | None = None) -> Sequence[WorkOrder]:
        statement: Select[tuple[WorkOrder]] = (
            select(WorkOrder)
            .options(
                selectinload(WorkOrder.stage_states),
                selectinload(WorkOrder.quantity_batches),
                selectinload(WorkOrder.parent_order),
                selectinload(WorkOrder.correction_orders),
                selectinload(WorkOrder.attachments),
            )
            .order_by(WorkOrder.queue_position.asc(), WorkOrder.id.asc())
        )
        statement = self._filter_by_external_order_number(statement, external_order_number_query)
        statement = statement.offset(offset).limit(limit)
        return self.session.scalars(statement).all()

    def count(self, *, external_order_number_query: str | None = None) -> int:
        statement = select(func.count()).select_from(WorkOrder)
        statement = self._filter_by_external_order_number(statement, external_order_number_query)
        return self.session.scalar(statement) or 0

    @staticmethod
    def _filter_by_external_order_number(statement, external_order_number_query: str | None):
        if external_order_number_query is None:
            return statement

        normalized_query = external_order_number_query.strip()
        if not normalized_query:
            return statement

        return statement.where(WorkOrder.external_order_number.ilike(f"%{normalized_query}%"))

    def get_next_queue_position(self) -> int:
        statement = select(func.max(WorkOrder.queue_position))
        current_max = self.session.scalar(statement)
        return 1 if current_max is None else current_max + 1

    def add_attachment(self, attachment: WorkOrderAttachment) -> WorkOrderAttachment:
        self.session.add(attachment)
        self.session.flush()
        self.session.refresh(attachment)
        return attachment

    def list_attachments(self, work_order_id: int) -> Sequence[WorkOrderAttachment]:
        statement = (
            select(WorkOrderAttachment)
            .where(WorkOrderAttachment.work_order_id == work_order_id)
            .order_by(WorkOrderAttachment.uploaded_at.desc(), WorkOrderAttachment.id.desc())
        )
        return self.session.scalars(statement).all()

    def get_attachment(self, work_order_id: int, attachment_id: int) -> WorkOrderAttachment | None:
        statement = select(WorkOrderAttachment).where(
            WorkOrderAttachment.id == attachment_id,
            WorkOrderAttachment.work_order_id == work_order_id,
        )
        return self.session.scalar(statement)

    def delete_attachment(self, attachment: WorkOrderAttachment) -> None:
        self.session.delete(attachment)

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
