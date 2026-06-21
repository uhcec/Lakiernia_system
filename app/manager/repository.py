from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.process.enums import QuantityBatchType
from app.process.models import StatOnlyCorrection, WorkOrderQuantityBatch
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

    def correction_events_select(self):
        # THE single definition of a "correction event" in the hybrid correction model (NA4): every
        # consumer (reason report, throughput chart, future correction stats) builds on this one
        # source so they can never drift. Three disjoint origins, normalized to (created_at, category,
        # quantity):
        #   * CORRECTION quantity batches (RAL packing / DECORAL decoral batch-reset),
        #   * child correction work orders (DECORAL packing spins the correction off as a "P" order), and
        #   * stat-only corrections (NA34: fixed on the spot — logged but never re-entered the workflow).
        batch_events = select(
            WorkOrderQuantityBatch.created_at.label("created_at"),
            WorkOrderQuantityBatch.correction_reason_category.label("category"),
            WorkOrderQuantityBatch.quantity.label("quantity"),
        ).where(WorkOrderQuantityBatch.type == QuantityBatchType.CORRECTION)
        child_events = select(
            WorkOrder.created_at.label("created_at"),
            WorkOrder.correction_reason_category.label("category"),
            WorkOrder.total_quantity.label("quantity"),
        ).where(WorkOrder.is_correction.is_(True))
        stat_only_events = select(
            StatOnlyCorrection.created_at.label("created_at"),
            StatOnlyCorrection.correction_reason_category.label("category"),
            StatOnlyCorrection.correction_quantity.label("quantity"),
        )
        return batch_events.union_all(child_events, stat_only_events).subquery()

    def list_correction_reason_report(self) -> Sequence[tuple[str | None, int, int]]:
        # Aggregate the shared correction-event source by reason/category.
        events = self.correction_events_select()
        rows = self.session.execute(
            select(
                events.c.category,
                func.count(),
                func.coalesce(func.sum(events.c.quantity), 0),
            ).group_by(events.c.category)
        ).all()

        # Order by total correction quantity desc, then category asc (None last).
        return sorted(
            ((category, int(count), int(quantity or 0)) for category, count, quantity in rows),
            key=lambda row: (-row[2], row[0] is None, row[0] or ""),
        )

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