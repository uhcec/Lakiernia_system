from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import get_settings, get_work_order_attachments_path
from app.process.enums import ProcessDisplayStatus
from app.process.repository import ProcessRepository
from app.process.service import ProcessService
from app.shared.enums import WorkOrderStatus, get_work_order_status_label
from app.shared.exceptions import InvalidAttachmentError, InvalidStatusTransitionError, ResourceNotFoundError
from app.work_orders.models import WorkOrder, WorkOrderAttachment
from app.work_orders.number_allocator import WorkOrderNumberAllocator
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import (
    WorkOrderAttachmentRead,
    WorkOrderCreate,
    WorkOrderListResponse,
    WorkOrderQuantityBatchRead,
    WorkOrderRelationSummaryRead,
    WorkOrderRead,
    WorkOrderStageStateRead,
    WorkOrderStatusOption,
    WorkOrderStatusView,
    WorkOrderUpdate,
    build_work_order_attachment_read,
    build_coating_type_view,
    build_process_status_view,
    build_process_stage_view,
    build_stage_status_info_view,
    build_quantity_batch_type_view,
    build_work_order_relation_summary,
    build_queue_namespace_view,
    build_production_type_view,
)


class WorkOrderService:
    ALLOWED_ATTACHMENT_CONTENT_TYPES = {"application/pdf"}

    def __init__(self, repository: WorkOrderRepository) -> None:
        self.repository = repository
        self.process_service = ProcessService(ProcessRepository(repository.session))
        self.number_allocator = WorkOrderNumberAllocator(repository.session)

    @staticmethod
    def get_status_options() -> list[WorkOrderStatusOption]:
        return [
            WorkOrderStatusOption(value=status, label=get_work_order_status_label(status))
            for status in WorkOrderStatus
        ]

    @staticmethod
    def derive_status(process_status: ProcessDisplayStatus) -> WorkOrderStatus:
        if process_status == ProcessDisplayStatus.INCOMPLETE:
            return WorkOrderStatus.INCOMPLETE
        if process_status == ProcessDisplayStatus.TO_BE_PLANNED:
            return WorkOrderStatus.ENTERED
        if process_status == ProcessDisplayStatus.READY:
            return WorkOrderStatus.FINISHED
        return WorkOrderStatus.IN_PROGRESS

    @classmethod
    def build_status_view(cls, process_status: ProcessDisplayStatus) -> WorkOrderStatusView:
        status = cls.derive_status(process_status)
        return WorkOrderStatusView(value=status, label=get_work_order_status_label(status))

    def create_work_order(self, payload: WorkOrderCreate) -> WorkOrderRead:
        initial_status = WorkOrderStatus.INCOMPLETE if payload.is_incomplete_on_arrival else WorkOrderStatus.ENTERED
        order_number = self.number_allocator.allocate()

        work_order = WorkOrder(
            order_number=order_number,
            title=payload.title or order_number,
            total_quantity=payload.total_quantity,
            description=payload.description,
            customer_name=payload.customer_name,
            ral_code=payload.ral_code,
            paint_producer=payload.paint_producer,
            status=initial_status,
            coating_type=payload.coating_type,
            received_date=payload.received_date,
            planned_pickup_date=payload.planned_pickup_date,
            total_area_m2=payload.total_area_m2,
            is_incomplete_on_arrival=payload.is_incomplete_on_arrival,
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
        process_status: ProcessDisplayStatus | None = None,
    ) -> WorkOrderListResponse:
        if process_status is None:
            items = self.repository.list(limit=limit, offset=offset)
            total = self.repository.count()
        else:
            all_items = self.repository.list(limit=self.repository.count(), offset=0)
            filtered_items = [item for item in all_items if self.process_service.get_display_status(item) == process_status]
            total = len(filtered_items)
            items = filtered_items[offset : offset + limit]

        return WorkOrderListResponse(
            items=[self._to_read_model(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    def reject_manual_status_transition(self, work_order_id: int) -> WorkOrderRead:
        self._get_existing_work_order(work_order_id)
        raise InvalidStatusTransitionError(
            "Work order status is derived from process status and cannot be changed manually."
        )

    def mark_complete_arrival(self, work_order_id: int) -> WorkOrderRead:
        work_order = self._get_existing_work_order(work_order_id)

        if not self._has_incomplete_marker(work_order):
            raise InvalidStatusTransitionError(
                f"Work order {work_order_id} is not marked as incomplete on arrival."
            )

        work_order.is_incomplete_on_arrival = False
        work_order.status = WorkOrderStatus.ENTERED
        work_order.updated_at = datetime.now(UTC)

        try:
            self.repository.commit()
        except Exception:
            self.repository.rollback()
            raise

        return self._to_read_model(work_order)

    @staticmethod
    def _has_incomplete_marker(work_order: WorkOrder) -> bool:
        return work_order.is_incomplete_on_arrival or work_order.status == WorkOrderStatus.INCOMPLETE

    async def upload_attachment(
        self,
        work_order_id: int,
        file: UploadFile,
        *,
        attachment_type: str | None = None,
        description: str | None = None,
    ) -> WorkOrderAttachmentRead:
        work_order = self._get_existing_work_order(work_order_id)
        original_filename = Path(file.filename or "").name.strip()
        if not original_filename:
            raise InvalidAttachmentError("Plik musi mieć nazwę.")
        if file.content_type not in self.ALLOWED_ATTACHMENT_CONTENT_TYPES:
            raise InvalidAttachmentError("Dozwolone są tylko pliki PDF.", status_code=415)

        settings = get_settings()
        root_path = get_work_order_attachments_path()
        attachment_directory = root_path / str(work_order.id)
        attachment_directory.mkdir(parents=True, exist_ok=True)

        stored_filename = f"{uuid4().hex}.pdf"
        destination_path = attachment_directory / stored_filename
        relative_storage_path = destination_path.relative_to(root_path).as_posix()

        file_size = 0
        try:
            with destination_path.open("wb") as output_file:
                while chunk := await file.read(1024 * 1024):
                    file_size += len(chunk)
                    if file_size > settings.work_order_attachment_max_size_bytes:
                        raise InvalidAttachmentError(
                            f"Plik przekracza limit {settings.work_order_attachment_max_size_bytes} B.",
                            status_code=413,
                        )
                    output_file.write(chunk)

            if file_size == 0:
                raise InvalidAttachmentError("Nie można przesłać pustego pliku PDF.")

            attachment = WorkOrderAttachment(
                work_order_id=work_order.id,
                original_filename=original_filename,
                stored_filename=stored_filename,
                storage_path=relative_storage_path,
                content_type=file.content_type,
                file_size=file_size,
                attachment_type=self._normalize_optional_text(attachment_type),
                description=self._normalize_optional_text(description),
            )

            persisted_attachment = self.repository.add_attachment(attachment)
            self.repository.commit()
        except Exception:
            self.repository.rollback()
            if destination_path.exists():
                destination_path.unlink()
            raise
        finally:
            await file.close()

        return build_work_order_attachment_read(persisted_attachment)

    def list_attachments(self, work_order_id: int) -> list[WorkOrderAttachmentRead]:
        self._get_existing_work_order(work_order_id)
        return [
            build_work_order_attachment_read(attachment)
            for attachment in self.repository.list_attachments(work_order_id)
        ]

    def get_attachment_download(self, work_order_id: int, attachment_id: int) -> tuple[WorkOrderAttachmentRead, Path]:
        attachment = self._get_existing_attachment(work_order_id, attachment_id)
        root_path = get_work_order_attachments_path()
        absolute_path = (root_path / attachment.storage_path).resolve()
        if not absolute_path.exists():
            raise ResourceNotFoundError(f"Attachment {attachment_id} file not found.")
        return build_work_order_attachment_read(attachment), absolute_path

    def delete_attachment(self, work_order_id: int, attachment_id: int) -> None:
        attachment = self._get_existing_attachment(work_order_id, attachment_id)
        file_path = get_work_order_attachments_path() / attachment.storage_path

        try:
            self.repository.delete_attachment(attachment)
            self.repository.commit()
        except Exception:
            self.repository.rollback()
            raise

        if file_path.exists():
            file_path.unlink()

        parent_directory = file_path.parent
        if parent_directory.exists() and not any(parent_directory.iterdir()):
            parent_directory.rmdir()

    def _get_existing_work_order(self, work_order_id: int) -> WorkOrder:
        work_order = self.repository.get_by_id(work_order_id)
        if work_order is None:
            raise ResourceNotFoundError(f"Work order {work_order_id} not found.")
        return work_order

    def _get_existing_attachment(self, work_order_id: int, attachment_id: int) -> WorkOrderAttachment:
        self._get_existing_work_order(work_order_id)
        attachment = self.repository.get_attachment(work_order_id, attachment_id)
        if attachment is None:
            raise ResourceNotFoundError(f"Attachment {attachment_id} not found for work order {work_order_id}.")
        return attachment

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    def _to_read_model(self, work_order: WorkOrder) -> WorkOrderRead:
        waiting_ok_quantity = self.process_service.get_waiting_ok_quantity(work_order)
        pending_correction_quantity = self.process_service.get_pending_correction_quantity(work_order)
        total_progress_quantity = self.process_service.get_total_progress_quantity(work_order)
        process_status = self.process_service.get_display_status(work_order)

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
            status=self.build_status_view(process_status),
            process_status=build_process_status_view(process_status),
            coating_type=build_coating_type_view(work_order.coating_type),
            production_type=(
                build_production_type_view(work_order.production_type)
                if work_order.production_type is not None
                else None
            ),
            queue_namespace=build_queue_namespace_view(work_order.queue_namespace),
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