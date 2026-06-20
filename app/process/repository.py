from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from app.process.enums import ProcessStage, ProductionType
from app.shared.enums import QueueNamespace
from app.shared.enums import WorkOrderStatus
from app.process.models import ProcessResourceLock, WorkOrderStageState
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
            .where(WorkOrder.is_incomplete_on_arrival.is_(False))
            .where(WorkOrder.status != WorkOrderStatus.INCOMPLETE)
            .order_by(WorkOrder.queue_position.asc(), WorkOrder.id.asc())
        )

        if stage == ProcessStage.PRODUCTION:
            # NA42: AUTOMATIC orders have no PRODUCTION stage row (the line paints automatically) and are
            # anchored on HANGING instead; MANUAL orders keep PRODUCTION. Match either so the production
            # panel still finds automatic orders. The precise visibility decision is made by
            # ProcessService.is_visible_in_stage; .unique() below dedupes the join.
            statement = statement.where(
                WorkOrderStageState.stage.in_([ProcessStage.PRODUCTION, ProcessStage.HANGING])
            )
        else:
            statement = statement.where(WorkOrderStageState.stage == stage)

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

    def acquire_resource_lock(self, resource_key: str, work_order_id: int) -> None:
        existing_lock = self.session.get(ProcessResourceLock, resource_key)
        if existing_lock is not None:
            if existing_lock.work_order_id == work_order_id:
                return
            raise ValueError(resource_key)

        self.session.add(ProcessResourceLock(resource_key=resource_key, work_order_id=work_order_id))
        self.session.flush()

    def release_resource_lock(self, resource_key: str, work_order_id: int) -> None:
        existing_lock = self.session.get(ProcessResourceLock, resource_key)
        if existing_lock is not None and existing_lock.work_order_id == work_order_id:
            self.session.delete(existing_lock)
            self.session.flush()

    def get_resource_lock(self, resource_key: str) -> ProcessResourceLock | None:
        return self.session.get(ProcessResourceLock, resource_key)

    def list_resource_locks_for_work_order(self, work_order_id: int) -> Sequence[ProcessResourceLock]:
        statement = select(ProcessResourceLock).where(ProcessResourceLock.work_order_id == work_order_id)
        return self.session.scalars(statement).all()

    def list_resource_locks_with_prefix(self, prefix: str) -> Sequence[ProcessResourceLock]:
        statement = select(ProcessResourceLock).where(ProcessResourceLock.resource_key.like(f"{prefix}%"))
        return self.session.scalars(statement).all()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
