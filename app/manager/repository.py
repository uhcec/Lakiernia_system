from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.shared.enums import WorkOrderStatus
from app.work_orders.models import WorkOrder


class ManagerRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, work_order_id: int) -> WorkOrder | None:
        statement = (
            select(WorkOrder)
            .options(
                selectinload(WorkOrder.stage_states),
                selectinload(WorkOrder.quantity_batches),
                selectinload(WorkOrder.parent_order),
                selectinload(WorkOrder.correction_orders),
            )
            .where(WorkOrder.id == work_order_id)
        )
        return self.session.scalar(statement)

    def list_by_ids(self, work_order_ids: Sequence[int]) -> Sequence[WorkOrder]:
        if not work_order_ids:
            return []

        statement = (
            select(WorkOrder)
            .options(
                selectinload(WorkOrder.stage_states),
                selectinload(WorkOrder.quantity_batches),
                selectinload(WorkOrder.parent_order),
                selectinload(WorkOrder.correction_orders),
            )
            .where(WorkOrder.id.in_(work_order_ids))
        )
        return self.session.scalars(statement).all()

    def get_planned_by_queue_position(
        self,
        queue_position: int,
        *,
        exclude_work_order_id: int | None = None,
    ) -> WorkOrder | None:
        statement = select(WorkOrder).where(
            WorkOrder.production_type.is_not(None),
            WorkOrder.queue_position == queue_position,
            WorkOrder.is_incomplete_on_arrival.is_(False),
            WorkOrder.status != WorkOrderStatus.INCOMPLETE,
        )
        if exclude_work_order_id is not None:
            statement = statement.where(WorkOrder.id != exclude_work_order_id)
        return self.session.scalar(statement)

    def list_unplanned_work_orders(self) -> Sequence[WorkOrder]:
        statement = (
            select(WorkOrder)
            .options(
                selectinload(WorkOrder.stage_states),
                selectinload(WorkOrder.quantity_batches),
                selectinload(WorkOrder.parent_order),
                selectinload(WorkOrder.correction_orders),
            )
            .where(
                WorkOrder.production_type.is_(None),
                WorkOrder.queue_position.is_(None),
                WorkOrder.is_incomplete_on_arrival.is_(False),
                WorkOrder.status != WorkOrderStatus.INCOMPLETE,
            )
            .order_by(WorkOrder.id.asc())
        )
        return self.session.scalars(statement).all()

    def list_planned_work_orders(self) -> Sequence[WorkOrder]:
        statement = (
            select(WorkOrder)
            .options(
                selectinload(WorkOrder.stage_states),
                selectinload(WorkOrder.quantity_batches),
                selectinload(WorkOrder.parent_order),
                selectinload(WorkOrder.correction_orders),
            )
            .where(
                WorkOrder.production_type.is_not(None),
                WorkOrder.queue_position.is_not(None),
                WorkOrder.is_incomplete_on_arrival.is_(False),
                WorkOrder.status != WorkOrderStatus.INCOMPLETE,
            )
            .order_by(WorkOrder.queue_position.asc(), WorkOrder.id.asc())
        )
        return self.session.scalars(statement).all()

    def list_correction_reason_report(self) -> Sequence[tuple[str | None, int, int]]:
        statement = (
            select(
                WorkOrder.correction_reason_category,
                func.count(WorkOrder.id),
                func.coalesce(func.sum(WorkOrder.total_quantity), 0),
            )
            .where(WorkOrder.is_correction.is_(True))
            .group_by(WorkOrder.correction_reason_category)
            .order_by(func.coalesce(func.sum(WorkOrder.total_quantity), 0).desc(), WorkOrder.correction_reason_category.asc())
        )
        return [
            (category, int(work_order_count), int(total_correction_quantity or 0))
            for category, work_order_count, total_correction_quantity in self.session.execute(statement).all()
        ]

    def get_planned_queue_revision(self):
        statement = select(func.max(WorkOrder.updated_at)).where(
            WorkOrder.production_type.is_not(None),
            WorkOrder.queue_position.is_not(None),
            WorkOrder.is_incomplete_on_arrival.is_(False),
            WorkOrder.status != WorkOrderStatus.INCOMPLETE,
        )
        return self.session.scalar(statement)

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()