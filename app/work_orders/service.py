from datetime import UTC, datetime

from app.process.repository import ProcessRepository
from app.process.service import ProcessService
from app.shared.enums import WorkOrderStatus, get_work_order_status_label
from app.shared.exceptions import ResourceNotFoundError
from app.work_orders.models import WorkOrder
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import (
    WorkOrderCreate,
    WorkOrderListResponse,
    WorkOrderQuantityBatchRead,
    WorkOrderRead,
    WorkOrderStageStateRead,
    WorkOrderStatusTransitionRequest,
    WorkOrderStatusOption,
    WorkOrderStatusView,
    WorkOrderUpdate,
    build_coating_type_view,
    build_process_status_view,
    build_process_stage_view,
    build_stage_status_info_view,
    build_quantity_batch_type_view,
    build_production_type_view,
)
from app.work_orders.workflow import validate_transition


class WorkOrderService:
    def __init__(self, repository: WorkOrderRepository) -> None:
        self.repository = repository
        self.process_service = ProcessService(ProcessRepository(repository.session))

    @staticmethod
    def get_status_options() -> list[WorkOrderStatusOption]:
        return [
            WorkOrderStatusOption(value=status, label=get_work_order_status_label(status))
            for status in WorkOrderStatus
        ]

    @staticmethod
    def build_status_view(status: WorkOrderStatus) -> WorkOrderStatusView:
        return WorkOrderStatusView(value=status, label=get_work_order_status_label(status))

    def create_work_order(self, payload: WorkOrderCreate) -> WorkOrderRead:
        work_order = WorkOrder(
            order_number=self._generate_order_number(),
            title=payload.title,
            total_quantity=payload.total_quantity,
            description=payload.description,
            customer_name=payload.customer_name,
            ral_code=payload.ral_code,
            paint_producer=payload.paint_producer,
            status=WorkOrderStatus.ENTERED,
            coating_type=payload.coating_type,
            received_date=payload.received_date,
            planned_pickup_date=payload.planned_pickup_date,
            total_area_m2=payload.total_area_m2,
            profiles_quantity=payload.profiles_quantity,
            profiles_to_count=payload.profiles_to_count,
            accessories_quantity=payload.accessories_quantity,
            accessories_to_count=payload.accessories_to_count,
            notes=payload.notes,
        )

        try:
            persisted_work_order = self.repository.add(work_order)
            self.process_service.initialize_quantity_tracking(persisted_work_order)
            self.process_service.initialize_stage_states(persisted_work_order)
            self.repository.commit()
        except Exception:
            self.repository.rollback()
            raise

        return self._to_read_model(persisted_work_order)

    def get_work_order(self, work_order_id: int) -> WorkOrderRead:
        work_order = self._get_existing_work_order(work_order_id)
        return self._to_read_model(work_order)

    def update_work_order(self, work_order_id: int, payload: WorkOrderUpdate) -> WorkOrderRead:
        work_order = self._get_existing_work_order(work_order_id)

        for field_name, field_value in payload.model_dump(exclude_unset=True).items():
            setattr(work_order, field_name, field_value)

        work_order.updated_at = datetime.now(UTC)

        try:
            self.repository.commit()
        except Exception:
            self.repository.rollback()
            raise

        return self._to_read_model(work_order)

    def list_work_orders(
        self,
        *,
        limit: int,
        offset: int,
        status: WorkOrderStatus | None = None,
    ) -> WorkOrderListResponse:
        items = self.repository.list(limit=limit, offset=offset, status=status)
        total = self.repository.count(status=status)
        return WorkOrderListResponse(
            items=[self._to_read_model(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    def transition_work_order_status(
        self,
        work_order_id: int,
        target_status: WorkOrderStatus,
        comment: str | None = None,
    ) -> WorkOrderRead:
        work_order = self._get_existing_work_order(work_order_id)

        validate_transition(work_order.status, target_status)

        work_order.status = target_status

        # TODO: Persist transition comments when audit/history storage is introduced.
        _ = comment

        try:
            self.repository.commit()
        except Exception:
            self.repository.rollback()
            raise

        return self._to_read_model(work_order)

    def transition_work_order_status_from_request(
        self,
        work_order_id: int,
        payload: WorkOrderStatusTransitionRequest,
    ) -> WorkOrderRead:
        return self.transition_work_order_status(
            work_order_id=work_order_id,
            target_status=payload.target_status,
            comment=payload.comment,
        )

    def _generate_order_number(self) -> str:
        year = datetime.now(UTC).year
        latest_order_number = self.repository.get_latest_order_number_for_year(year)
        next_sequence = 1 if latest_order_number is None else int(latest_order_number.rsplit("-", 1)[-1]) + 1
        return f"WO-{year}-{next_sequence:04d}"

    def _get_existing_work_order(self, work_order_id: int) -> WorkOrder:
        work_order = self.repository.get_by_id(work_order_id)
        if work_order is None:
            raise ResourceNotFoundError(f"Work order {work_order_id} not found.")
        return work_order

    def _to_read_model(self, work_order: WorkOrder) -> WorkOrderRead:
        return WorkOrderRead(
            id=work_order.id,
            order_number=work_order.order_number,
            title=work_order.title,
            total_quantity=work_order.total_quantity,
            completed_quantity=work_order.completed_quantity,
            current_active_quantity=work_order.current_active_quantity,
            description=work_order.description,
            customer_name=work_order.customer_name,
            ral_code=work_order.ral_code,
            paint_producer=work_order.paint_producer,
            status=self.build_status_view(work_order.status),
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