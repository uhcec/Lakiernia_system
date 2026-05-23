from datetime import UTC, datetime

from app.process.repository import ProcessRepository
from app.process.service import ProcessService
from app.manager.repository import ManagerRepository
from app.manager.schemas import WorkOrderPlanAssignRequest, WorkOrderQueuePositionUpdateRequest
from app.shared.exceptions import InvalidManagerPlanningError, ResourceNotFoundError
from app.work_orders.models import WorkOrder
from app.work_orders.schemas import WorkOrderRead
from app.work_orders.schemas import (
    WorkOrderStageStateRead,
    build_coating_type_view,
    build_process_stage_view,
    build_process_status_view,
    build_production_type_view,
    build_stage_status_info_view,
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

    def _get_existing_work_order(self, work_order_id: int) -> WorkOrder:
        work_order = self.repository.get_by_id(work_order_id)
        if work_order is None:
            raise ResourceNotFoundError(f"Work order {work_order_id} not found.")
        return work_order

    @staticmethod
    def _is_planned(work_order: WorkOrder) -> bool:
        return work_order.production_type is not None and work_order.queue_position is not None

    def _to_read_model(self, work_order: WorkOrder) -> WorkOrderRead:
        return WorkOrderRead(
            id=work_order.id,
            order_number=work_order.order_number,
            title=work_order.title,
            description=work_order.description,
            customer_name=work_order.customer_name,
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
            due_date=work_order.due_date,
            notes=work_order.notes,
            created_at=work_order.created_at,
            updated_at=work_order.updated_at,
        )

    def _get_ordered_stage_states(self, work_order: WorkOrder):
        stage_order = {
            stage: index
            for index, stage in enumerate(self.process_service.get_stage_sequence(work_order.coating_type))
        }
        return sorted(work_order.stage_states, key=lambda stage_state: stage_order[stage_state.stage])