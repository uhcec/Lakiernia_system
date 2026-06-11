from collections.abc import Sequence
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
import json
from threading import RLock

from sqlalchemy.exc import IntegrityError

from app.audit.context import StationContext, ensure_station_allowed
from app.audit.models import AuditEvent
from app.audit.repository import AuditRepository
from app.paints.repository import PaintRepository
from app.paints.service import PaintService
from app.process.enums import CoatingType, ProcessDisplayStatus, ProcessStage, ProductionType, QuantityBatchType, StageStatus
from app.process.models import WorkOrderQuantityBatch, WorkOrderStageState
from app.process.repository import ProcessRepository
from app.process.schemas import ProcessStageStatusRead, ProcessStageWorkOrderRead, StageStatusView
from app.shared.enums import QueueNamespace, StationId, WorkOrderKind, WorkOrderStatus
from app.shared.exceptions import InvalidPaintInventoryError, InvalidProcessStageTransitionError, ResourceNotFoundError
from app.work_orders.number_allocator import WorkOrderNumberAllocator
from app.work_orders.models import WorkOrder
from app.work_orders.schemas import build_coating_type_view, build_production_type_view, build_queue_namespace_view, build_work_order_kind_view


_PROCESS_MUTATION_LOCKS: dict[int, RLock] = {}
_PROCESS_MUTATION_LOCKS_GUARD = RLock()
_RESOURCE_MUTATION_LOCKS: dict[str, RLock] = {}
_RESOURCE_MUTATION_LOCKS_GUARD = RLock()


class ProcessService:
    DEFAULT_CORRECTION_RETURN_STAGE = ProcessStage.PRODUCTION
    AUTOMATIC_PRODUCTION_MANUAL_ACTION_ERROR = (
        "Automatic production does not use manual start/finish. Finish HANGING to enter automatic production and complete from PACKING."
    )
    AUTOMATIC_PAINT_CONSUMPTION_REQUIRED_ERROR = "Automatic paint consumption must be recorded before packing can be completed."
    AUTOMATIC_PAINT_CONSUMPTION_CONFIGURATION_ERROR = "Paint code must be configured before automatic paint consumption can be recorded."
    AUTOMATIC_PAINT_CONSUMPTION_STAGE_ERROR = "Automatic paint consumption can be recorded once HANGING has started."
    AUTOMATIC_PAINT_CONSUMPTION_ALREADY_RECORDED_ERROR = "Automatic paint consumption cannot be edited after it has been saved. Use a manual office stock adjustment if a correction is required."
    QUEUE_RESOURCE_BLOCK_REASONS = {
        "HANGING": "Zawieszanie zajęte",
        "AUTOMATIC_LINE": "Linia automatyczna zajęta",
    }

    def __init__(self, repository: ProcessRepository) -> None:
        self.repository = repository
        self.paint_service = PaintService(PaintRepository(repository.session))
        self.number_allocator = WorkOrderNumberAllocator(repository.session)
        self.audit_repository = AuditRepository(repository.session)

    @staticmethod
    def get_stage_sequence_for_configuration(
        coating_type: CoatingType,
        production_type: ProductionType | None,
        *,
        skips_surface_preparation: bool = False,
    ) -> list[ProcessStage]:
        stages = [] if skips_surface_preparation else [ProcessStage.SURFACE_PREPARATION]
        if production_type != ProductionType.MANUAL:
            stages.append(ProcessStage.HANGING)
        stages.append(ProcessStage.PRODUCTION)
        stages.append(ProcessStage.PACKING)
        if coating_type == CoatingType.DECORAL:
            stages.append(ProcessStage.DECORAL_PRODUCTION)
        return stages

    def get_stage_sequence_for_work_order(self, work_order: WorkOrder) -> list[ProcessStage]:
        return self.get_stage_sequence_for_configuration(
            work_order.coating_type,
            work_order.production_type,
            skips_surface_preparation=self._omits_surface_preparation_stage(work_order),
        )

    @staticmethod
    def get_configured_stage_states_sequence(
        coating_type: CoatingType,
        *,
        skips_surface_preparation: bool = False,
    ) -> list[ProcessStage]:
        stages = [] if skips_surface_preparation else [ProcessStage.SURFACE_PREPARATION]
        stages.extend([ProcessStage.HANGING, ProcessStage.PRODUCTION, ProcessStage.PACKING])
        if coating_type == CoatingType.DECORAL:
            stages.append(ProcessStage.DECORAL_PRODUCTION)
        return stages

    def initialize_stage_states(self, work_order: WorkOrder) -> None:
        stage_states = [
            WorkOrderStageState(
                work_order_id=work_order.id,
                stage=stage,
                status=StageStatus.NOT_STARTED,
            )
            for stage in self.get_configured_stage_states_sequence(
                work_order.coating_type,
                skips_surface_preparation=self._omits_surface_preparation_stage(work_order),
            )
        ]
        self.repository.add_stage_states(stage_states)

    def initialize_quantity_tracking(self, work_order: WorkOrder) -> None:
        main_batch = WorkOrderQuantityBatch(
            work_order_id=work_order.id,
            quantity=work_order.total_quantity,
            type=QuantityBatchType.MAIN,
            parent_batch_id=None,
            is_active=True,
            current_stage=None,
            current_stage_status=None,
            is_partial=False,
        )
        self.repository.add_quantity_batch(main_batch)
        work_order.current_active_batch_id = main_batch.id

    def list_stage_states(self, work_order_id: int) -> Sequence[WorkOrderStageState]:
        return self.repository.list_stage_states(work_order_id)

    @staticmethod
    def get_surface_preparation_counted_quantity(work_order: WorkOrder) -> int | None:
        for stage_state in work_order.stage_states:
            if stage_state.stage == ProcessStage.SURFACE_PREPARATION:
                return stage_state.counted_quantity
        return None

    def get_surface_preparation_quantity_difference(self, work_order: WorkOrder) -> int | None:
        counted_quantity = self.get_surface_preparation_counted_quantity(work_order)
        if counted_quantity is None:
            return None
        return counted_quantity - work_order.total_quantity

    def get_work_order_process(self, work_order_id: int) -> WorkOrder:
        work_order = self.repository.get_work_order_with_stage_states(work_order_id)
        if work_order is None:
            raise ResourceNotFoundError(f"Work order {work_order_id} not found.")
        return work_order

    def transition_stage(
        self,
        work_order_id: int,
        stage: ProcessStage,
        target_status: StageStatus,
        station_context: StationContext | None = None,
    ) -> WorkOrderStageState:
        with self._serialize_process_mutation(work_order_id):
            work_order = self.get_work_order_process(work_order_id)
            self._ensure_stage_station_action(work_order, stage, station_context)
            resource_keys = self._get_stage_resource_keys(work_order, stage, target_status)
            with self._serialize_stage_resources(resource_keys):
                if resource_keys:
                    self._ensure_stage_resources_available(work_order, stage, target_status)

                stage_state = self._get_stage_state(work_order, stage)
                self._validate_transition(work_order, stage_state, target_status)
                if resource_keys:
                    self._acquire_stage_resource_locks(work_order, stage, target_status)
                stage_state.status = target_status
                stage_state.updated_at = datetime.now(UTC)

                if (
                    stage == ProcessStage.HANGING
                    and target_status == StageStatus.DONE
                    and work_order.production_type == ProductionType.AUTOMATIC
                ):
                    production_state = self._get_stage_state(work_order, ProcessStage.PRODUCTION)
                    if production_state.status == StageStatus.NOT_STARTED:
                        production_state.status = StageStatus.IN_PROGRESS
                        production_state.updated_at = stage_state.updated_at
                    packing_state = self._get_stage_state(work_order, ProcessStage.PACKING)
                    if packing_state.status == StageStatus.NOT_STARTED:
                        packing_state.status = StageStatus.IN_PROGRESS
                        packing_state.updated_at = stage_state.updated_at

                if target_status != StageStatus.IN_PROGRESS:
                    self._release_inactive_resource_locks(work_order)

                self._record_stage_audit_event(
                    work_order=work_order,
                    stage=stage,
                    target_status=target_status,
                    station_context=station_context,
                    batch_id=None,
                )

                try:
                    self.repository.commit()
                except Exception:
                    self.repository.rollback()
                    raise

                return stage_state

    def list_stage_work_orders(
        self,
        stage: ProcessStage,
        production_type: ProductionType | None = None,
        queue_namespace: QueueNamespace | None = None,
    ) -> list[ProcessStageWorkOrderRead]:
        work_orders = self.repository.list_work_orders_with_stage(stage, production_type, queue_namespace)
        items: list[ProcessStageWorkOrderRead] = []
        for work_order in work_orders:
            tracked_batches = self._get_batches_visible_in_stage(work_order, stage, include_done=True)
            if tracked_batches:
                items.extend(self._to_stage_work_order_read(work_order, stage, batch=batch) for batch in tracked_batches)
                continue

            if self.is_visible_in_stage(work_order, stage, production_type, include_done=True):
                items.append(self._to_stage_work_order_read(work_order, stage))

        return items

    def start_stage(
        self,
        work_order_id: int,
        stage: ProcessStage,
        batch_id: int | None = None,
        counted_quantity: int | None = None,
        station_context: StationContext | None = None,
    ) -> ProcessStageWorkOrderRead:
        with self._serialize_process_mutation(work_order_id):
            work_order = self.get_work_order_process(work_order_id)
            self._ensure_stage_station_action(work_order, stage, station_context)
            target_batch = self._resolve_batch_for_stage(work_order, stage, batch_id)
            if target_batch is not None:
                resource_keys = self._get_stage_resource_keys(work_order, stage, StageStatus.IN_PROGRESS)
                with self._serialize_stage_resources(resource_keys):
                    self._ensure_stage_resources_available(work_order, stage, StageStatus.IN_PROGRESS)
                    return self._start_tracked_batch_stage(
                        work_order,
                        target_batch,
                        stage,
                        counted_quantity=counted_quantity,
                        station_context=station_context,
                    )

            if self._is_automatic_production_preview_stage(work_order, stage):
                raise InvalidProcessStageTransitionError(self.AUTOMATIC_PRODUCTION_MANUAL_ACTION_ERROR)

            if self._is_skipped_surface_preparation(work_order, stage):
                raise InvalidProcessStageTransitionError(self._get_surface_preparation_skipped_message(work_order))

            self._store_stage_start_data(work_order, stage, counted_quantity)

            self.transition_stage(work_order_id, stage, StageStatus.IN_PROGRESS, station_context=station_context)
            work_order = self.get_work_order_process(work_order_id)

            return self._to_stage_work_order_read(work_order, stage)

    def finish_stage(
        self,
        work_order_id: int,
        stage: ProcessStage,
        batch_id: int | None = None,
        counted_quantity: int | None = None,
        station_context: StationContext | None = None,
    ) -> ProcessStageWorkOrderRead:
        with self._serialize_process_mutation(work_order_id):
            work_order = self.get_work_order_process(work_order_id)
            self._ensure_stage_station_action(work_order, stage, station_context)
            target_batch = self._resolve_batch_for_stage(work_order, stage, batch_id)
            if target_batch is not None:
                return self._finish_tracked_batch_stage(
                    work_order,
                    target_batch,
                    stage,
                    counted_quantity=counted_quantity,
                    station_context=station_context,
                )

            if self._is_automatic_production_preview_stage(work_order, stage):
                raise InvalidProcessStageTransitionError(self.AUTOMATIC_PRODUCTION_MANUAL_ACTION_ERROR)

            stage_state = self._get_stage_state(work_order, stage)
            if stage_state.status == StageStatus.DONE:
                return self._to_stage_work_order_read(work_order, stage)

            if stage == ProcessStage.SURFACE_PREPARATION:
                self._store_surface_preparation_counted_quantity(work_order, counted_quantity)
                self._ensure_surface_preparation_counted_quantity(work_order)

            if stage == ProcessStage.PACKING:
                return self.complete_packing(
                    work_order_id,
                    counted_quantity=work_order.current_active_quantity,
                    ok_quantity=work_order.current_active_quantity,
                    correction_quantity=0,
                    station_context=station_context,
                )

            self.transition_stage(work_order_id, stage, StageStatus.DONE, station_context=station_context)
            work_order = self.get_work_order_process(work_order_id)

            if stage == ProcessStage.DECORAL_PRODUCTION:
                active_quantity = work_order.current_active_quantity
                if active_quantity > 0:
                    work_order.completed_quantity += active_quantity
                    active_batch = work_order.active_batch
                    if active_batch is not None:
                        active_batch.is_active = False
                    work_order.current_active_batch_id = None
                    try:
                        self.repository.commit()
                    except Exception:
                        self.repository.rollback()
                        raise
                    work_order = self.get_work_order_process(work_order_id)

                    finalized_work_order = self._finalize_completion_chain_if_ready(work_order)
                    if finalized_work_order is not None:
                        work_order = self.get_work_order_process(work_order_id)

            return self._to_stage_work_order_read(work_order, stage)

    def reopen_stage(
        self,
        work_order_id: int,
        stage: ProcessStage,
        batch_id: int | None = None,
        station_context: StationContext | None = None,
    ) -> ProcessStageWorkOrderRead:
        work_order = self.get_work_order_process(work_order_id)
        self._ensure_stage_station_action(work_order, stage, station_context)
        target_batch = self._resolve_batch_for_stage(work_order, stage, batch_id)
        if target_batch is not None:
            return self._reopen_tracked_batch_stage(work_order, target_batch, stage, station_context=station_context)

        if self._is_automatic_production_preview_stage(work_order, stage):
            raise InvalidProcessStageTransitionError(self.AUTOMATIC_PRODUCTION_MANUAL_ACTION_ERROR)

        if self._is_skipped_surface_preparation(work_order, stage):
            raise InvalidProcessStageTransitionError(self._get_surface_preparation_skipped_message(work_order))

        stage_state = self._get_stage_state(work_order, stage)

        if work_order.current_active_quantity == 0:
            raise InvalidProcessStageTransitionError(
                "Cannot reopen process stages because the work order has no active quantity remaining."
            )

        if stage_state.status == StageStatus.DONE:
            target_status = StageStatus.IN_PROGRESS
        elif stage_state.status == StageStatus.IN_PROGRESS:
            target_status = StageStatus.NOT_STARTED
        else:
            raise InvalidProcessStageTransitionError(
                f"Cannot reopen stage {stage.value} from {stage_state.status.value}."
            )

        self.transition_stage(work_order_id, stage, target_status, station_context=station_context)
        work_order = self.get_work_order_process(work_order_id)
        return self._to_stage_work_order_read(work_order, stage)

    def complete_packing(
        self,
        work_order_id: int,
        *,
        counted_quantity: int,
        ok_quantity: int,
        correction_quantity: int,
        correction_profiles_quantity: int | None = None,
        correction_accessories_quantity: int | None = None,
        correction_reason_category: str | None = None,
        correction_reason_note: str | None = None,
        batch_id: int | None = None,
        station_context: StationContext | None = None,
    ) -> ProcessStageWorkOrderRead:
        with self._serialize_process_mutation(work_order_id):
            work_order = self.get_work_order_process(work_order_id)
            self._ensure_packing_station_action(station_context)
            normalized_correction_reason_category, normalized_correction_reason_note = self._validate_correction_reason(
                correction_quantity,
                correction_reason_category,
                correction_reason_note,
            )
            correction_category_fields = self._validate_correction_category_split(
                correction_quantity,
                correction_profiles_quantity,
                correction_accessories_quantity,
            )
            target_batch = self._resolve_batch_for_stage(work_order, ProcessStage.PACKING, batch_id)
            if target_batch is not None:
                return self._complete_tracked_batch_packing(
                    work_order,
                    target_batch,
                    counted_quantity=counted_quantity,
                    ok_quantity=ok_quantity,
                    correction_quantity=correction_quantity,
                    correction_category_fields=correction_category_fields,
                    correction_reason_category=normalized_correction_reason_category,
                    correction_reason_note=normalized_correction_reason_note,
                    station_context=station_context,
                )

            packing_state = self._get_stage_state(work_order, ProcessStage.PACKING)
            hanging_state = self._get_stage_state(work_order, ProcessStage.HANGING)

            if packing_state.status == StageStatus.DONE:
                return self._to_idempotent_packing_response(work_order)

            if self._is_in_correction_round(work_order) and packing_state.status == StageStatus.NOT_STARTED:
                return self._to_idempotent_packing_response(work_order)

            if work_order.production_type == ProductionType.AUTOMATIC and hanging_state.status == StageStatus.IN_PROGRESS:
                raise InvalidProcessStageTransitionError("Automatic hanging must be finished before packing.")

            self._ensure_automatic_paint_consumption_recorded_before_packing(work_order)

            if packing_state.status != StageStatus.IN_PROGRESS:
                raise InvalidProcessStageTransitionError("Packing can be completed only from IN_PROGRESS state.")

            active_batch = work_order.active_batch
            if active_batch is None:
                raise InvalidProcessStageTransitionError("No active quantity batch available for packing.")

            if ok_quantity + correction_quantity != counted_quantity:
                raise InvalidProcessStageTransitionError(
                    "Packing quantities must add up to the counted quantity."
                )

            if ok_quantity < 0 or correction_quantity < 0:
                raise InvalidProcessStageTransitionError("Packing quantities cannot be negative.")

            planned_quantity = active_batch.quantity
            if self._is_in_correction_round(work_order):
                required_counted_quantity = planned_quantity
            else:
                actual_received_quantity = self._get_surface_preparation_actual_quantity(work_order)
                required_counted_quantity = actual_received_quantity if actual_received_quantity is not None else planned_quantity
            if counted_quantity != required_counted_quantity:
                raise InvalidProcessStageTransitionError(
                    "Policzona ilość musi odpowiadać rzeczywistej ilości z przygotowania powierzchni."
                    if not self._is_in_correction_round(work_order) and self._get_surface_preparation_actual_quantity(work_order) is not None
                    else "Policzona ilość różni się od planowanej. Wyjaśnij brakujące sztuki."
                )

            packing_state.counted_quantity = counted_quantity
            packing_state.updated_at = datetime.now(UTC)

            production_state = self._get_stage_state(work_order, ProcessStage.PRODUCTION)

            if correction_quantity > 0:
                if work_order.coating_type == CoatingType.DECORAL:
                    response_stage, response_batch = self._complete_packing_with_correction_order(
                        work_order,
                        active_batch,
                        packing_state,
                        production_state,
                        planned_quantity=active_batch.quantity,
                        ok_quantity=ok_quantity,
                        correction_quantity=correction_quantity,
                        correction_category_fields=correction_category_fields,
                        correction_reason_category=normalized_correction_reason_category,
                        correction_reason_note=normalized_correction_reason_note,
                        station_context=station_context,
                    )
                else:
                    self._reset_to_correction_planning(
                        work_order,
                        active_batch,
                        ok_quantity=ok_quantity,
                        correction_quantity=correction_quantity,
                        correction_reason_category=normalized_correction_reason_category,
                        correction_reason_note=normalized_correction_reason_note,
                        station_context=station_context,
                    )
                    response_stage = ProcessStage.PACKING
                    response_batch = None
                self._release_inactive_resource_locks(work_order)
                self._record_packing_audit_event(
                    work_order=work_order,
                    station_context=station_context,
                    batch_id=active_batch.id,
                    counted_quantity=counted_quantity,
                    ok_quantity=ok_quantity,
                    correction_quantity=correction_quantity,
                    correction_category_fields=correction_category_fields,
                )
                self._commit_process_changes()
                refreshed_work_order = self.get_work_order_process(work_order_id)
                if response_batch is not None:
                    refreshed_batch = self._get_batch(refreshed_work_order, response_batch.id)
                    return self._to_stage_work_order_read(refreshed_work_order, response_stage, batch=refreshed_batch)
                return self._to_stage_work_order_read(refreshed_work_order, ProcessStage.PACKING)
            else:
                packing_state.status = StageStatus.DONE
                packing_state.updated_at = datetime.now(UTC)
                if work_order.coating_type == CoatingType.RAL:
                    work_order.completed_quantity += ok_quantity
                    work_order.current_active_batch_id = None
                    active_batch.is_active = False

            if work_order.production_type == ProductionType.AUTOMATIC:
                production_state.status = StageStatus.DONE
                production_state.updated_at = datetime.now(UTC)

            if work_order.coating_type == CoatingType.DECORAL and correction_quantity == 0:
                active_batch.is_active = True

            self._release_inactive_resource_locks(work_order)
            self._record_packing_audit_event(
                work_order=work_order,
                station_context=station_context,
                batch_id=active_batch.id,
                counted_quantity=counted_quantity,
                ok_quantity=ok_quantity,
                correction_quantity=correction_quantity,
                correction_category_fields=correction_category_fields,
            )

            try:
                self.repository.commit()
            except Exception:
                self.repository.rollback()
                raise

            refreshed_work_order = self.get_work_order_process(work_order_id)
            finalized_work_order = self._finalize_completion_chain_if_ready(refreshed_work_order)
            if finalized_work_order is not None:
                refreshed_work_order = self.get_work_order_process(work_order_id)
            return self._to_idempotent_packing_response(refreshed_work_order)

    def record_automatic_paint_consumption(
        self,
        work_order_id: int,
        *,
        consumed_paint_quantity_kg: float,
        station_context: StationContext | None = None,
    ) -> ProcessStageWorkOrderRead:
        with self._serialize_process_mutation(work_order_id):
            work_order = self.get_work_order_process(work_order_id)
            self._ensure_automatic_production_station_action(station_context)

            if work_order.production_type != ProductionType.AUTOMATIC:
                raise InvalidProcessStageTransitionError("Paint consumption can be recorded only for automatic production work orders.")

            hanging_state = self._get_stage_state(work_order, ProcessStage.HANGING)
            packing_state = self._get_stage_state(work_order, ProcessStage.PACKING)

            if hanging_state.status == StageStatus.NOT_STARTED:
                raise InvalidProcessStageTransitionError(self.AUTOMATIC_PAINT_CONSUMPTION_STAGE_ERROR)
            if packing_state.status == StageStatus.DONE:
                return self._to_stage_work_order_read(work_order, ProcessStage.PRODUCTION)
            if work_order.paint_code is None:
                raise InvalidProcessStageTransitionError(self.AUTOMATIC_PAINT_CONSUMPTION_CONFIGURATION_ERROR)

            previous_value = work_order.consumed_paint_quantity_kg
            if previous_value == consumed_paint_quantity_kg:
                return self._to_stage_work_order_read(work_order, ProcessStage.PRODUCTION)
            if previous_value > 0:
                raise InvalidProcessStageTransitionError(self.AUTOMATIC_PAINT_CONSUMPTION_ALREADY_RECORDED_ERROR)

            try:
                paint = self.paint_service.record_automatic_consumption(
                    ral_code=work_order.ral_code,
                    paint_producer=work_order.paint_producer,
                    paint_code=work_order.paint_code,
                    quantity_kg=consumed_paint_quantity_kg,
                    work_order_id=work_order.id,
                    station_context=station_context,
                )
            except InvalidPaintInventoryError as exc:
                raise InvalidProcessStageTransitionError(exc.detail) from exc

            work_order.paint_id = paint.id
            work_order.consumed_paint_quantity_kg = consumed_paint_quantity_kg
            work_order.updated_at = datetime.now(UTC)
            self._record_automatic_paint_consumption_audit_event(
                work_order=work_order,
                station_context=station_context,
                previous_value=previous_value,
                consumed_paint_quantity_kg=consumed_paint_quantity_kg,
            )

            try:
                self.repository.commit()
            except Exception:
                self.repository.rollback()
                raise

            refreshed_work_order = self.get_work_order_process(work_order_id)
            return self._to_stage_work_order_read(refreshed_work_order, ProcessStage.PRODUCTION)

    def list_visible_work_orders(
        self,
        stage: ProcessStage,
        production_type: ProductionType | None = None,
        include_done: bool = False,
        queue_namespace: QueueNamespace | None = None,
    ) -> list[WorkOrder]:
        work_orders = self.repository.list_work_orders_with_stage(stage, production_type, queue_namespace)
        return [
            work_order
            for work_order in work_orders
            if self.is_visible_in_stage(work_order, stage, production_type, include_done=include_done)
        ]

    def is_visible_in_stage(
        self,
        work_order: WorkOrder,
        stage: ProcessStage,
        production_type: ProductionType | None = None,
        include_done: bool = False,
    ) -> bool:
        if self._has_incomplete_marker(work_order):
            return False

        if not self._is_planned(work_order):
            return False

        if self._is_skipped_surface_preparation(work_order, stage):
            return False

        if self._uses_batch_tracking(work_order):
            if stage == ProcessStage.PRODUCTION and production_type is not None and work_order.production_type != production_type:
                return False
            return bool(self._get_batches_visible_in_stage(work_order, stage, include_done=include_done))

        stage_sequence = self.get_stage_sequence_for_work_order(work_order)
        if stage not in stage_sequence:
            return False

        stage_state = self._get_stage_state(work_order, stage)
        allowed_statuses = {StageStatus.NOT_STARTED, StageStatus.IN_PROGRESS}
        if include_done:
            allowed_statuses.add(StageStatus.DONE)

        if self._is_automatic_production_preview_stage(work_order, stage):
            return self._is_visible_in_automatic_production_preview(work_order, production_type)

        if self._is_visible_in_automatic_packing(work_order, stage, stage_state.status):
            return True

        if stage_state.status not in allowed_statuses:
            return False

        previous_stage = self._get_previous_stage(stage_sequence, stage)
        if previous_stage is not None:
            previous_state = self._get_stage_state(work_order, previous_stage)
            if previous_state.status != StageStatus.DONE:
                return False

        if stage == ProcessStage.PRODUCTION:
            if production_type is not None and work_order.production_type != production_type:
                return False

        return True

    @staticmethod
    def _is_planned(work_order: WorkOrder) -> bool:
        return work_order.production_type is not None and work_order.queue_position is not None

    def get_display_status(self, work_order: WorkOrder) -> ProcessDisplayStatus:
        if self._has_incomplete_marker(work_order):
            return ProcessDisplayStatus.INCOMPLETE

        if self._is_complete_for_display(work_order):
            return ProcessDisplayStatus.READY

        if not self._is_planned(work_order):
            return ProcessDisplayStatus.TO_BE_PLANNED

        if self._uses_batch_tracking(work_order):
            active_batches = [batch for batch in work_order.active_batches if batch.current_stage is not None]
            if active_batches:
                return self._get_display_status_for_tracked_batches(work_order)

        if self._has_open_corrections(work_order):
            return ProcessDisplayStatus.WAITING_FOR_CORRECTIONS

        if self._uses_batch_tracking(work_order):
            return self._get_display_status_for_tracked_batches(work_order)

        if work_order.production_type == ProductionType.AUTOMATIC:
            packing_state = self._get_stage_state(work_order, ProcessStage.PACKING)
            if packing_state.status == StageStatus.IN_PROGRESS:
                return ProcessDisplayStatus.PACKING

        stage_sequence = self.get_stage_sequence_for_work_order(work_order)
        for stage in stage_sequence:
            stage_state = self._get_stage_state(work_order, stage)
            if stage_state.status != StageStatus.DONE:
                return self._get_display_status_for_stage(work_order, stage)

        return ProcessDisplayStatus.READY

    def get_waiting_ok_quantity(self, work_order: WorkOrder) -> int:
        if not self._has_open_corrections(work_order):
            return 0

        pending_correction_quantity = self.get_pending_correction_quantity(work_order)
        return max(0, work_order.total_quantity - work_order.completed_quantity - pending_correction_quantity)

    def get_pending_correction_quantity(self, work_order: WorkOrder) -> int:
        pending_quantity = 0
        for correction_order in work_order.correction_orders:
            if self._is_complete_for_display(correction_order):
                continue
            pending_quantity += max(0, correction_order.total_quantity - correction_order.completed_quantity)
        return pending_quantity

    def get_total_progress_quantity(self, work_order: WorkOrder) -> int:
        progress_quantity = work_order.completed_quantity + self.get_waiting_ok_quantity(work_order)
        progress_quantity += sum(correction_order.completed_quantity for correction_order in work_order.correction_orders)
        return min(work_order.total_quantity, progress_quantity)

    def get_display_status_label(self, work_order: WorkOrder) -> str:
        return self.get_display_status(work_order).polish_label

    def get_queue_resource_block(self, work_order: WorkOrder) -> tuple[str, str] | None:
        if (
            self._has_incomplete_marker(work_order)
            or self._is_complete_for_display(work_order)
            or not self._is_planned(work_order)
        ):
            return None
        if work_order.production_type != ProductionType.AUTOMATIC:
            return None

        hanging_state = self._get_stage_state(work_order, ProcessStage.HANGING)
        if hanging_state.status == StageStatus.NOT_STARTED and self._is_stage_ready_for_next_action(
            work_order,
            ProcessStage.HANGING,
        ):
            if self._find_active_hanging_conflict(work_order.id) is not None:
                return "HANGING", self.QUEUE_RESOURCE_BLOCK_REASONS["HANGING"]

        if hanging_state.status == StageStatus.IN_PROGRESS:
            if self._find_active_automatic_line_conflict(work_order.id) is not None:
                return "AUTOMATIC_LINE", self.QUEUE_RESOURCE_BLOCK_REASONS["AUTOMATIC_LINE"]

        return None

    def _is_stage_ready_for_next_action(self, work_order: WorkOrder, stage: ProcessStage) -> bool:
        stage_sequence = self.get_actionable_stage_sequence_for_work_order(work_order)
        previous_stage = self._get_previous_stage(stage_sequence, stage)
        if previous_stage is None:
            return True
        previous_state = self._get_stage_state(work_order, previous_stage)
        return previous_state.status == StageStatus.DONE

    @staticmethod
    def build_stage_status_view(status: StageStatus) -> StageStatusView:
        return StageStatusView(value=status, label=status.polish_label)

    @staticmethod
    def _get_display_status_for_stage(work_order: WorkOrder, stage: ProcessStage) -> ProcessDisplayStatus:
        if stage == ProcessStage.SURFACE_PREPARATION:
            return ProcessDisplayStatus.SURFACE_PREPARATION

        if stage == ProcessStage.HANGING:
            return ProcessDisplayStatus.HANGING

        if stage == ProcessStage.PRODUCTION:
            if work_order.production_type == ProductionType.AUTOMATIC:
                return ProcessDisplayStatus.PRODUCTION_AUTOMATIC
            return ProcessDisplayStatus.PRODUCTION_MANUAL

        if stage == ProcessStage.DECORAL_PRODUCTION:
            return ProcessDisplayStatus.DECORAL_PRODUCTION

        return ProcessDisplayStatus.PACKING

    def _get_display_status_for_tracked_batches(self, work_order: WorkOrder) -> ProcessDisplayStatus:
        active_batches = [batch for batch in work_order.active_batches if batch.current_stage is not None]
        if not active_batches:
            return ProcessDisplayStatus.READY if work_order.completed_quantity == work_order.total_quantity else ProcessDisplayStatus.PACKING

        if any(batch.current_stage == ProcessStage.HANGING for batch in active_batches):
            return ProcessDisplayStatus.HANGING
        if any(batch.current_stage == ProcessStage.PRODUCTION for batch in active_batches):
            return ProcessDisplayStatus.PRODUCTION_MANUAL
        if any(batch.current_stage == ProcessStage.PACKING for batch in active_batches):
            return ProcessDisplayStatus.PACKING
        if any(batch.current_stage == ProcessStage.DECORAL_PRODUCTION for batch in active_batches):
            return ProcessDisplayStatus.DECORAL_PRODUCTION
        return ProcessDisplayStatus.READY

    def _validate_transition(
        self,
        work_order: WorkOrder,
        stage_state: WorkOrderStageState,
        target_status: StageStatus,
    ) -> None:
        stage_sequence = self.get_stage_sequence_for_work_order(work_order)
        if stage_state.stage not in stage_sequence:
            raise InvalidProcessStageTransitionError(
                f"Stage {stage_state.stage.value} is not part of the workflow for work order {work_order.id}."
            )

        if self._is_automatic_production_preview_stage(work_order, stage_state.stage):
            raise InvalidProcessStageTransitionError(self.AUTOMATIC_PRODUCTION_MANUAL_ACTION_ERROR)

        if self._is_skipped_surface_preparation(work_order, stage_state.stage):
            raise InvalidProcessStageTransitionError(self._get_surface_preparation_skipped_message(work_order))

        allowed_transitions = {
            StageStatus.NOT_STARTED: {StageStatus.IN_PROGRESS},
            StageStatus.IN_PROGRESS: {StageStatus.DONE, StageStatus.NOT_STARTED},
            StageStatus.DONE: {StageStatus.IN_PROGRESS, StageStatus.NOT_STARTED},
        }
        current_status = stage_state.status
        if target_status not in allowed_transitions[current_status]:
            raise InvalidProcessStageTransitionError(
                f"Cannot transition stage {stage_state.stage.value} from {current_status.value} to {target_status.value}."
            )

        if target_status in {StageStatus.IN_PROGRESS, StageStatus.DONE}:
            previous_stage = self._get_previous_stage(self.get_actionable_stage_sequence_for_work_order(work_order), stage_state.stage)
            if previous_stage is not None:
                previous_state = self._get_stage_state(work_order, previous_stage)
                if previous_state.status != StageStatus.DONE:
                    raise InvalidProcessStageTransitionError(
                        f"Stage {stage_state.stage.value} requires {previous_stage.value} to be DONE first."
                    )

    def _ensure_stage_station_action(
        self,
        work_order: WorkOrder,
        stage: ProcessStage,
        station_context: StationContext | None,
    ) -> None:
        ensure_station_allowed(
            station_context,
            allowed_station_ids=self._get_allowed_stage_station_ids(work_order, stage),
            action=f"{stage.value} stage actions",
        )

    @staticmethod
    def _ensure_packing_station_action(station_context: StationContext | None) -> None:
        ensure_station_allowed(
            station_context,
            allowed_station_ids={StationId.PACKING},
            action="PACKING actions",
        )

    @staticmethod
    def _ensure_automatic_production_station_action(station_context: StationContext | None) -> None:
        ensure_station_allowed(
            station_context,
            allowed_station_ids={StationId.AUTOMATIC_PRODUCTION},
            action="AUTOMATIC_PRODUCTION actions",
        )

    @staticmethod
    def _is_automatic_paint_tracking_required(work_order: WorkOrder) -> bool:
        return work_order.production_type == ProductionType.AUTOMATIC

    def _ensure_automatic_paint_consumption_recorded_before_packing(self, work_order: WorkOrder) -> None:
        if not self._is_automatic_paint_tracking_required(work_order):
            return
        if work_order.consumed_paint_quantity_kg <= 0:
            raise InvalidProcessStageTransitionError(self.AUTOMATIC_PAINT_CONSUMPTION_REQUIRED_ERROR)

    @classmethod
    def _validate_correction_reason(
        cls,
        correction_quantity: int,
        correction_reason_category: str | None,
        correction_reason_note: str | None,
    ) -> tuple[str | None, str | None]:
        normalized_category = cls._normalize_optional_text(correction_reason_category)
        normalized_note = cls._normalize_optional_text(correction_reason_note)
        if normalized_category is not None and len(normalized_category) > 64:
            raise InvalidProcessStageTransitionError("Correction reason category must be at most 64 characters.")
        if normalized_note is not None and len(normalized_note) > 500:
            raise InvalidProcessStageTransitionError("Correction reason note must be at most 500 characters.")
        if correction_quantity > 0 and normalized_category is None:
            raise InvalidProcessStageTransitionError("Correction reason is required when correction quantity is greater than zero.")
        if correction_quantity == 0 and (normalized_category is not None or normalized_note is not None):
            raise InvalidProcessStageTransitionError("Correction reason can only be set when correction quantity is greater than zero.")
        return normalized_category, normalized_note

    @staticmethod
    def _validate_correction_category_split(
        correction_quantity: int,
        correction_profiles_quantity: int | None,
        correction_accessories_quantity: int | None,
    ) -> dict[str, int | bool | None]:
        if correction_quantity == 0:
            if correction_profiles_quantity is not None or correction_accessories_quantity is not None:
                raise InvalidProcessStageTransitionError(
                    "Correction category quantities can only be set when correction quantity is greater than zero."
                )
            return {}

        if correction_profiles_quantity is None or correction_accessories_quantity is None:
            raise InvalidProcessStageTransitionError(
                "Correction profile and accessory quantities are required when correction quantity is greater than zero."
            )
        if correction_profiles_quantity < 0 or correction_accessories_quantity < 0:
            raise InvalidProcessStageTransitionError("Correction category quantities cannot be negative.")
        if correction_profiles_quantity + correction_accessories_quantity != correction_quantity:
            raise InvalidProcessStageTransitionError(
                "Correction profile and accessory quantities must add up to correction quantity."
            )

        return {
            "profiles_quantity": correction_profiles_quantity,
            "profiles_to_count": False,
            "accessories_quantity": correction_accessories_quantity,
            "accessories_to_count": False,
        }

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        if value is None:
            return None
        normalized_value = value.strip()
        return normalized_value or None

    @staticmethod
    def _get_allowed_stage_station_ids(work_order: WorkOrder, stage: ProcessStage) -> set[StationId]:
        if stage == ProcessStage.SURFACE_PREPARATION:
            return {StationId.SURFACE_PREPARATION}
        if stage == ProcessStage.HANGING:
            return {StationId.HANGING}
        if stage == ProcessStage.PRODUCTION:
            if work_order.production_type == ProductionType.AUTOMATIC:
                return {StationId.AUTOMATIC_PRODUCTION}
            return {StationId.MANUAL_PRODUCTION}
        if stage == ProcessStage.PACKING:
            return {StationId.PACKING}
        if stage == ProcessStage.DECORAL_PRODUCTION:
            return {StationId.DECORAL_PRODUCTION}
        return {StationId.SYSTEM}

    def get_correction_return_stage(self, work_order: WorkOrder) -> ProcessStage:
        if work_order.production_type == ProductionType.AUTOMATIC:
            return ProcessStage.HANGING

        stage_sequence = self.get_stage_sequence_for_work_order(work_order)
        if self.DEFAULT_CORRECTION_RETURN_STAGE in stage_sequence:
            return self.DEFAULT_CORRECTION_RETURN_STAGE
        return stage_sequence[0]

    def _reset_stage_states_for_active_batch(self, work_order: WorkOrder, return_stage: ProcessStage) -> None:
        stage_sequence = self.get_actionable_stage_sequence_for_work_order(work_order)
        return_stage_index = stage_sequence.index(return_stage)
        current_timestamp = datetime.now(UTC)

        for index, stage in enumerate(stage_sequence):
            stage_state = self._get_stage_state(work_order, stage)
            stage_state.status = StageStatus.DONE if index < return_stage_index else StageStatus.NOT_STARTED
            stage_state.updated_at = current_timestamp

        if work_order.production_type == ProductionType.AUTOMATIC:
            production_state = self._get_stage_state(work_order, ProcessStage.PRODUCTION)
            production_state.status = StageStatus.NOT_STARTED
            production_state.updated_at = current_timestamp

    def get_actionable_stage_sequence_for_work_order(self, work_order: WorkOrder) -> list[ProcessStage]:
        stage_sequence = self.get_stage_sequence_for_work_order(work_order)
        if work_order.production_type == ProductionType.AUTOMATIC:
            return [stage for stage in stage_sequence if stage != ProcessStage.PRODUCTION]
        return stage_sequence

    @staticmethod
    def _is_automatic_production_preview_stage(work_order: WorkOrder, stage: ProcessStage) -> bool:
        return work_order.production_type == ProductionType.AUTOMATIC and stage == ProcessStage.PRODUCTION

    @staticmethod
    def _skips_surface_preparation(work_order: WorkOrder) -> bool:
        if work_order.is_correction or work_order.work_order_kind == WorkOrderKind.PRZEMALOWANKA:
            return True
        active_batch = work_order.active_batch
        return active_batch is not None and active_batch.parent_batch_id is not None

    @staticmethod
    def _omits_surface_preparation_stage(work_order: WorkOrder) -> bool:
        return work_order.work_order_kind == WorkOrderKind.PRZEMALOWANKA

    def _is_skipped_surface_preparation(self, work_order: WorkOrder, stage: ProcessStage) -> bool:
        return stage == ProcessStage.SURFACE_PREPARATION and self._skips_surface_preparation(work_order)

    @staticmethod
    def _get_surface_preparation_skipped_message(work_order: WorkOrder) -> str:
        if work_order.is_correction:
            return "Correction orders do not go through surface preparation."
        if work_order.work_order_kind == WorkOrderKind.PRZEMALOWANKA:
            return "Przemalowanka work orders do not go through surface preparation."
        return "Correction rounds do not go through surface preparation."

    def _is_visible_in_automatic_production_preview(
        self,
        work_order: WorkOrder,
        production_type: ProductionType | None,
    ) -> bool:
        if production_type is not None and work_order.production_type != production_type:
            return False

        hanging_state = self._get_stage_state(work_order, ProcessStage.HANGING)
        packing_state = self._get_stage_state(work_order, ProcessStage.PACKING)
        production_state = self._get_stage_state(work_order, ProcessStage.PRODUCTION)

        if packing_state.status == StageStatus.DONE:
            return False

        if hanging_state.status == StageStatus.NOT_STARTED:
            return self._is_stage_ready_for_next_action(work_order, ProcessStage.HANGING)

        if hanging_state.status == StageStatus.IN_PROGRESS:
            return True

        return production_state.status == StageStatus.IN_PROGRESS

    def _get_automatic_production_preview_display_stage(self, work_order: WorkOrder) -> ProcessStage:
        hanging_state = self._get_stage_state(work_order, ProcessStage.HANGING)
        if hanging_state.status != StageStatus.DONE:
            return ProcessStage.HANGING
        return ProcessStage.PRODUCTION

    def _is_visible_in_automatic_packing(
        self,
        work_order: WorkOrder,
        stage: ProcessStage,
        stage_status: StageStatus,
    ) -> bool:
        if stage != ProcessStage.PACKING or work_order.production_type != ProductionType.AUTOMATIC:
            return False

        if stage_status not in {StageStatus.NOT_STARTED, StageStatus.IN_PROGRESS}:
            return False

        hanging_state = self._get_stage_state(work_order, ProcessStage.HANGING)
        return hanging_state.status in {StageStatus.IN_PROGRESS, StageStatus.DONE}

    def _get_automatic_packing_display_stage(self, work_order: WorkOrder) -> ProcessStage:
        hanging_state = self._get_stage_state(work_order, ProcessStage.HANGING)
        if hanging_state.status != StageStatus.DONE:
            return ProcessStage.HANGING
        return ProcessStage.PACKING

    def _get_batches_visible_in_stage(
        self,
        work_order: WorkOrder,
        stage: ProcessStage,
        *,
        include_done: bool,
    ) -> list[WorkOrderQuantityBatch]:
        if not self._uses_batch_tracking(work_order):
            return []

        visible_batches: list[WorkOrderQuantityBatch] = []
        for batch in self._get_ordered_batches(work_order):
            status = self._get_tracked_batch_stage_status(work_order, batch, stage)
            if status is None:
                continue
            if status == StageStatus.DONE and not include_done:
                continue
            if status != StageStatus.DONE and not batch.is_active:
                continue
            visible_batches.append(batch)
        return visible_batches

    def _get_tracked_batch_stage_status(
        self,
        work_order: WorkOrder,
        batch: WorkOrderQuantityBatch,
        stage: ProcessStage,
    ) -> StageStatus | None:
        if batch.current_stage is None:
            return None

        if stage == ProcessStage.PRODUCTION and work_order.production_type == ProductionType.AUTOMATIC:
            if batch.current_stage == ProcessStage.HANGING and batch.current_stage_status in {StageStatus.IN_PROGRESS, StageStatus.DONE}:
                return StageStatus.IN_PROGRESS
            if batch.current_stage == ProcessStage.PACKING and batch.current_stage_status in {StageStatus.NOT_STARTED, StageStatus.IN_PROGRESS}:
                return StageStatus.IN_PROGRESS
            return None

        if stage == ProcessStage.PACKING and work_order.production_type == ProductionType.AUTOMATIC:
            if batch.current_stage == ProcessStage.HANGING:
                return None

        if batch.current_stage != stage:
            return None

        return batch.current_stage_status

    def _resolve_batch_for_stage(
        self,
        work_order: WorkOrder,
        stage: ProcessStage,
        batch_id: int | None,
    ) -> WorkOrderQuantityBatch | None:
        if batch_id is not None:
            batch = self._get_batch(work_order, batch_id)
            return batch if batch.current_stage is not None else None

        if not self._uses_batch_tracking(work_order):
            return None

        candidate_batches = [batch for batch in work_order.active_batches if batch.current_stage == stage]
        if len(candidate_batches) == 1:
            return candidate_batches[0]
        return None

    def _start_tracked_batch_stage(
        self,
        work_order: WorkOrder,
        batch: WorkOrderQuantityBatch,
        stage: ProcessStage,
        counted_quantity: int | None = None,
        station_context: StationContext | None = None,
    ) -> ProcessStageWorkOrderRead:
        if stage == ProcessStage.PRODUCTION and work_order.production_type == ProductionType.AUTOMATIC:
            raise InvalidProcessStageTransitionError(self.AUTOMATIC_PRODUCTION_MANUAL_ACTION_ERROR)
        if batch.current_stage != stage or batch.current_stage_status != StageStatus.NOT_STARTED:
            raise InvalidProcessStageTransitionError(
                f"Cannot transition stage {stage.value} from {batch.current_stage_status.value if batch.current_stage_status else 'UNKNOWN'} to IN_PROGRESS."
            )

        self._store_stage_start_data(work_order, stage, counted_quantity)
        self._acquire_stage_resource_locks(work_order, stage, StageStatus.IN_PROGRESS)
        batch.current_stage_status = StageStatus.IN_PROGRESS
        self._sync_legacy_current_active_batch(work_order)
        self._record_stage_audit_event(
            work_order=work_order,
            stage=stage,
            target_status=StageStatus.IN_PROGRESS,
            station_context=station_context,
            batch_id=batch.id,
        )
        self._commit_process_changes()
        refreshed_work_order = self.get_work_order_process(work_order.id)
        refreshed_batch = self._get_batch(refreshed_work_order, batch.id)
        return self._to_stage_work_order_read(refreshed_work_order, stage, batch=refreshed_batch)

    def _finish_tracked_batch_stage(
        self,
        work_order: WorkOrder,
        batch: WorkOrderQuantityBatch,
        stage: ProcessStage,
        counted_quantity: int | None = None,
        station_context: StationContext | None = None,
    ) -> ProcessStageWorkOrderRead:
        if stage == ProcessStage.PACKING:
            raise InvalidProcessStageTransitionError(
                "Tracked batch packing must be completed with explicit counted quantity."
            )
        if stage == ProcessStage.PRODUCTION and work_order.production_type == ProductionType.AUTOMATIC:
            raise InvalidProcessStageTransitionError(self.AUTOMATIC_PRODUCTION_MANUAL_ACTION_ERROR)
        if self._has_tracked_batch_already_finished_stage(work_order, batch, stage):
            response_stage = batch.current_stage or stage
            return self._to_stage_work_order_read(work_order, response_stage, batch=batch)
        if batch.current_stage != stage or batch.current_stage_status != StageStatus.IN_PROGRESS:
            raise InvalidProcessStageTransitionError(
                f"Cannot transition stage {stage.value} from {batch.current_stage_status.value if batch.current_stage_status else 'UNKNOWN'} to DONE."
            )

        if stage == ProcessStage.SURFACE_PREPARATION:
            self._store_surface_preparation_counted_quantity(work_order, counted_quantity)
            self._ensure_surface_preparation_counted_quantity(work_order)

        response_stage = stage
        if stage == ProcessStage.SURFACE_PREPARATION:
            batch.current_stage = ProcessStage.HANGING if work_order.production_type == ProductionType.AUTOMATIC else ProcessStage.PRODUCTION
            batch.current_stage_status = StageStatus.NOT_STARTED
            response_stage = batch.current_stage
        elif stage == ProcessStage.HANGING:
            if work_order.production_type == ProductionType.AUTOMATIC:
                resource_keys = self._get_stage_resource_keys(work_order, stage, StageStatus.DONE)
                with self._serialize_stage_resources(resource_keys):
                    self._ensure_stage_resources_available(work_order, stage, StageStatus.DONE)
                    self._acquire_stage_resource_locks(work_order, stage, StageStatus.DONE)
            batch.current_stage = ProcessStage.PACKING if work_order.production_type == ProductionType.AUTOMATIC else ProcessStage.PRODUCTION
            batch.current_stage_status = (
                StageStatus.IN_PROGRESS if work_order.production_type == ProductionType.AUTOMATIC else StageStatus.NOT_STARTED
            )
            response_stage = batch.current_stage
        elif stage == ProcessStage.PRODUCTION:
            batch.current_stage = ProcessStage.PACKING
            batch.current_stage_status = StageStatus.NOT_STARTED
            response_stage = ProcessStage.PACKING
        elif stage == ProcessStage.DECORAL_PRODUCTION:
            batch.current_stage_status = StageStatus.DONE
            batch.is_active = False
            work_order.completed_quantity += batch.quantity
            self._sync_legacy_current_active_batch(work_order)
            self._record_stage_audit_event(
                work_order=work_order,
                stage=stage,
                target_status=StageStatus.DONE,
                station_context=station_context,
                batch_id=batch.id,
            )
            self._commit_process_changes()
            refreshed_work_order = self.get_work_order_process(work_order.id)
            finalized_work_order = self._finalize_completion_chain_if_ready(refreshed_work_order)
            if finalized_work_order is not None:
                refreshed_work_order = self.get_work_order_process(work_order.id)
            refreshed_batch = self._get_batch(refreshed_work_order, batch.id)
            return self._to_stage_work_order_read(refreshed_work_order, stage, batch=refreshed_batch)

        self._sync_legacy_current_active_batch(work_order)
        self._release_inactive_resource_locks(work_order)
        self._record_stage_audit_event(
            work_order=work_order,
            stage=stage,
            target_status=StageStatus.DONE,
            station_context=station_context,
            batch_id=batch.id,
        )
        self._commit_process_changes()
        refreshed_work_order = self.get_work_order_process(work_order.id)
        refreshed_batch = self._get_batch(refreshed_work_order, batch.id)
        return self._to_stage_work_order_read(refreshed_work_order, response_stage, batch=refreshed_batch)

    def _reopen_tracked_batch_stage(
        self,
        work_order: WorkOrder,
        batch: WorkOrderQuantityBatch,
        stage: ProcessStage,
        station_context: StationContext | None = None,
    ) -> ProcessStageWorkOrderRead:
        if batch.current_stage != stage or batch.current_stage_status not in {StageStatus.IN_PROGRESS, StageStatus.DONE}:
            raise InvalidProcessStageTransitionError(
                f"Cannot reopen stage {stage.value} from {batch.current_stage_status.value if batch.current_stage_status else 'UNKNOWN'}."
            )

        if batch.current_stage_status == StageStatus.DONE:
            raise InvalidProcessStageTransitionError("Finished tracked batches cannot be reopened.")

        batch.current_stage_status = StageStatus.NOT_STARTED
        batch.is_active = True
        self._sync_legacy_current_active_batch(work_order)
        self._release_inactive_resource_locks(work_order)
        self._record_stage_audit_event(
            work_order=work_order,
            stage=stage,
            target_status=StageStatus.NOT_STARTED,
            station_context=station_context,
            batch_id=batch.id,
        )
        self._commit_process_changes()
        refreshed_work_order = self.get_work_order_process(work_order.id)
        refreshed_batch = self._get_batch(refreshed_work_order, batch.id)
        return self._to_stage_work_order_read(refreshed_work_order, stage, batch=refreshed_batch)

    def _complete_tracked_batch_packing(
        self,
        work_order: WorkOrder,
        batch: WorkOrderQuantityBatch,
        *,
        counted_quantity: int,
        ok_quantity: int,
        correction_quantity: int,
        correction_category_fields: dict[str, int | bool | None],
        correction_reason_category: str | None,
        correction_reason_note: str | None,
        station_context: StationContext | None = None,
    ) -> ProcessStageWorkOrderRead:
        if batch.current_stage == ProcessStage.PACKING and batch.current_stage_status == StageStatus.DONE:
            return self._to_stage_work_order_read(work_order, ProcessStage.PACKING, batch=batch)

        if batch.current_stage != ProcessStage.PACKING or batch.current_stage_status != StageStatus.IN_PROGRESS:
            raise InvalidProcessStageTransitionError("Packing can be completed only from IN_PROGRESS state.")
        if ok_quantity < 0 or correction_quantity < 0:
            raise InvalidProcessStageTransitionError("Packing quantities cannot be negative.")
        if ok_quantity + correction_quantity != counted_quantity:
            raise InvalidProcessStageTransitionError("Packing quantities must add up to the counted quantity.")

        planned_quantity = batch.quantity
        if counted_quantity != planned_quantity:
            raise InvalidProcessStageTransitionError(
                "Policzona ilość różni się od planowanej. Wyjaśnij brakujące sztuki."
            )

        packing_state = self._get_stage_state(work_order, ProcessStage.PACKING)
        packing_state.counted_quantity = counted_quantity
        packing_state.updated_at = datetime.now(UTC)

        batch.is_active = False
        batch.current_stage = ProcessStage.PACKING
        batch.current_stage_status = StageStatus.DONE
        batch.is_partial = False

        created_batches: list[WorkOrderQuantityBatch] = []
        if work_order.coating_type == CoatingType.DECORAL and ok_quantity > 0:
            ok_batch = WorkOrderQuantityBatch(
                work_order_id=work_order.id,
                quantity=ok_quantity,
                type=QuantityBatchType.MAIN,
                parent_batch_id=batch.id,
                is_active=True,
                current_stage=ProcessStage.DECORAL_PRODUCTION,
                current_stage_status=StageStatus.NOT_STARTED,
                is_partial=correction_quantity > 0,
            )
            self.repository.add_quantity_batch(ok_batch)
            created_batches.append(ok_batch)

        if correction_quantity > 0:
            if work_order.coating_type == CoatingType.DECORAL:
                self._create_correction_work_order(
                    work_order,
                    correction_quantity,
                    correction_category_fields=correction_category_fields,
                    correction_reason_category=correction_reason_category,
                    correction_reason_note=correction_reason_note,
                    station_context=station_context,
                )
            else:
                self._reset_to_correction_planning(
                    work_order,
                    batch,
                    ok_quantity=ok_quantity,
                    correction_quantity=correction_quantity,
                    correction_reason_category=correction_reason_category,
                    correction_reason_note=correction_reason_note,
                    station_context=station_context,
                )
        elif ok_quantity > 0:
            work_order.completed_quantity += ok_quantity

        self._sync_legacy_current_active_batch(work_order)
        self._release_inactive_resource_locks(work_order)
        self._record_packing_audit_event(
            work_order=work_order,
            station_context=station_context,
            batch_id=batch.id,
            counted_quantity=counted_quantity,
            ok_quantity=ok_quantity,
            correction_quantity=correction_quantity,
            correction_category_fields=correction_category_fields,
        )
        self._commit_process_changes()

        refreshed_work_order = self.get_work_order_process(work_order.id)
        finalized_work_order = self._finalize_completion_chain_if_ready(refreshed_work_order)
        if finalized_work_order is not None:
            refreshed_work_order = self.get_work_order_process(work_order.id)
        if created_batches:
            preferred_batch = created_batches[-1]
            refreshed_batch = self._get_batch(refreshed_work_order, preferred_batch.id)
            response_stage = refreshed_batch.current_stage or ProcessStage.PACKING
            return self._to_stage_work_order_read(refreshed_work_order, response_stage, batch=refreshed_batch)

        refreshed_batch = self._get_batch(refreshed_work_order, batch.id)
        return self._to_stage_work_order_read(refreshed_work_order, ProcessStage.PACKING, batch=refreshed_batch)

    def _complete_packing_with_correction_order(
        self,
        work_order: WorkOrder,
        active_batch: WorkOrderQuantityBatch,
        packing_state: WorkOrderStageState,
        production_state: WorkOrderStageState,
        *,
        planned_quantity: int,
        ok_quantity: int,
        correction_quantity: int,
        correction_category_fields: dict[str, int | bool | None],
        correction_reason_category: str | None,
        correction_reason_note: str | None,
        station_context: StationContext | None = None,
    ) -> tuple[ProcessStage, WorkOrderQuantityBatch | None]:
        _ = planned_quantity
        response_stage = ProcessStage.PACKING
        response_batch: WorkOrderQuantityBatch | None = None

        packing_state.status = StageStatus.DONE
        packing_state.updated_at = datetime.now(UTC)
        active_batch.is_active = False
        active_batch.current_stage = ProcessStage.PACKING
        active_batch.current_stage_status = StageStatus.DONE

        if work_order.coating_type == CoatingType.DECORAL and ok_quantity > 0:
            response_batch = WorkOrderQuantityBatch(
                work_order_id=work_order.id,
                quantity=ok_quantity,
                type=QuantityBatchType.MAIN,
                parent_batch_id=active_batch.id,
                is_active=True,
                current_stage=ProcessStage.DECORAL_PRODUCTION,
                current_stage_status=StageStatus.NOT_STARTED,
                is_partial=True,
            )
            self.repository.add_quantity_batch(response_batch)
            response_stage = ProcessStage.DECORAL_PRODUCTION

        self._create_correction_work_order(
            work_order,
            correction_quantity,
            correction_category_fields=correction_category_fields,
            correction_reason_category=correction_reason_category,
            correction_reason_note=correction_reason_note,
            station_context=station_context,
        )

        if work_order.production_type == ProductionType.AUTOMATIC:
            production_state.status = StageStatus.DONE
            production_state.updated_at = datetime.now(UTC)

        self._sync_legacy_current_active_batch(work_order)
        return response_stage, response_batch

    def _create_correction_work_order(
        self,
        parent_work_order: WorkOrder,
        correction_quantity: int,
        *,
        correction_category_fields: dict[str, int | bool | None],
        correction_reason_category: str | None,
        correction_reason_note: str | None,
        station_context: StationContext | None = None,
    ) -> WorkOrder:
        correction_order = WorkOrder(
            paint_id=parent_work_order.paint_id,
            order_number=self.number_allocator.allocate(),
            external_order_number=parent_work_order.external_order_number,
            title=parent_work_order.title,
            total_quantity=correction_quantity,
            completed_quantity=0,
            current_active_batch_id=None,
            parent_order_id=parent_work_order.id,
            is_correction=True,
            correction_reason_category=correction_reason_category,
            correction_reason_note=correction_reason_note,
            description=parent_work_order.description,
            customer_name=parent_work_order.customer_name,
            ral_code=parent_work_order.ral_code,
            paint_code=parent_work_order.paint_code,
            paint_producer=parent_work_order.paint_producer,
            paint_stock_snapshot_quantity_kg=self.paint_service.lookup_current_stock(
                ral_code=parent_work_order.ral_code,
                paint_producer=parent_work_order.paint_producer,
                paint_code=parent_work_order.paint_code,
            ).current_quantity_kg,
            consumed_paint_quantity_kg=0,
            status=WorkOrderStatus.ENTERED,
            coating_type=parent_work_order.coating_type,
            work_order_kind=WorkOrderKind.STANDARD,
            is_ocynk=parent_work_order.is_ocynk,
            production_type=None,
            queue_namespace=QueueNamespace.CORRECTIONS,
            queue_position=None,
            received_date=parent_work_order.received_date,
            planned_pickup_date=parent_work_order.planned_pickup_date,
            total_area_m2=parent_work_order.total_area_m2,
            is_incomplete_on_arrival=False,
            **correction_category_fields,
            notes=parent_work_order.notes,
        )
        persisted_correction_order = self.repository.add_work_order(correction_order)
        self.initialize_quantity_tracking(persisted_correction_order)
        self.initialize_stage_states(persisted_correction_order)
        self._record_audit_event(
            event_type="work_order.correction_created",
            station_context=station_context,
            work_order=persisted_correction_order,
            target_type="work_order",
            target_id=persisted_correction_order.id,
            summary=f"Created correction work order {persisted_correction_order.order_number}.",
            details={
                "parent_work_order_id": parent_work_order.id,
                "parent_order_number": parent_work_order.order_number,
                "correction_quantity": correction_quantity,
                "correction_profiles_quantity": correction_category_fields["profiles_quantity"],
                "correction_accessories_quantity": correction_category_fields["accessories_quantity"],
                "correction_reason_category": correction_reason_category,
                "correction_reason_note": correction_reason_note,
            },
        )
        return persisted_correction_order

    def prepare_correction_work_order_for_planning(self, work_order: WorkOrder) -> None:
        if not work_order.is_correction and not self._is_in_correction_round(work_order):
            return

        return_stage = self.get_correction_return_stage(work_order)
        self._reset_stage_states_for_active_batch(work_order, return_stage)

    @staticmethod
    def _is_in_correction_round(work_order: WorkOrder) -> bool:
        active_batch = work_order.active_batch
        return active_batch is not None and active_batch.parent_batch_id is not None

    def _reset_to_correction_planning(
        self,
        work_order: WorkOrder,
        active_batch: WorkOrderQuantityBatch,
        ok_quantity: int,
        correction_quantity: int,
        correction_reason_category: str | None,
        correction_reason_note: str | None,
        station_context: StationContext | None = None,
    ) -> None:
        work_order.completed_quantity += ok_quantity

        active_batch.is_active = False
        active_batch.current_stage = ProcessStage.PACKING
        active_batch.current_stage_status = StageStatus.DONE

        correction_batch = WorkOrderQuantityBatch(
            work_order_id=work_order.id,
            quantity=correction_quantity,
            type=QuantityBatchType.CORRECTION,
            parent_batch_id=active_batch.id,
            is_active=True,
            current_stage=None,
            current_stage_status=None,
            is_partial=True,
        )
        self.repository.add_quantity_batch(correction_batch)
        work_order.current_active_batch_id = correction_batch.id

        work_order.correction_reason_category = correction_reason_category
        work_order.correction_reason_note = correction_reason_note

        current_timestamp = datetime.now(UTC)
        for stage_state in work_order.stage_states:
            if stage_state.stage == ProcessStage.SURFACE_PREPARATION:
                stage_state.status = StageStatus.DONE
            elif stage_state.stage == ProcessStage.PACKING:
                stage_state.status = StageStatus.NOT_STARTED
                stage_state.counted_quantity = None
            else:
                stage_state.status = StageStatus.NOT_STARTED
            stage_state.updated_at = current_timestamp

        work_order.production_type = None
        work_order.queue_position = None
        work_order.consumed_paint_quantity_kg = 0

        self._record_audit_event(
            event_type="work_order.returned_to_correction_planning",
            station_context=station_context,
            work_order=work_order,
            target_type="work_order",
            target_id=work_order.id,
            summary=f"Returned work order {work_order.order_number} to planning for correction ({correction_quantity} pcs, {ok_quantity} ok so far).",
            details={
                "ok_quantity": ok_quantity,
                "correction_quantity": correction_quantity,
                "accumulated_completed_quantity": work_order.completed_quantity,
                "total_quantity": work_order.total_quantity,
                "correction_reason_category": correction_reason_category,
            },
        )

    def _record_stage_audit_event(
        self,
        *,
        work_order: WorkOrder,
        stage: ProcessStage,
        target_status: StageStatus,
        station_context: StationContext | None,
        batch_id: int | None,
    ) -> None:
        action_by_status = {
            StageStatus.IN_PROGRESS: ("process.stage.started", "Started"),
            StageStatus.DONE: ("process.stage.finished", "Finished"),
            StageStatus.NOT_STARTED: ("process.stage.reopened", "Reopened"),
        }
        event_type, action_label = action_by_status[target_status]
        self._record_audit_event(
            event_type=event_type,
            station_context=station_context,
            work_order=work_order,
            target_type="process_stage",
            target_id=batch_id,
            summary=f"{action_label} {stage.value} for work order {work_order.order_number}.",
            details={
                "stage": stage.value,
                "target_status": target_status.value,
                "batch_id": batch_id,
            },
        )

    def _record_packing_audit_event(
        self,
        *,
        work_order: WorkOrder,
        station_context: StationContext | None,
        batch_id: int | None,
        counted_quantity: int,
        ok_quantity: int,
        correction_quantity: int,
        correction_category_fields: dict[str, int | bool | None],
    ) -> None:
        details = {
            "stage": ProcessStage.PACKING.value,
            "batch_id": batch_id,
            "counted_quantity": counted_quantity,
            "ok_quantity": ok_quantity,
            "correction_quantity": correction_quantity,
        }
        if correction_quantity > 0:
            details.update(
                {
                    "correction_profiles_quantity": correction_category_fields["profiles_quantity"],
                    "correction_accessories_quantity": correction_category_fields["accessories_quantity"],
                }
            )
        self._record_audit_event(
            event_type="process.packing.completed",
            station_context=station_context,
            work_order=work_order,
            target_type="process_stage",
            target_id=batch_id,
            summary=f"Completed packing for work order {work_order.order_number}.",
            details=details,
        )

    def _record_automatic_paint_consumption_audit_event(
        self,
        *,
        work_order: WorkOrder,
        station_context: StationContext | None,
        previous_value: float,
        consumed_paint_quantity_kg: float,
    ) -> None:
        self._record_audit_event(
            event_type="process.automatic_paint_consumption.recorded",
            station_context=station_context,
            work_order=work_order,
            target_type="process_stage",
            target_id=work_order.current_active_batch_id,
            summary=f"Recorded automatic paint consumption for work order {work_order.order_number}.",
            details={
                "stage": ProcessStage.PRODUCTION.value,
                "paint_code": work_order.paint_code,
                "paint_stock_snapshot_quantity_kg": work_order.paint_stock_snapshot_quantity_kg,
                "previous_consumed_paint_quantity_kg": previous_value,
                "consumed_paint_quantity_kg": consumed_paint_quantity_kg,
            },
        )

    def _record_audit_event(
        self,
        *,
        event_type: str,
        station_context: StationContext | None,
        work_order: WorkOrder,
        target_type: str,
        target_id: int | None,
        summary: str,
        details: dict[str, object],
    ) -> None:
        station_id = station_context.station_id if station_context is not None else StationId.SYSTEM
        self.audit_repository.add(
            AuditEvent(
                event_type=event_type,
                station_id=station_id,
                work_order_id=work_order.id,
                target_type=target_type,
                target_id=target_id,
                summary=summary,
                details_json=json.dumps(details, separators=(",", ":")),
            )
        )

    @staticmethod
    def _persisted_category_fields(work_order: WorkOrder) -> dict[str, int | bool | None]:
        return {
            "profiles_quantity": work_order.profiles_quantity,
            "profiles_to_count": work_order.profiles_to_count,
            "accessories_quantity": work_order.accessories_quantity,
            "accessories_to_count": work_order.accessories_to_count,
        }

    @staticmethod
    def _unknown_category_fields(work_order: WorkOrder) -> dict[str, int | bool | None]:
        profiles_known_absent = work_order.profiles_quantity == 0 and not work_order.profiles_to_count
        accessories_known_absent = work_order.accessories_quantity == 0 and not work_order.accessories_to_count
        return {
            "profiles_quantity": 0 if profiles_known_absent else None,
            "profiles_to_count": False if profiles_known_absent else True,
            "accessories_quantity": 0 if accessories_known_absent else None,
            "accessories_to_count": False if accessories_known_absent else True,
        }

    @staticmethod
    def _derive_category_fields_for_operational_quantity(
        work_order: WorkOrder,
        operational_quantity: int,
    ) -> dict[str, int | bool | None]:
        if operational_quantity == work_order.total_quantity:
            return ProcessService._persisted_category_fields(work_order)

        profiles_known = not work_order.profiles_to_count and work_order.profiles_quantity is not None
        accessories_known = not work_order.accessories_to_count and work_order.accessories_quantity is not None
        if profiles_known and accessories_known:
            if work_order.profiles_quantity == 0:
                return {
                    "profiles_quantity": 0,
                    "profiles_to_count": False,
                    "accessories_quantity": operational_quantity,
                    "accessories_to_count": False,
                }
            if work_order.accessories_quantity == 0:
                return {
                    "profiles_quantity": operational_quantity,
                    "profiles_to_count": False,
                    "accessories_quantity": 0,
                    "accessories_to_count": False,
                }

        return ProcessService._unknown_category_fields(work_order)

    @staticmethod
    def _uses_batch_tracking(work_order: WorkOrder) -> bool:
        return any(batch.current_stage is not None for batch in work_order.active_batches)

    @staticmethod
    def _get_batch(work_order: WorkOrder, batch_id: int) -> WorkOrderQuantityBatch:
        for batch in work_order.quantity_batches:
            if batch.id == batch_id:
                return batch
        raise InvalidProcessStageTransitionError(f"Batch {batch_id} is not configured for work order {work_order.id}.")

    @staticmethod
    def _get_ordered_batches(work_order: WorkOrder) -> list[WorkOrderQuantityBatch]:
        return sorted(work_order.quantity_batches, key=lambda batch: (batch.created_at, batch.id))

    @staticmethod
    def _sync_legacy_current_active_batch(work_order: WorkOrder) -> None:
        active_batches = sorted(work_order.active_batches, key=lambda batch: (batch.created_at, batch.id))
        work_order.current_active_batch_id = active_batches[0].id if active_batches else None

    def _commit_process_changes(self) -> None:
        try:
            self.repository.commit()
        except Exception:
            self.repository.rollback()
            raise

    def _finalize_completion_chain_if_ready(self, work_order: WorkOrder) -> WorkOrder | None:
        current_work_order: WorkOrder | None
        if work_order.is_correction and work_order.parent_order_id is not None:
            current_work_order = self.repository.get_work_order_with_stage_states(work_order.parent_order_id)
        else:
            current_work_order = work_order

        finalized_work_order: WorkOrder | None = None
        while current_work_order is not None:
            if not self._can_finalize_work_order(current_work_order):
                break

            current_work_order.completed_quantity = current_work_order.total_quantity
            current_work_order.current_active_batch_id = None
            self._mark_all_stage_states_done(current_work_order)
            finalized_work_order = current_work_order

            if not current_work_order.is_correction or current_work_order.parent_order_id is None:
                break

            current_work_order = self.repository.get_work_order_with_stage_states(current_work_order.parent_order_id)

        if finalized_work_order is None:
            return None

        self._commit_process_changes()
        return finalized_work_order

    def _can_finalize_work_order(self, work_order: WorkOrder) -> bool:
        if self._has_open_corrections(work_order):
            return False

        if work_order.current_active_quantity != 0:
            return False

        if work_order.completed_quantity == work_order.total_quantity:
            return True

        return bool(work_order.correction_orders)

    def _mark_all_stage_states_done(self, work_order: WorkOrder) -> None:
        current_timestamp = datetime.now(UTC)
        for stage_state in work_order.stage_states:
            stage_state.status = StageStatus.DONE
            stage_state.updated_at = current_timestamp

    def _has_open_corrections(self, work_order: WorkOrder) -> bool:
        return any(not self._is_complete_for_display(correction_order) for correction_order in work_order.correction_orders)

    @staticmethod
    def _has_incomplete_marker(work_order: WorkOrder) -> bool:
        return work_order.is_incomplete_on_arrival or work_order.status == WorkOrderStatus.INCOMPLETE

    def _is_complete_for_display(self, work_order: WorkOrder) -> bool:
        return (
            work_order.completed_quantity == work_order.total_quantity
            and work_order.current_active_quantity == 0
            and not any(not self._is_complete_for_display(correction_order) for correction_order in work_order.correction_orders)
        )

    def is_historical_correction(self, work_order: WorkOrder) -> bool:
        return work_order.is_correction and self._is_complete_for_display(work_order)

    def _store_stage_start_data(
        self,
        work_order: WorkOrder,
        stage: ProcessStage,
        counted_quantity: int | None,
    ) -> None:
        if stage != ProcessStage.SURFACE_PREPARATION:
            return

        if counted_quantity is None:
            return

        self._store_surface_preparation_counted_quantity(work_order, counted_quantity)

    def _store_surface_preparation_counted_quantity(
        self,
        work_order: WorkOrder,
        counted_quantity: int | None,
    ) -> None:
        if counted_quantity is None:
            return

        if counted_quantity <= 0:
            raise InvalidProcessStageTransitionError("Counted quantity must be greater than zero.")

        if counted_quantity > work_order.current_active_quantity:
            raise InvalidProcessStageTransitionError("Counted quantity cannot exceed the expected active quantity.")

        stage_state = self._get_stage_state(work_order, ProcessStage.SURFACE_PREPARATION)
        stage_state.counted_quantity = counted_quantity
        stage_state.updated_at = datetime.now(UTC)

    def _ensure_surface_preparation_counted_quantity(self, work_order: WorkOrder) -> None:
        stage_state = self._get_stage_state(work_order, ProcessStage.SURFACE_PREPARATION)
        if stage_state.counted_quantity is None:
            raise InvalidProcessStageTransitionError("Counted quantity is required to finish surface preparation.")

    @staticmethod
    def _get_previous_stage(
        stage_sequence: Sequence[ProcessStage],
        stage: ProcessStage,
    ) -> ProcessStage | None:
        stage_index = stage_sequence.index(stage)
        if stage_index == 0:
            return None
        return stage_sequence[stage_index - 1]

    @staticmethod
    def _get_stage_state(work_order: WorkOrder, stage: ProcessStage) -> WorkOrderStageState:
        for stage_state in work_order.stage_states:
            if stage_state.stage == stage:
                return stage_state
        raise InvalidProcessStageTransitionError(f"Stage {stage.value} is not configured for work order {work_order.id}.")

    def _to_stage_work_order_read(
        self,
        work_order: WorkOrder,
        stage: ProcessStage,
        batch: WorkOrderQuantityBatch | None = None,
    ) -> ProcessStageWorkOrderRead:
        if batch is None and self._is_automatic_production_preview_stage(work_order, stage):
            stage = self._get_automatic_production_preview_display_stage(work_order)
        elif batch is None and stage == ProcessStage.PACKING and work_order.production_type == ProductionType.AUTOMATIC:
            stage = self._get_automatic_packing_display_stage(work_order)

        stage_state = self._get_stage_state(work_order, stage)
        if batch is None:
            current_active_quantity = work_order.current_active_quantity
            batch_quantity = self._get_stage_display_quantity(work_order, stage, stage_state, batch=None)
            batch_type = None
            batch_is_partial = False
            batch_id = None
            planned_quantity = self._get_stage_planned_quantity(work_order, stage, stage_state, batch=None)
            stage_status = self.build_stage_status_view(stage_state.status)
        else:
            batch_status = self._get_tracked_batch_stage_status(work_order, batch, stage)
            if batch_status is None:
                batch_status = batch.current_stage_status or StageStatus.NOT_STARTED
            current_active_quantity = batch.quantity
            batch_quantity = self._get_stage_display_quantity(work_order, stage, stage_state, batch=batch)
            batch_type = batch.type
            batch_is_partial = batch.is_partial
            batch_id = batch.id
            planned_quantity = self._get_stage_planned_quantity(work_order, stage, stage_state, batch=batch)
            stage_status = self.build_stage_status_view(batch_status)

        counted_quantity = self._get_stage_counted_quantity(work_order, stage, batch=batch)
        quantity_difference = counted_quantity - planned_quantity if counted_quantity is not None else None

        category_fields = self._derive_category_fields_for_operational_quantity(
            work_order,
            batch_quantity if batch_quantity is not None else current_active_quantity,
        )
        current_paint_stock_quantity_kg = self.paint_service.lookup_current_stock(
            ral_code=work_order.ral_code,
            paint_producer=work_order.paint_producer,
            paint_code=work_order.paint_code,
        ).current_quantity_kg

        return ProcessStageWorkOrderRead(
            id=work_order.id,
            batch_id=batch_id,
            is_correction=work_order.is_correction,
            completed_quantity=work_order.completed_quantity,
            is_historical_correction=self.is_historical_correction(work_order),
            work_order_kind=build_work_order_kind_view(work_order.work_order_kind),
            is_ocynk=work_order.is_ocynk,
            order_number=work_order.order_number,
            title=work_order.title,
            ral_code=work_order.ral_code,
            paint_code=work_order.paint_code,
            paint_producer=work_order.paint_producer,
            current_paint_stock_quantity_kg=current_paint_stock_quantity_kg,
            paint_stock_snapshot_quantity_kg=work_order.paint_stock_snapshot_quantity_kg,
            consumed_paint_quantity_kg=work_order.consumed_paint_quantity_kg,
            total_area_m2=work_order.total_area_m2,
            total_quantity=work_order.total_quantity,
            current_active_quantity=current_active_quantity,
            batch_quantity=batch_quantity,
            planned_quantity=planned_quantity,
            counted_quantity=counted_quantity,
            quantity_difference=quantity_difference,
            customer_name=work_order.customer_name,
            **category_fields,
            queue_position=work_order.queue_position,
            queue_namespace=build_queue_namespace_view(work_order.queue_namespace),
            production_type=(
                build_production_type_view(work_order.production_type)
                if work_order.production_type is not None
                else None
            ),
            coating_type=build_coating_type_view(work_order.coating_type),
            batch_type=batch_type,
            batch_is_partial=batch_is_partial,
            stage_status=ProcessStageStatusRead(
                stage=stage,
                status=stage_status,
            ),
        )

    @staticmethod
    def _get_stage_display_quantity(
        work_order: WorkOrder,
        stage: ProcessStage,
        stage_state: WorkOrderStageState,
        *,
        batch: WorkOrderQuantityBatch | None,
    ) -> int | None:
        if batch is not None:
            return batch.quantity

        if stage_state.status == StageStatus.DONE:
            return work_order.total_quantity

        return work_order.current_active_quantity

    @staticmethod
    def _get_stage_planned_quantity(
        work_order: WorkOrder,
        stage: ProcessStage,
        stage_state: WorkOrderStageState,
        *,
        batch: WorkOrderQuantityBatch | None,
    ) -> int:
        _ = stage
        _ = stage_state
        if batch is not None:
            return batch.quantity

        active_batch = work_order.active_batch
        if active_batch is not None and active_batch.parent_batch_id is not None:
            return active_batch.quantity

        return work_order.total_quantity

    @staticmethod
    def _get_process_mutation_lock(work_order_id: int) -> RLock:
        with _PROCESS_MUTATION_LOCKS_GUARD:
            lock = _PROCESS_MUTATION_LOCKS.get(work_order_id)
            if lock is None:
                lock = RLock()
                _PROCESS_MUTATION_LOCKS[work_order_id] = lock
            return lock

    @staticmethod
    def _get_resource_mutation_lock(resource_key: str) -> RLock:
        with _RESOURCE_MUTATION_LOCKS_GUARD:
            lock = _RESOURCE_MUTATION_LOCKS.get(resource_key)
            if lock is None:
                lock = RLock()
                _RESOURCE_MUTATION_LOCKS[resource_key] = lock
            return lock

    @staticmethod
    def _get_stage_resource_keys(
        work_order: WorkOrder,
        stage: ProcessStage,
        target_status: StageStatus,
    ) -> tuple[str, ...]:
        if stage != ProcessStage.HANGING:
            return ()

        if target_status == StageStatus.IN_PROGRESS:
            return ("HANGING",)

        if target_status == StageStatus.DONE and work_order.production_type == ProductionType.AUTOMATIC:
            return ("AUTOMATIC_LINE",)

        return ()

    @contextmanager
    def _serialize_stage_resources(self, resource_keys: Sequence[str]):
        with ExitStack() as stack:
            for resource_key in sorted(set(resource_keys)):
                stack.enter_context(self._serialize_resource_mutation(resource_key))
            yield

    @contextmanager
    def _serialize_resource_mutation(self, resource_key: str):
        lock = self._get_resource_mutation_lock(resource_key)
        lock.acquire()
        try:
            yield
        finally:
            lock.release()

    def _ensure_stage_resources_available(
        self,
        work_order: WorkOrder,
        stage: ProcessStage,
        target_status: StageStatus,
    ) -> None:
        if stage != ProcessStage.HANGING:
            return

        if target_status == StageStatus.DONE and work_order.production_type == ProductionType.AUTOMATIC:
            automatic_line_conflict = self._find_active_automatic_line_conflict(work_order.id)
            if automatic_line_conflict is not None:
                raise InvalidProcessStageTransitionError("Automatic line is already occupied by another active job.")
            return

        if target_status != StageStatus.IN_PROGRESS:
            return

        hanging_conflict = self._find_active_hanging_conflict(work_order.id)
        if hanging_conflict is not None:
            raise InvalidProcessStageTransitionError("Hanging resource is already occupied by another active job.")

    def _acquire_stage_resource_locks(self, work_order: WorkOrder, stage: ProcessStage, target_status: StageStatus) -> None:
        resource_keys = self._get_stage_resource_keys(work_order, stage, target_status)
        for resource_key in resource_keys:
            self._acquire_resource_lock_with_stale_recovery(resource_key, work_order)

    def _acquire_resource_lock_with_stale_recovery(self, resource_key: str, work_order: WorkOrder) -> None:
        try:
            self.repository.acquire_resource_lock(resource_key, work_order.id)
            return
        except ValueError:
            if not self._release_stale_resource_lock(resource_key):
                raise self._build_resource_conflict_error(resource_key)
        except IntegrityError:
            self.repository.rollback()
            if not self._release_stale_resource_lock(resource_key):
                raise self._build_resource_conflict_error(resource_key)

        try:
            self.repository.acquire_resource_lock(resource_key, work_order.id)
        except ValueError as exc:
            raise self._build_resource_conflict_error(resource_key) from exc
        except IntegrityError as exc:
            self.repository.rollback()
            raise self._build_resource_conflict_error(resource_key) from exc

    def _release_stale_resource_lock(self, resource_key: str) -> bool:
        existing_lock = self.repository.get_resource_lock(resource_key)
        if existing_lock is None:
            return False

        lock_owner = self.repository.get_work_order_with_stage_states(existing_lock.work_order_id)
        if lock_owner is None:
            self.repository.release_resource_lock(resource_key, existing_lock.work_order_id)
            return True

        if resource_key == "HANGING" and not self._has_active_hanging_work(lock_owner):
            self.repository.release_resource_lock(resource_key, existing_lock.work_order_id)
            return True

        if resource_key == "AUTOMATIC_LINE" and not self._occupies_automatic_line(lock_owner):
            self.repository.release_resource_lock(resource_key, existing_lock.work_order_id)
            return True

        return False

    def _release_inactive_resource_locks(self, work_order: WorkOrder) -> None:
        for resource_lock in self.repository.list_resource_locks_for_work_order(work_order.id):
            if resource_lock.resource_key == "HANGING" and not self._has_active_hanging_work(work_order):
                self.repository.release_resource_lock(resource_lock.resource_key, work_order.id)
            elif resource_lock.resource_key == "AUTOMATIC_LINE" and not self._occupies_automatic_line(work_order):
                self.repository.release_resource_lock(resource_lock.resource_key, work_order.id)

    @staticmethod
    def _build_resource_conflict_error(resource_key: str) -> InvalidProcessStageTransitionError:
        if resource_key == "AUTOMATIC_LINE":
            return InvalidProcessStageTransitionError("Automatic line is already occupied by another active job.")
        return InvalidProcessStageTransitionError("Hanging resource is already occupied by another active job.")

    def _find_active_hanging_conflict(self, work_order_id: int) -> WorkOrder | None:
        for candidate in self.repository.list_work_orders_with_stage(ProcessStage.HANGING):
            if candidate.id == work_order_id:
                continue
            if self._has_active_hanging_work(candidate):
                return candidate
        return None

    def _find_active_automatic_line_conflict(self, work_order_id: int) -> WorkOrder | None:
        for candidate in self.repository.list_work_orders_with_stage(ProcessStage.HANGING):
            if candidate.id == work_order_id:
                continue
            if self._occupies_automatic_line(candidate):
                return candidate
        return None

    def _has_active_hanging_work(self, work_order: WorkOrder) -> bool:
        hanging_state = self._get_stage_state(work_order, ProcessStage.HANGING)
        if hanging_state.status == StageStatus.IN_PROGRESS:
            return True

        return any(
            batch.is_active
            and batch.current_stage == ProcessStage.HANGING
            and batch.current_stage_status == StageStatus.IN_PROGRESS
            for batch in work_order.quantity_batches
        )

    def _occupies_automatic_line(self, work_order: WorkOrder) -> bool:
        if work_order.production_type != ProductionType.AUTOMATIC:
            return False

        hanging_state = self._get_stage_state(work_order, ProcessStage.HANGING)
        production_state = self._get_stage_state(work_order, ProcessStage.PRODUCTION)
        packing_state = self._get_stage_state(work_order, ProcessStage.PACKING)
        if hanging_state.status == StageStatus.DONE and production_state.status == StageStatus.IN_PROGRESS and packing_state.status != StageStatus.DONE:
            return True

        return any(
            batch.is_active
            and batch.current_stage == ProcessStage.PACKING
            and batch.current_stage_status == StageStatus.IN_PROGRESS
            for batch in work_order.quantity_batches
        )

    def _get_surface_preparation_actual_quantity(self, work_order: WorkOrder) -> int | None:
        if self._skips_surface_preparation(work_order):
            return None

        surface_preparation_state = self._get_stage_state(work_order, ProcessStage.SURFACE_PREPARATION)
        return surface_preparation_state.counted_quantity

    def _get_stage_counted_quantity(
        self,
        work_order: WorkOrder,
        stage: ProcessStage,
        *,
        batch: WorkOrderQuantityBatch | None,
    ) -> int | None:
        stage_state = self._get_stage_state(work_order, stage)
        if stage == ProcessStage.SURFACE_PREPARATION:
            return stage_state.counted_quantity

        if stage != ProcessStage.PACKING:
            return None

        if stage_state.counted_quantity is not None:
            return stage_state.counted_quantity

        if batch is None:
            if self._is_in_correction_round(work_order):
                return None
            return self._get_surface_preparation_actual_quantity(work_order)

        return None

    @contextmanager
    def _serialize_process_mutation(self, work_order_id: int):
        lock = self._get_process_mutation_lock(work_order_id)
        lock.acquire()
        try:
            yield
        finally:
            lock.release()

    def _to_idempotent_packing_response(self, work_order: WorkOrder) -> ProcessStageWorkOrderRead:
        return_stage = ProcessStage.DECORAL_PRODUCTION if work_order.coating_type == CoatingType.DECORAL else ProcessStage.PACKING
        return self._to_stage_work_order_read(work_order, return_stage)

    def _has_tracked_batch_already_finished_stage(
        self,
        work_order: WorkOrder,
        batch: WorkOrderQuantityBatch,
        stage: ProcessStage,
    ) -> bool:
        if batch.current_stage == stage and batch.current_stage_status == StageStatus.DONE:
            return True

        if batch.current_stage is None:
            return False

        stage_sequence = self.get_actionable_stage_sequence_for_work_order(work_order)
        if stage not in stage_sequence or batch.current_stage not in stage_sequence:
            return False

        return stage_sequence.index(batch.current_stage) > stage_sequence.index(stage)
