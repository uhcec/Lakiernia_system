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
    WorkOrderRead,
    WorkOrderStatusTransitionRequest,
    WorkOrderStatusOption,
    WorkOrderStatusView,
    WorkOrderUpdate,
    build_coating_type_view,
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
            description=payload.description,
            customer_name=payload.customer_name,
            status=WorkOrderStatus.ENTERED,
            coating_type=payload.coating_type,
            due_date=payload.due_date,
            notes=payload.notes,
        )

        try:
            persisted_work_order = self.repository.add(work_order)
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
            description=work_order.description,
            customer_name=work_order.customer_name,
            status=self.build_status_view(work_order.status),
            coating_type=build_coating_type_view(work_order.coating_type),
            production_type=(
                build_production_type_view(work_order.production_type)
                if work_order.production_type is not None
                else None
            ),
            queue_position=work_order.queue_position,
            due_date=work_order.due_date,
            notes=work_order.notes,
            created_at=work_order.created_at,
            updated_at=work_order.updated_at,
        )