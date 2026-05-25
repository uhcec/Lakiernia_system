from collections.abc import Sequence
from datetime import date

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.shared.enums import WorkOrderStatus
from app.work_orders.models import WorkOrder


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
            )
            .where(WorkOrder.id == work_order_id)
        )
        return self.session.scalar(statement)

    def list(self, *, limit: int, offset: int, status: WorkOrderStatus | None = None) -> Sequence[WorkOrder]:
        statement: Select[tuple[WorkOrder]] = (
            select(WorkOrder)
            .options(
                selectinload(WorkOrder.stage_states),
                selectinload(WorkOrder.quantity_batches),
                selectinload(WorkOrder.parent_order),
                selectinload(WorkOrder.correction_orders),
            )
            .order_by(WorkOrder.queue_position.asc(), WorkOrder.id.asc())
        )
        if status is not None:
            statement = statement.where(WorkOrder.status == status)
        statement = statement.offset(offset).limit(limit)
        return self.session.scalars(statement).all()

    def count(self, *, status: WorkOrderStatus | None = None) -> int:
        statement = select(func.count()).select_from(WorkOrder)
        if status is not None:
            statement = statement.where(WorkOrder.status == status)
        return self.session.scalar(statement) or 0

    def get_latest_order_number_for_year(self, year: int) -> str | None:
        prefix = f"WO-{year}-"
        statement = (
            select(WorkOrder.order_number)
            .where(WorkOrder.order_number.like(f"{prefix}%"))
            .order_by(WorkOrder.order_number.desc())
            .limit(1)
        )
        return self.session.scalar(statement)

    def get_next_queue_position(self) -> int:
        statement = select(func.max(WorkOrder.queue_position))
        current_max = self.session.scalar(statement)
        return 1 if current_max is None else current_max + 1

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()