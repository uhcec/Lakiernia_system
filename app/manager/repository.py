from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.process.enums import ProductionType, QuantityBatchType
from app.process.models import WorkOrderQuantityBatch
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
        production_type: ProductionType,
        *,
        exclude_work_order_id: int | None = None,
    ) -> WorkOrder | None:
        statement = select(WorkOrder).where(
            WorkOrder.production_type == production_type,
            WorkOrder.queue_position == queue_position,
            WorkOrder.is_incomplete_on_arrival.is_(False),
            WorkOrder.status != WorkOrderStatus.INCOMPLETE,
        )
        if exclude_work_order_id is not None:
            statement = statement.where(WorkOrder.id != exclude_work_order_id)
        return self.session.scalar(statement)

    def get_max_queue_position_for_line(self, production_type: ProductionType) -> int:
        """Highest queue position currently used on a production line (0 if the line is empty)."""
        statement = select(func.max(WorkOrder.queue_position)).where(
            WorkOrder.production_type == production_type,
            WorkOrder.queue_position.is_not(None),
        )
        return int(self.session.scalar(statement) or 0)

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
        # Corrections originate from two places in the hybrid correction model:
        #   * CORRECTION quantity batches (RAL packing / DECORAL decoral batch-reset), and
        #   * child correction work orders (DECORAL packing keeps the OK part on Decoral and spins
        #     the correction off as a separate "P" work order).
        # The report aggregates both correction events by reason/category.
        aggregate: dict[str | None, list[int]] = {}

        def add(category: str | None, count: int, quantity: int) -> None:
            bucket = aggregate.setdefault(category, [0, 0])
            bucket[0] += count
            bucket[1] += quantity

        batch_rows = self.session.execute(
            select(
                WorkOrderQuantityBatch.correction_reason_category,
                func.count(WorkOrderQuantityBatch.id),
                func.coalesce(func.sum(WorkOrderQuantityBatch.quantity), 0),
            )
            .where(WorkOrderQuantityBatch.type == QuantityBatchType.CORRECTION)
            .group_by(WorkOrderQuantityBatch.correction_reason_category)
        ).all()
        for category, count, quantity in batch_rows:
            add(category, int(count), int(quantity or 0))

        child_rows = self.session.execute(
            select(
                WorkOrder.correction_reason_category,
                func.count(WorkOrder.id),
                func.coalesce(func.sum(WorkOrder.total_quantity), 0),
            )
            .where(WorkOrder.is_correction.is_(True))
            .group_by(WorkOrder.correction_reason_category)
        ).all()
        for category, count, quantity in child_rows:
            add(category, int(count), int(quantity or 0))

        # Order by total correction quantity desc, then category asc (None last).
        return sorted(
            ((category, counts[0], counts[1]) for category, counts in aggregate.items()),
            key=lambda row: (-row[2], row[0] is None, row[0] or ""),
        )

    def get_planned_queue_revision(self, production_type: ProductionType | None = None):
        statement = select(func.max(WorkOrder.updated_at)).where(
            WorkOrder.production_type.is_not(None),
            WorkOrder.queue_position.is_not(None),
            WorkOrder.is_incomplete_on_arrival.is_(False),
            WorkOrder.status != WorkOrderStatus.INCOMPLETE,
        )
        if production_type is not None:
            statement = statement.where(WorkOrder.production_type == production_type)
        return self.session.scalar(statement)

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()