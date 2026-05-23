from collections.abc import Sequence

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from app.process.enums import ProcessStage, ProductionType
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
            .options(selectinload(WorkOrder.stage_states))
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
    ) -> Sequence[WorkOrder]:
        statement = (
            select(WorkOrder)
            .join(WorkOrderStageState, WorkOrderStageState.work_order_id == WorkOrder.id)
            .options(selectinload(WorkOrder.stage_states))
            .where(WorkOrderStageState.stage == stage)
            .order_by(WorkOrder.queue_position.asc(), WorkOrder.id.asc())
        )

        if production_type is not None:
            statement = statement.where(WorkOrder.production_type == production_type)

        return self.session.scalars(statement).unique().all()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
