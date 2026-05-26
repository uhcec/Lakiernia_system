from collections.abc import Sequence
from datetime import UTC, datetime

from app.process.enums import CoatingType, ProcessDisplayStatus, ProcessStage, ProductionType, QuantityBatchType, StageStatus
from app.process.models import WorkOrderQuantityBatch, WorkOrderStageState
from app.process.repository import ProcessRepository
from app.process.schemas import ProcessStageStatusRead, ProcessStageWorkOrderRead, StageStatusView
from app.shared.enums import WorkOrderStatus
from app.shared.exceptions import InvalidProcessStageTransitionError, ResourceNotFoundError
from app.work_orders.models import WorkOrder
from app.work_orders.schemas import build_coating_type_view, build_production_type_view


class ProcessService:
    DEFAULT_CORRECTION_RETURN_STAGE = ProcessStage.PRODUCTION

    def __init__(self, repository: ProcessRepository) -> None:
        self.repository = repository

    @staticmethod
    def get_stage_sequence_for_configuration(
        coating_type: CoatingType,
        production_type: ProductionType | None,
    ) -> list[ProcessStage]:
        stages = [ProcessStage.SURFACE_PREPARATION]
        if production_type != ProductionType.MANUAL:
            stages.append(ProcessStage.HANGING)
        stages.append(ProcessStage.PRODUCTION)
        stages.append(ProcessStage.PACKING)
        if coating_type == CoatingType.DECORAL:
            stages.append(ProcessStage.DECORAL_PRODUCTION)
        return stages

    def get_stage_sequence_for_work_order(self, work_order: WorkOrder) -> list[ProcessStage]:
        return self.get_stage_sequence_for_configuration(work_order.coating_type, work_order.production_type)

    @staticmethod
    def get_configured_stage_states_sequence(coating_type: CoatingType) -> list[ProcessStage]:
        stages = [
            ProcessStage.SURFACE_PREPARATION,
            ProcessStage.HANGING,
            ProcessStage.PRODUCTION,
            ProcessStage.PACKING,
        ]
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
            for stage in self.get_configured_stage_states_sequence(work_order.coating_type)
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
    ) -> WorkOrderStageState:
        work_order = self.get_work_order_process(work_order_id)
        stage_state = self._get_stage_state(work_order, stage)
        self._validate_transition(work_order, stage_state, target_status)
        stage_state.status = target_status
        stage_state.updated_at = datetime.now(UTC)

        if (
            stage == ProcessStage.HANGING
            and target_status == StageStatus.IN_PROGRESS
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
    ) -> list[ProcessStageWorkOrderRead]:
        work_orders = self.repository.list_work_orders_with_stage(stage, production_type)
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
    ) -> ProcessStageWorkOrderRead:
        work_order = self.get_work_order_process(work_order_id)
        target_batch = self._resolve_batch_for_stage(work_order, stage, batch_id)
        if target_batch is not None:
            return self._start_tracked_batch_stage(work_order, target_batch, stage, counted_quantity=counted_quantity)

        if self._is_automatic_production_preview_stage(work_order, stage):
            raise InvalidProcessStageTransitionError(
                "Automatic production is preview-only. Start the process from HANGING and finish it from PACKING."
            )

        self._store_stage_start_data(work_order, stage, counted_quantity)

        self.transition_stage(work_order_id, stage, StageStatus.IN_PROGRESS)
        work_order = self.get_work_order_process(work_order_id)

        if stage == ProcessStage.HANGING and work_order.production_type == ProductionType.AUTOMATIC:
            production_state = self._get_stage_state(work_order, ProcessStage.PRODUCTION)
            if production_state.status == StageStatus.NOT_STARTED:
                production_state.status = StageStatus.IN_PROGRESS
                production_state.updated_at = datetime.now(UTC)
                try:
                    self.repository.commit()
                except Exception:
                    self.repository.rollback()
                    raise
                work_order = self.get_work_order_process(work_order_id)

        return self._to_stage_work_order_read(work_order, stage)

    def finish_stage(self, work_order_id: int, stage: ProcessStage, batch_id: int | None = None) -> ProcessStageWorkOrderRead:
        work_order = self.get_work_order_process(work_order_id)
        target_batch = self._resolve_batch_for_stage(work_order, stage, batch_id)
        if target_batch is not None:
            return self._finish_tracked_batch_stage(work_order, target_batch, stage)

        if self._is_automatic_production_preview_stage(work_order, stage):
            raise InvalidProcessStageTransitionError(
                "Automatic production is preview-only. Start the process from HANGING and finish it from PACKING."
            )

        if stage == ProcessStage.PACKING:
            return self.complete_packing(
                work_order_id,
                counted_quantity=work_order.current_active_quantity,
                ok_quantity=work_order.current_active_quantity,
                correction_quantity=0,
            )

        self.transition_stage(work_order_id, stage, StageStatus.DONE)
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

                merged_parent = self._merge_completed_correction_into_parent_if_ready(work_order)
                if merged_parent is not None:
                    work_order = self.get_work_order_process(work_order_id)

        return self._to_stage_work_order_read(work_order, stage)

    def reopen_stage(self, work_order_id: int, stage: ProcessStage) -> ProcessStageWorkOrderRead:
        work_order = self.get_work_order_process(work_order_id)
        target_batch = self._resolve_batch_for_stage(work_order, stage, None)
        if target_batch is not None:
            return self._reopen_tracked_batch_stage(work_order, target_batch, stage)

        if self._is_automatic_production_preview_stage(work_order, stage):
            raise InvalidProcessStageTransitionError(
                "Automatic production is preview-only. Start the process from HANGING and finish it from PACKING."
            )

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

        self.transition_stage(work_order_id, stage, target_status)
        work_order = self.get_work_order_process(work_order_id)
        return self._to_stage_work_order_read(work_order, stage)

    def complete_packing(
        self,
        work_order_id: int,
        *,
        counted_quantity: int,
        ok_quantity: int,
        correction_quantity: int,
        batch_id: int | None = None,
    ) -> ProcessStageWorkOrderRead:
        work_order = self.get_work_order_process(work_order_id)
        target_batch = self._resolve_batch_for_stage(work_order, ProcessStage.PACKING, batch_id)
        if target_batch is not None:
            return self._complete_tracked_batch_packing(
                work_order,
                target_batch,
                counted_quantity=counted_quantity,
                ok_quantity=ok_quantity,
                correction_quantity=correction_quantity,
            )

        packing_state = self._get_stage_state(work_order, ProcessStage.PACKING)
        hanging_state = self._get_stage_state(work_order, ProcessStage.HANGING)

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
        if counted_quantity != planned_quantity:
            raise InvalidProcessStageTransitionError(
                "Policzona ilość różni się od planowanej. Wyjaśnij brakujące sztuki."
            )

        packing_state.counted_quantity = counted_quantity
        packing_state.updated_at = datetime.now(UTC)

        production_state = self._get_stage_state(work_order, ProcessStage.PRODUCTION)
        if work_order.production_type == ProductionType.AUTOMATIC and hanging_state.status == StageStatus.IN_PROGRESS:
            hanging_state.status = StageStatus.DONE
            hanging_state.updated_at = datetime.now(UTC)

        if correction_quantity > 0:
            response_stage, response_batch = self._complete_packing_with_correction_order(
                work_order,
                active_batch,
                packing_state,
                production_state,
                planned_quantity=planned_quantity,
                ok_quantity=ok_quantity,
                correction_quantity=correction_quantity,
            )
            self._commit_process_changes()
            refreshed_work_order = self.get_work_order_process(work_order_id)
            if response_batch is not None:
                refreshed_batch = self._get_batch(refreshed_work_order, response_batch.id)
                return self._to_stage_work_order_read(refreshed_work_order, response_stage, batch=refreshed_batch)
            return self._to_stage_work_order_read(refreshed_work_order, response_stage)
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

        try:
            self.repository.commit()
        except Exception:
            self.repository.rollback()
            raise

        refreshed_work_order = self.get_work_order_process(work_order_id)
        merged_parent = self._merge_completed_correction_into_parent_if_ready(refreshed_work_order)
        if merged_parent is not None:
            refreshed_work_order = self.get_work_order_process(work_order_id)
        if refreshed_work_order.coating_type == CoatingType.DECORAL:
            return_stage = ProcessStage.DECORAL_PRODUCTION
        else:
            return_stage = ProcessStage.PACKING
        return self._to_stage_work_order_read(refreshed_work_order, return_stage)

    def list_visible_work_orders(
        self,
        stage: ProcessStage,
        production_type: ProductionType | None = None,
        include_done: bool = False,
    ) -> list[WorkOrder]:
        work_orders = self.repository.list_work_orders_with_stage(stage, production_type)
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

        if self._has_open_corrections(work_order):
            return ProcessDisplayStatus.WAITING_FOR_CORRECTIONS

        if self._is_complete_for_display(work_order):
            return ProcessDisplayStatus.READY

        if not self._is_planned(work_order):
            return ProcessDisplayStatus.TO_BE_PLANNED

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
            raise InvalidProcessStageTransitionError(
                "Automatic production is preview-only. Start the process from HANGING and finish it from PACKING."
            )

        if (
            work_order.production_type == ProductionType.AUTOMATIC
            and stage_state.stage == ProcessStage.HANGING
            and target_status == StageStatus.DONE
        ):
            raise InvalidProcessStageTransitionError(
                "Automatic hanging can only start painting. Finish it from PACKING."
            )

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

        if hanging_state.status == StageStatus.NOT_STARTED:
            return False

        if packing_state.status == StageStatus.DONE:
            return False

        return production_state.status == StageStatus.IN_PROGRESS

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
        return hanging_state.status == StageStatus.IN_PROGRESS

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
            if batch.current_stage == ProcessStage.HANGING and batch.current_stage_status == StageStatus.IN_PROGRESS:
                return StageStatus.IN_PROGRESS

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
    ) -> ProcessStageWorkOrderRead:
        if stage == ProcessStage.PRODUCTION and work_order.production_type == ProductionType.AUTOMATIC:
            raise InvalidProcessStageTransitionError(
                "Automatic production is preview-only. Start the process from HANGING and finish it from PACKING."
            )
        if batch.current_stage != stage or batch.current_stage_status != StageStatus.NOT_STARTED:
            raise InvalidProcessStageTransitionError(
                f"Cannot transition stage {stage.value} from {batch.current_stage_status.value if batch.current_stage_status else 'UNKNOWN'} to IN_PROGRESS."
            )

        self._store_stage_start_data(work_order, stage, counted_quantity)
        batch.current_stage_status = StageStatus.IN_PROGRESS
        self._sync_legacy_current_active_batch(work_order)
        self._commit_process_changes()
        refreshed_work_order = self.get_work_order_process(work_order.id)
        refreshed_batch = self._get_batch(refreshed_work_order, batch.id)
        return self._to_stage_work_order_read(refreshed_work_order, stage, batch=refreshed_batch)

    def _finish_tracked_batch_stage(
        self,
        work_order: WorkOrder,
        batch: WorkOrderQuantityBatch,
        stage: ProcessStage,
    ) -> ProcessStageWorkOrderRead:
        if stage == ProcessStage.PACKING:
            return self.complete_packing(work_order.id, ok_quantity=batch.quantity, correction_quantity=0, batch_id=batch.id)
        if stage == ProcessStage.HANGING and work_order.production_type == ProductionType.AUTOMATIC:
            raise InvalidProcessStageTransitionError(
                "Automatic hanging can only start painting. Finish it from PACKING."
            )
        if stage == ProcessStage.PRODUCTION and work_order.production_type == ProductionType.AUTOMATIC:
            raise InvalidProcessStageTransitionError(
                "Automatic production is preview-only. Start the process from HANGING and finish it from PACKING."
            )
        if batch.current_stage != stage or batch.current_stage_status != StageStatus.IN_PROGRESS:
            raise InvalidProcessStageTransitionError(
                f"Cannot transition stage {stage.value} from {batch.current_stage_status.value if batch.current_stage_status else 'UNKNOWN'} to DONE."
            )

        response_stage = stage
        if stage == ProcessStage.SURFACE_PREPARATION:
            batch.current_stage = ProcessStage.HANGING if work_order.production_type == ProductionType.AUTOMATIC else ProcessStage.PRODUCTION
            batch.current_stage_status = StageStatus.NOT_STARTED
            response_stage = batch.current_stage
        elif stage == ProcessStage.HANGING:
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
            self._commit_process_changes()
            refreshed_work_order = self.get_work_order_process(work_order.id)
            refreshed_batch = self._get_batch(refreshed_work_order, batch.id)
            return self._to_stage_work_order_read(refreshed_work_order, stage, batch=refreshed_batch)

        self._sync_legacy_current_active_batch(work_order)
        self._commit_process_changes()
        refreshed_work_order = self.get_work_order_process(work_order.id)
        refreshed_batch = self._get_batch(refreshed_work_order, batch.id)
        return self._to_stage_work_order_read(refreshed_work_order, response_stage, batch=refreshed_batch)

    def _reopen_tracked_batch_stage(
        self,
        work_order: WorkOrder,
        batch: WorkOrderQuantityBatch,
        stage: ProcessStage,
    ) -> ProcessStageWorkOrderRead:
        if batch.current_stage != stage or batch.current_stage_status not in {StageStatus.IN_PROGRESS, StageStatus.DONE}:
            raise InvalidProcessStageTransitionError(
                f"Cannot reopen stage {stage.value} from {batch.current_stage_status.value if batch.current_stage_status else 'UNKNOWN'}."
            )

        batch.current_stage_status = StageStatus.IN_PROGRESS if batch.current_stage_status == StageStatus.DONE else StageStatus.NOT_STARTED
        batch.is_active = True
        self._sync_legacy_current_active_batch(work_order)
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
    ) -> ProcessStageWorkOrderRead:
        is_automatic_hanging_in_progress = (
            work_order.production_type == ProductionType.AUTOMATIC
            and batch.current_stage == ProcessStage.HANGING
            and batch.current_stage_status == StageStatus.IN_PROGRESS
        )
        if (
            not is_automatic_hanging_in_progress
            and (batch.current_stage != ProcessStage.PACKING or batch.current_stage_status != StageStatus.IN_PROGRESS)
        ):
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
        if correction_quantity > 0:
            self._create_correction_work_order(work_order, correction_quantity)
        elif work_order.coating_type == CoatingType.DECORAL and ok_quantity > 0:
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
        elif ok_quantity > 0:
            work_order.completed_quantity += ok_quantity

        self._sync_legacy_current_active_batch(work_order)
        self._commit_process_changes()

        refreshed_work_order = self.get_work_order_process(work_order.id)
        merged_parent = self._merge_completed_correction_into_parent_if_ready(refreshed_work_order)
        if merged_parent is not None:
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
    ) -> tuple[ProcessStage, WorkOrderQuantityBatch | None]:
        _ = planned_quantity
        _ = ok_quantity
        self._create_correction_work_order(work_order, correction_quantity)

        packing_state.status = StageStatus.DONE
        packing_state.updated_at = datetime.now(UTC)
        active_batch.is_active = False
        active_batch.current_stage = ProcessStage.PACKING
        active_batch.current_stage_status = StageStatus.DONE

        if work_order.production_type == ProductionType.AUTOMATIC:
            production_state.status = StageStatus.DONE
            production_state.updated_at = datetime.now(UTC)

        work_order.current_active_batch_id = None
        return ProcessStage.PACKING, None

    def _create_correction_work_order(self, parent_work_order: WorkOrder, correction_quantity: int) -> WorkOrder:
        correction_order = WorkOrder(
            order_number=self._generate_work_order_number(),
            title=parent_work_order.title,
            total_quantity=correction_quantity,
            completed_quantity=0,
            current_active_batch_id=None,
            parent_order_id=parent_work_order.id,
            is_correction=True,
            description=parent_work_order.description,
            customer_name=parent_work_order.customer_name,
            ral_code=parent_work_order.ral_code,
            paint_producer=parent_work_order.paint_producer,
            status=WorkOrderStatus.ENTERED,
            coating_type=parent_work_order.coating_type,
            production_type=None,
            queue_position=None,
            received_date=parent_work_order.received_date,
            planned_pickup_date=parent_work_order.planned_pickup_date,
            total_area_m2=parent_work_order.total_area_m2,
            is_incomplete_on_arrival=False,
            profiles_quantity=parent_work_order.profiles_quantity,
            profiles_to_count=parent_work_order.profiles_to_count,
            accessories_quantity=parent_work_order.accessories_quantity,
            accessories_to_count=parent_work_order.accessories_to_count,
            notes=parent_work_order.notes,
        )
        persisted_correction_order = self.repository.add_work_order(correction_order)
        self.initialize_quantity_tracking(persisted_correction_order)
        self.initialize_stage_states(persisted_correction_order)
        return persisted_correction_order

    def _generate_work_order_number(self) -> str:
        year = datetime.now(UTC).year
        latest_order_number = self.repository.get_latest_order_number_for_year(year)
        next_sequence = 1 if latest_order_number is None else int(latest_order_number.rsplit("-", 1)[-1]) + 1
        return f"WO-{year}-{next_sequence:04d}"

    @staticmethod
    def _uses_batch_tracking(work_order: WorkOrder) -> bool:
        return any(batch.current_stage is not None for batch in work_order.quantity_batches)

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

    def _merge_completed_correction_into_parent_if_ready(self, work_order: WorkOrder) -> WorkOrder | None:
        if not work_order.is_correction or work_order.parent_order_id is None:
            return None

        if not self._is_complete_for_display(work_order):
            return None

        merged_parent: WorkOrder | None = None
        parent_order_id = work_order.parent_order_id
        while parent_order_id is not None:
            parent_work_order = self.repository.get_work_order_with_stage_states(parent_order_id)
            if parent_work_order is None or self._has_open_corrections(parent_work_order):
                break

            parent_work_order.completed_quantity = parent_work_order.total_quantity
            parent_work_order.current_active_batch_id = None
            self._mark_all_stage_states_done(parent_work_order)
            merged_parent = parent_work_order
            parent_order_id = parent_work_order.parent_order_id if parent_work_order.is_correction else None

        if merged_parent is None:
            return None

        self._commit_process_changes()
        return merged_parent

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

    def _store_stage_start_data(
        self,
        work_order: WorkOrder,
        stage: ProcessStage,
        counted_quantity: int | None,
    ) -> None:
        if stage != ProcessStage.SURFACE_PREPARATION:
            return

        if counted_quantity is None:
            raise InvalidProcessStageTransitionError("Counted quantity is required to start surface preparation.")

        if counted_quantity <= 0:
            raise InvalidProcessStageTransitionError("Counted quantity must be greater than zero.")

        stage_state = self._get_stage_state(work_order, stage)
        stage_state.counted_quantity = counted_quantity
        stage_state.updated_at = datetime.now(UTC)

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
        stage_state = self._get_stage_state(work_order, stage)
        if batch is None:
            batch_quantity = work_order.current_active_quantity
            batch_type = None
            batch_is_partial = False
            batch_id = None
            stage_status = self.build_stage_status_view(stage_state.status)
        else:
            batch_status = self._get_tracked_batch_stage_status(work_order, batch, stage)
            if batch_status is None:
                batch_status = batch.current_stage_status or StageStatus.NOT_STARTED
            batch_quantity = batch.quantity
            batch_type = batch.type
            batch_is_partial = batch.is_partial
            batch_id = batch.id
            stage_status = self.build_stage_status_view(batch_status)

        counted_quantity = stage_state.counted_quantity if stage in {ProcessStage.SURFACE_PREPARATION, ProcessStage.PACKING} else None
        quantity_difference = counted_quantity - batch_quantity if counted_quantity is not None else None

        return ProcessStageWorkOrderRead(
            id=work_order.id,
            batch_id=batch_id,
            order_number=work_order.order_number,
            title=work_order.title,
            ral_code=work_order.ral_code,
            total_area_m2=work_order.total_area_m2,
            total_quantity=work_order.total_quantity,
            current_active_quantity=batch_quantity,
            batch_quantity=batch_quantity,
            planned_quantity=batch_quantity,
            counted_quantity=counted_quantity,
            quantity_difference=quantity_difference,
            customer_name=work_order.customer_name,
            queue_position=work_order.queue_position,
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
