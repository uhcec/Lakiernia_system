from datetime import UTC, datetime

from app.process.repository import ProcessRepository
from app.process.service import ProcessService
from app.manager.repository import ManagerRepository
from app.manager.schemas import WorkOrderPlanAssignRequest, WorkOrderQueuePositionUpdateRequest, WorkOrderQueueReorderRequest
from app.shared.exceptions import InvalidManagerPlanningError, ResourceNotFoundError
from app.work_orders.models import WorkOrder
from app.work_orders.schemas import WorkOrderRead
from app.work_orders.schemas import (
    WorkOrderQuantityBatchRead,
    WorkOrderRelationSummaryRead,
    WorkOrderStageStateRead,
    build_coating_type_view,
    build_process_stage_view,
    build_process_status_view,
    build_production_type_view,
    build_quantity_batch_type_view,
    build_stage_status_info_view,
    build_work_order_relation_summary,
)
from app.work_orders.service import WorkOrderService


class ManagerService:
    def __init__(self, repository: ManagerRepository) -> None:
        self.repository = repository
        self.process_service = ProcessService(ProcessRepository(repository.session))

    def list_unplanned_work_orders(self) -> list[WorkOrderRead]:
        return [self._to_read_model(work_order) for work_order in self.repository.list_unplanned_work_orders()]

    def list_planned_work_orders(self) -> list[WorkOrderRead]:
        return [self._to_read_model(work_order) for work_order in self.repository.list_planned_work_orders()]

    def assign_plan(self, work_order_id: int, payload: WorkOrderPlanAssignRequest) -> WorkOrderRead:
        work_order = self._get_existing_work_order(work_order_id)
        if self._is_planned(work_order):
            raise InvalidManagerPlanningError(f"Work order {work_order_id} is already planned.")
        if work_order.is_incomplete_on_arrival:
            raise InvalidManagerPlanningError("Cannot plan incomplete order. Mark as complete first.")

        work_order.production_type = payload.production_type
        work_order.queue_position = payload.queue_position
        work_order.updated_at = datetime.now(UTC)

        try:
            self.repository.commit()
        except Exception:
            self.repository.rollback()
            raise

        return self._to_read_model(work_order)

    def update_queue_position(
        self,
        work_order_id: int,
        payload: WorkOrderQueuePositionUpdateRequest,
    ) -> WorkOrderRead:
        work_order = self._get_existing_work_order(work_order_id)
        if not self._is_planned(work_order):
            raise InvalidManagerPlanningError(f"Work order {work_order_id} must be planned before updating queue position.")

        work_order.queue_position = payload.queue_position
        work_order.updated_at = datetime.now(UTC)

        try:
            self.repository.commit()
        except Exception:
            self.repository.rollback()
            raise

        return self._to_read_model(work_order)

    def reorder_queue(self, payload: list[WorkOrderQueueReorderRequest]) -> list[WorkOrderRead]:
        if not payload:
            return self.list_planned_work_orders()

        work_order_ids = [item.work_order_id for item in payload]
        queue_positions = [item.queue_position for item in payload]

        if len(set(work_order_ids)) != len(work_order_ids):
            raise InvalidManagerPlanningError("Queue reorder payload cannot contain duplicate work order IDs.")
        if len(set(queue_positions)) != len(queue_positions):
            raise InvalidManagerPlanningError("Queue reorder payload cannot contain duplicate queue positions.")

        existing_work_orders = {work_order.id: work_order for work_order in self.repository.list_by_ids(work_order_ids)}
        missing_ids = [work_order_id for work_order_id in work_order_ids if work_order_id not in existing_work_orders]
        if missing_ids:
            missing_id = missing_ids[0]
            raise ResourceNotFoundError(f"Work order {missing_id} not found.")

        now = datetime.now(UTC)
        for item in payload:
            work_order = existing_work_orders[item.work_order_id]
            if not self._is_planned(work_order):
                raise InvalidManagerPlanningError(
                    f"Work order {item.work_order_id} must be planned before reordering the queue."
                )

            work_order.queue_position = item.queue_position
            work_order.updated_at = now

        try:
            self.repository.commit()
        except Exception:
            self.repository.rollback()
            raise

        return self.list_planned_work_orders()

    def _get_existing_work_order(self, work_order_id: int) -> WorkOrder:
        work_order = self.repository.get_by_id(work_order_id)
        if work_order is None:
            raise ResourceNotFoundError(f"Work order {work_order_id} not found.")
        return work_order

    @staticmethod
    def _is_planned(work_order: WorkOrder) -> bool:
        return work_order.production_type is not None and work_order.queue_position is not None

    def _to_read_model(self, work_order: WorkOrder) -> WorkOrderRead:
        waiting_ok_quantity = self.process_service.get_waiting_ok_quantity(work_order)
        pending_correction_quantity = self.process_service.get_pending_correction_quantity(work_order)
        total_progress_quantity = self.process_service.get_total_progress_quantity(work_order)

        return WorkOrderRead(
            id=work_order.id,
            order_number=work_order.order_number,
            title=work_order.title,
            total_quantity=work_order.total_quantity,
            completed_quantity=work_order.completed_quantity,
            current_active_quantity=work_order.current_active_quantity,
            waiting_ok_quantity=waiting_ok_quantity,
            pending_correction_quantity=pending_correction_quantity,
            total_progress_quantity=total_progress_quantity,
            is_correction=work_order.is_correction,
            parent_order=(
                self._build_relation_summary(work_order.parent_order)
                if work_order.parent_order is not None
                else None
            ),
            correction_orders=[
                self._build_relation_summary(correction_order)
                for correction_order in self._get_ordered_correction_orders(work_order)
            ],
            description=work_order.description,
            customer_name=work_order.customer_name,
            ral_code=work_order.ral_code,
            paint_producer=work_order.paint_producer,
            status=WorkOrderService.build_status_view(work_order.status),
            process_status=build_process_status_view(self.process_service.get_display_status(work_order)),
            coating_type=build_coating_type_view(work_order.coating_type),
            production_type=(
                build_production_type_view(work_order.production_type)
                if work_order.production_type is not None
                else None
            ),
            queue_position=work_order.queue_position,
            stage_states=[
                WorkOrderStageStateRead(
                    stage=build_process_stage_view(stage_state.stage),
                    status=build_stage_status_info_view(stage_state.status),
                )
                for stage_state in self._get_ordered_stage_states(work_order)
            ],
            batches=[
                WorkOrderQuantityBatchRead(
                    id=batch.id,
                    quantity=batch.quantity,
                    type=build_quantity_batch_type_view(batch.type),
                    parent_batch_id=batch.parent_batch_id,
                    is_active=batch.is_active,
                    is_finished=not batch.is_active,
                    current_stage=(build_process_stage_view(batch.current_stage) if batch.current_stage is not None else None),
                    current_stage_status=(
                        build_stage_status_info_view(batch.current_stage_status)
                        if batch.current_stage_status is not None
                        else None
                    ),
                    is_partial=batch.is_partial,
                    created_at=batch.created_at,
                )
                for batch in self._get_ordered_batches(work_order)
            ],
            received_date=work_order.received_date,
            planned_pickup_date=work_order.planned_pickup_date,
            total_area_m2=work_order.total_area_m2,
            is_incomplete_on_arrival=work_order.is_incomplete_on_arrival,
            profiles_quantity=work_order.profiles_quantity,
            profiles_to_count=work_order.profiles_to_count,
            accessories_quantity=work_order.accessories_quantity,
            accessories_to_count=work_order.accessories_to_count,
            notes=work_order.notes,
            created_at=work_order.created_at,
            updated_at=work_order.updated_at,
        )

    def _get_ordered_stage_states(self, work_order: WorkOrder):
        stage_order = {
            stage: index
            for index, stage in enumerate(self.process_service.get_stage_sequence_for_work_order(work_order))
        }
        return sorted(
            [stage_state for stage_state in work_order.stage_states if stage_state.stage in stage_order],
            key=lambda stage_state: stage_order[stage_state.stage],
        )

    @staticmethod
    def _get_ordered_batches(work_order: WorkOrder):
        return sorted(work_order.quantity_batches, key=lambda batch: (batch.created_at, batch.id))

    @staticmethod
    def _get_ordered_correction_orders(work_order: WorkOrder) -> list[WorkOrder]:
        return sorted(work_order.correction_orders, key=lambda correction_order: (correction_order.created_at, correction_order.id))

    def _build_relation_summary(self, work_order: WorkOrder):
        summary = build_work_order_relation_summary(work_order)
        summary.process_status = build_process_status_view(self.process_service.get_display_status(work_order))
        return summary