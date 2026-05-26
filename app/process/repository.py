from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from app.process.enums import ProcessStage, ProductionType
from app.shared.enums import QueueNamespace
from app.process.models import WorkOrderStageState
from app.work_orders.models import WorkOrder


class ProcessRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_stage_states(self, stage_states: Sequence[WorkOrderStageState]) -> None:
        self.session.add_all(stage_states)
        self.session.flush()

    def get_work_order_with_stage_states(self, work_order_id: int) -> WorkOrder | None:
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

    def list_stage_states(self, work_order_id: int) -> Sequence[WorkOrderStageState]:
        statement: Select[tuple[WorkOrderStageState]] = (
            select(WorkOrderStageState)
            .where(WorkOrderStageState.work_order_id == work_order_id)
            .order_by(WorkOrderStageState.id.asc())
        )
        return self.session.scalars(statement).all()

    def list_work_orders_with_stage(
        self,
        stage: ProcessStage,
        production_type: ProductionType | None = None,
        queue_namespace: QueueNamespace | None = None,
    ) -> Sequence[WorkOrder]:
        statement = (
            select(WorkOrder)
            .join(WorkOrderStageState, WorkOrderStageState.work_order_id == WorkOrder.id)
            .options(
                selectinload(WorkOrder.stage_states),
                selectinload(WorkOrder.quantity_batches),
                selectinload(WorkOrder.parent_order),
                selectinload(WorkOrder.correction_orders),
            )
            .where(WorkOrderStageState.stage == stage)
            .where(WorkOrder.is_incomplete_on_arrival.is_(False))
            .order_by(WorkOrder.queue_position.asc(), WorkOrder.id.asc())
        )

        if production_type is not None:
            statement = statement.where(WorkOrder.production_type == production_type)
        if queue_namespace is not None:
            statement = statement.where(WorkOrder.queue_namespace == queue_namespace)

        return self.session.scalars(statement).unique().all()

    def add_quantity_batch(self, batch) -> None:
        self.session.add(batch)
        self.session.flush()

    def add_work_order(self, work_order: WorkOrder) -> WorkOrder:
        self.session.add(work_order)
        self.session.flush()
        self.session.refresh(work_order)
        return work_order

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
