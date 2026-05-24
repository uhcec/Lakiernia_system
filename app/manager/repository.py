from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.work_orders.models import WorkOrder


class ManagerRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, work_order_id: int) -> WorkOrder | None:
        statement = select(WorkOrder).options(selectinload(WorkOrder.stage_states), selectinload(WorkOrder.quantity_batches)).where(WorkOrder.id == work_order_id)
        return self.session.scalar(statement)

    def list_unplanned_work_orders(self) -> Sequence[WorkOrder]:
        statement = (
            select(WorkOrder)
            .options(selectinload(WorkOrder.stage_states), selectinload(WorkOrder.quantity_batches))
            .where(WorkOrder.production_type.is_(None), WorkOrder.queue_position.is_(None))
            .order_by(WorkOrder.id.asc())
        )
        return self.session.scalars(statement).all()

    def list_planned_work_orders(self) -> Sequence[WorkOrder]:
        statement = (
            select(WorkOrder)
            .options(selectinload(WorkOrder.stage_states), selectinload(WorkOrder.quantity_batches))
            .where(WorkOrder.production_type.is_not(None), WorkOrder.queue_position.is_not(None))
            .order_by(WorkOrder.queue_position.asc(), WorkOrder.id.asc())
        )
        return self.session.scalars(statement).all()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()