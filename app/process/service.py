from collections.abc import Sequence
from datetime import UTC, datetime

from app.process.enums import CoatingType, ProcessStage, ProductionType, StageStatus
from app.process.models import WorkOrderStageState
from app.process.repository import ProcessRepository
from app.process.schemas import ProcessStageStatusRead, ProcessStageWorkOrderRead, StageStatusView
from app.shared.exceptions import InvalidProcessStageTransitionError, ResourceNotFoundError
from app.work_orders.models import WorkOrder
from app.work_orders.schemas import build_coating_type_view, build_production_type_view


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

    def list_stage_work_orders(
        self,
        stage: ProcessStage,
        production_type: ProductionType | None = None,
    ) -> list[ProcessStageWorkOrderRead]:
        work_orders = self.list_visible_work_orders(stage, production_type)
        return [self._to_stage_work_order_read(work_order, stage) for work_order in work_orders]

    def start_stage(self, work_order_id: int, stage: ProcessStage) -> ProcessStageWorkOrderRead:
        self.transition_stage(work_order_id, stage, StageStatus.IN_PROGRESS)
        work_order = self.get_work_order_process(work_order_id)
        return self._to_stage_work_order_read(work_order, stage)

    def finish_stage(self, work_order_id: int, stage: ProcessStage) -> ProcessStageWorkOrderRead:
        self.transition_stage(work_order_id, stage, StageStatus.DONE)
        work_order = self.get_work_order_process(work_order_id)
        return self._to_stage_work_order_read(work_order, stage)

    def reopen_stage(self, work_order_id: int, stage: ProcessStage) -> ProcessStageWorkOrderRead:
        work_order = self.get_work_order_process(work_order_id)
        stage_state = self._get_stage_state(work_order, stage)

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
        if not self._is_planned(work_order):
            return False

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
            if production_type is not None and work_order.production_type != production_type:
                return False

        return True

    @staticmethod
    def _is_planned(work_order: WorkOrder) -> bool:
        return work_order.production_type is not None and work_order.queue_position is not None

    @staticmethod
    def build_stage_status_view(status: StageStatus) -> StageStatusView:
        return StageStatusView(value=status, label=status.polish_label)

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

    def _to_stage_work_order_read(self, work_order: WorkOrder, stage: ProcessStage) -> ProcessStageWorkOrderRead:
        stage_state = self._get_stage_state(work_order, stage)
        return ProcessStageWorkOrderRead(
            id=work_order.id,
            order_number=work_order.order_number,
            title=work_order.title,
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
