from collections.abc import Sequence
from datetime import UTC, datetime

from app.process.enums import CoatingType, ProcessStage, ProductionType, StageStatus
from app.process.models import WorkOrderStageState
from app.process.repository import ProcessRepository
from app.shared.exceptions import InvalidProcessStageTransitionError, ResourceNotFoundError
from app.work_orders.models import WorkOrder


class ProcessService:
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

    def list_visible_work_orders(
        self,
        stage: ProcessStage,
        production_type: ProductionType | None = None,
    ) -> list[WorkOrder]:
        work_orders = self.repository.list_work_orders_with_stage(stage, production_type)
        return [
            work_order
            for work_order in work_orders
            if self.is_visible_in_stage(work_order, stage, production_type)
        ]

    def is_visible_in_stage(
        self,
        work_order: WorkOrder,
        stage: ProcessStage,
        production_type: ProductionType | None = None,
    ) -> bool:
        stage_sequence = self.get_stage_sequence(work_order.coating_type)
        if stage not in stage_sequence:
            return False

        stage_state = self._get_stage_state(work_order, stage)
        if stage_state.status not in {StageStatus.NOT_STARTED, StageStatus.IN_PROGRESS}:
            return False

        previous_stage = self._get_previous_stage(stage_sequence, stage)
        if previous_stage is not None:
            previous_state = self._get_stage_state(work_order, previous_stage)
            if previous_state.status != StageStatus.DONE:
                return False

        if stage == ProcessStage.PRODUCTION:
            if work_order.production_type is None:
                return False
            if production_type is not None and work_order.production_type != production_type:
                return False

        return True

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
