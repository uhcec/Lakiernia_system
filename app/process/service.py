from collections.abc import Sequence
from datetime import UTC, datetime

from app.process.enums import CoatingType, ProcessDisplayStatus, ProcessStage, ProductionType, QuantityBatchType, StageStatus
from app.process.models import WorkOrderQuantityBatch, WorkOrderStageState
from app.process.repository import ProcessRepository
from app.process.schemas import ProcessStageStatusRead, ProcessStageWorkOrderRead, StageStatusView
from app.shared.exceptions import InvalidProcessStageTransitionError, ResourceNotFoundError
from app.work_orders.models import WorkOrder
from app.work_orders.schemas import build_coating_type_view, build_production_type_view


class ProcessService:
    DEFAULT_CORRECTION_RETURN_STAGE = ProcessStage.PRODUCTION

    def __init__(self, repository: ProcessRepository) -> None:
        self.repository = repository

    @staticmethod
    def get_stage_sequence(coating_type: CoatingType) -> list[ProcessStage]:
        stages = [
            ProcessStage.SURFACE_PREPARATION,
            ProcessStage.HANGING,
            ProcessStage.PRODUCTION,
        ]
        if coating_type == CoatingType.DECORAL:
            stages.append(ProcessStage.DECORAL_PRODUCTION)
        stages.append(ProcessStage.PACKING)
        return stages

    def initialize_stage_states(self, work_order: WorkOrder) -> None:
        stage_states = [
            WorkOrderStageState(
                work_order_id=work_order.id,
                stage=stage,
                status=StageStatus.NOT_STARTED,
            )
            for stage in self.get_stage_sequence(work_order.coating_type)
        ]
        self.repository.add_stage_states(stage_states)

    def initialize_quantity_tracking(self, work_order: WorkOrder) -> None:
        main_batch = WorkOrderQuantityBatch(
            work_order_id=work_order.id,
            quantity=work_order.total_quantity,
            type=QuantityBatchType.MAIN,
            parent_batch_id=None,
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
        work_orders = self.list_visible_work_orders(stage, production_type, include_done=True)
        return [self._to_stage_work_order_read(work_order, stage) for work_order in work_orders]

    def start_stage(self, work_order_id: int, stage: ProcessStage) -> ProcessStageWorkOrderRead:
        self.transition_stage(work_order_id, stage, StageStatus.IN_PROGRESS)
        work_order = self.get_work_order_process(work_order_id)
        return self._to_stage_work_order_read(work_order, stage)

    def finish_stage(self, work_order_id: int, stage: ProcessStage) -> ProcessStageWorkOrderRead:
        if stage == ProcessStage.PACKING:
            work_order = self.get_work_order_process(work_order_id)
            return self.complete_packing(
                work_order_id,
                ok_quantity=work_order.current_active_quantity,
                correction_quantity=0,
            )

        self.transition_stage(work_order_id, stage, StageStatus.DONE)
        work_order = self.get_work_order_process(work_order_id)
        return self._to_stage_work_order_read(work_order, stage)

    def reopen_stage(self, work_order_id: int, stage: ProcessStage) -> ProcessStageWorkOrderRead:
        work_order = self.get_work_order_process(work_order_id)
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
        ok_quantity: int,
        correction_quantity: int,
    ) -> ProcessStageWorkOrderRead:
        work_order = self.get_work_order_process(work_order_id)
        packing_state = self._get_stage_state(work_order, ProcessStage.PACKING)

        if packing_state.status != StageStatus.IN_PROGRESS:
            raise InvalidProcessStageTransitionError("Packing can be completed only from IN_PROGRESS state.")

        active_batch = work_order.active_batch
        if active_batch is None:
            raise InvalidProcessStageTransitionError("No active quantity batch available for packing.")

        active_quantity = active_batch.quantity
        if ok_quantity + correction_quantity != active_quantity:
            raise InvalidProcessStageTransitionError(
                "Packing quantities must add up to the current active quantity."
            )

        if ok_quantity < 0 or correction_quantity < 0:
            raise InvalidProcessStageTransitionError("Packing quantities cannot be negative.")

        work_order.completed_quantity += ok_quantity

        if correction_quantity > 0:
            correction_batch = WorkOrderQuantityBatch(
                work_order_id=work_order.id,
                quantity=correction_quantity,
                type=QuantityBatchType.CORRECTION,
                parent_batch_id=active_batch.id,
            )
            self.repository.add_quantity_batch(correction_batch)
            work_order.current_active_batch_id = correction_batch.id
            self._reset_stage_states_for_active_batch(work_order, self.get_correction_return_stage(work_order))
        else:
            packing_state.status = StageStatus.DONE
            packing_state.updated_at = datetime.now(UTC)
            work_order.current_active_batch_id = None

        try:
            self.repository.commit()
        except Exception:
            self.repository.rollback()
            raise

        refreshed_work_order = self.get_work_order_process(work_order_id)
        return_stage = self.get_correction_return_stage(refreshed_work_order) if correction_quantity > 0 else ProcessStage.PACKING
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
        if not self._is_planned(work_order):
            return False

        stage_sequence = self.get_stage_sequence(work_order.coating_type)
        if stage not in stage_sequence:
            return False

        stage_state = self._get_stage_state(work_order, stage)
        allowed_statuses = {StageStatus.NOT_STARTED, StageStatus.IN_PROGRESS}
        if include_done:
            allowed_statuses.add(StageStatus.DONE)

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
        if not self._is_planned(work_order):
            return ProcessDisplayStatus.TO_BE_PLANNED

        stage_sequence = self.get_stage_sequence(work_order.coating_type)
        for stage in stage_sequence:
            stage_state = self._get_stage_state(work_order, stage)
            if stage_state.status != StageStatus.DONE:
                return self._get_display_status_for_stage(work_order, stage)

        return ProcessDisplayStatus.READY

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

    def _validate_transition(
        self,
        work_order: WorkOrder,
        stage_state: WorkOrderStageState,
        target_status: StageStatus,
    ) -> None:
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
            stage_sequence = self.get_stage_sequence(work_order.coating_type)
            previous_stage = self._get_previous_stage(stage_sequence, stage_state.stage)
            if previous_stage is not None:
                previous_state = self._get_stage_state(work_order, previous_stage)
                if previous_state.status != StageStatus.DONE:
                    raise InvalidProcessStageTransitionError(
                        f"Stage {stage_state.stage.value} requires {previous_stage.value} to be DONE first."
                    )

    def get_correction_return_stage(self, work_order: WorkOrder) -> ProcessStage:
        stage_sequence = self.get_stage_sequence(work_order.coating_type)
        if self.DEFAULT_CORRECTION_RETURN_STAGE in stage_sequence:
            return self.DEFAULT_CORRECTION_RETURN_STAGE
        return stage_sequence[0]

    def _reset_stage_states_for_active_batch(self, work_order: WorkOrder, return_stage: ProcessStage) -> None:
        stage_sequence = self.get_stage_sequence(work_order.coating_type)
        return_stage_index = stage_sequence.index(return_stage)
        current_timestamp = datetime.now(UTC)

        for index, stage in enumerate(stage_sequence):
            stage_state = self._get_stage_state(work_order, stage)
            stage_state.status = StageStatus.DONE if index < return_stage_index else StageStatus.NOT_STARTED
            stage_state.updated_at = current_timestamp

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

    def _to_stage_work_order_read(self, work_order: WorkOrder, stage: ProcessStage) -> ProcessStageWorkOrderRead:
        stage_state = self._get_stage_state(work_order, stage)
        return ProcessStageWorkOrderRead(
            id=work_order.id,
            order_number=work_order.order_number,
            title=work_order.title,
            total_quantity=work_order.total_quantity,
            current_active_quantity=work_order.current_active_quantity,
            customer_name=work_order.customer_name,
            queue_position=work_order.queue_position,
            production_type=(
                build_production_type_view(work_order.production_type)
                if work_order.production_type is not None
                else None
            ),
            coating_type=build_coating_type_view(work_order.coating_type),
            stage_status=ProcessStageStatusRead(
                stage=stage_state.stage,
                status=self.build_stage_status_view(stage_state.status),
            ),
        )
