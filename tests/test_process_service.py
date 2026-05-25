from sqlalchemy.orm import Session
import pytest

from app.manager.repository import ManagerRepository
from app.manager.schemas import WorkOrderPlanAssignRequest
from app.manager.service import ManagerService
from app.process.enums import CoatingType, ProcessStage, ProductionType, StageStatus
from app.process.repository import ProcessRepository
from app.process.service import ProcessService
from app.shared.exceptions import InvalidProcessStageTransitionError
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import WorkOrderCreate
from app.work_orders.service import WorkOrderService


def build_services(
    db_session: Session,
) -> tuple[WorkOrderService, ProcessService, ManagerService, WorkOrderRepository, ProcessRepository]:
    work_order_repository = WorkOrderRepository(db_session)
    process_repository = ProcessRepository(db_session)
    manager_repository = ManagerRepository(db_session)
    return (
        WorkOrderService(work_order_repository),
        ProcessService(process_repository),
        ManagerService(manager_repository),
        work_order_repository,
        process_repository,
    )


def advance_to_production(process_service: ProcessService, work_order_id: int) -> None:
    work_order = process_service.get_work_order_process(work_order_id)
    process_service.transition_stage(work_order_id, ProcessStage.SURFACE_PREPARATION, StageStatus.IN_PROGRESS)
    process_service.transition_stage(work_order_id, ProcessStage.SURFACE_PREPARATION, StageStatus.DONE)
    if work_order.production_type != ProductionType.MANUAL:
        process_service.transition_stage(work_order_id, ProcessStage.HANGING, StageStatus.IN_PROGRESS)
        process_service.transition_stage(work_order_id, ProcessStage.HANGING, StageStatus.DONE)


def advance_to_packing(process_service: ProcessService, work_order_id: int) -> None:
    advance_to_production(process_service, work_order_id)
    work_order = process_service.get_work_order_process(work_order_id)
    production_state = next(stage for stage in work_order.stage_states if stage.stage == ProcessStage.PRODUCTION)
    if production_state.status == StageStatus.NOT_STARTED:
        process_service.transition_stage(work_order_id, ProcessStage.PRODUCTION, StageStatus.IN_PROGRESS)
    process_service.transition_stage(work_order_id, ProcessStage.PRODUCTION, StageStatus.DONE)
    process_service.transition_stage(work_order_id, ProcessStage.PACKING, StageStatus.IN_PROGRESS)


def create_ral_work_order(work_order_service: WorkOrderService, title: str):
    return work_order_service.create_work_order(WorkOrderCreate(title=title, coating_type=CoatingType.RAL, total_quantity=100))


def test_creating_work_order_initializes_stage_states(db_session: Session) -> None:
    work_order_service, process_service, _, work_order_repository, _ = build_services(db_session)

    created = create_ral_work_order(work_order_service, "Init stages")
    stage_states = process_service.list_stage_states(created.id)

    assert [stage_state.stage for stage_state in stage_states] == [
        ProcessStage.SURFACE_PREPARATION,
        ProcessStage.HANGING,
        ProcessStage.PRODUCTION,
        ProcessStage.PACKING,
    ]
    assert all(stage_state.status == StageStatus.NOT_STARTED for stage_state in stage_states)
    persisted = work_order_repository.get_by_id(created.id)
    assert persisted is not None
    assert persisted.total_quantity == 100
    assert persisted.current_active_quantity == 100
    assert len(persisted.quantity_batches) == 1


def test_stage_transitions_forward(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    created = create_ral_work_order(work_order_service, "Forward flow")
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )

    process_service.transition_stage(created.id, ProcessStage.SURFACE_PREPARATION, StageStatus.IN_PROGRESS)
    process_service.transition_stage(created.id, ProcessStage.SURFACE_PREPARATION, StageStatus.DONE)

    work_order = process_repository.get_work_order_with_stage_states(created.id)

    assert work_order is not None
    assert process_service.is_visible_in_stage(work_order, ProcessStage.PRODUCTION, ProductionType.MANUAL)


def test_stage_transitions_backward(db_session: Session) -> None:
    work_order_service, process_service, _, _, process_repository = build_services(db_session)

    created = create_ral_work_order(work_order_service, "Backward flow")

    process_service.transition_stage(created.id, ProcessStage.SURFACE_PREPARATION, StageStatus.IN_PROGRESS)
    process_service.transition_stage(created.id, ProcessStage.SURFACE_PREPARATION, StageStatus.DONE)
    process_service.transition_stage(created.id, ProcessStage.SURFACE_PREPARATION, StageStatus.IN_PROGRESS)
    process_service.transition_stage(created.id, ProcessStage.SURFACE_PREPARATION, StageStatus.NOT_STARTED)

    work_order = process_repository.get_work_order_with_stage_states(created.id)

    assert work_order is not None
    surface_stage = next(stage for stage in work_order.stage_states if stage.stage == ProcessStage.SURFACE_PREPARATION)
    assert surface_stage.status == StageStatus.NOT_STARTED


def test_decoral_orders_include_decoral_production_stage(db_session: Session) -> None:
    work_order_service, process_service, _, _, _ = build_services(db_session)

    created = work_order_service.create_work_order(
        WorkOrderCreate(title="Decoral order", coating_type=CoatingType.DECORAL, total_quantity=100)
    )
    stage_states = process_service.list_stage_states(created.id)

    assert ProcessStage.DECORAL_PRODUCTION in [stage_state.stage for stage_state in stage_states]


def test_ral_orders_skip_decoral_production_stage(db_session: Session) -> None:
    work_order_service, process_service, _, _, _ = build_services(db_session)

    created = work_order_service.create_work_order(
        WorkOrderCreate(title="RAL order", coating_type=CoatingType.RAL, total_quantity=100)
    )
    stage_states = process_service.list_stage_states(created.id)

    assert ProcessStage.DECORAL_PRODUCTION not in [stage_state.stage for stage_state in stage_states]


def test_production_type_affects_visibility_logic(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, _ = build_services(db_session)

    manual_order = create_ral_work_order(work_order_service, "Manual order")
    automatic_order = create_ral_work_order(work_order_service, "Automatic order")
    unassigned_order = create_ral_work_order(work_order_service, "Unassigned production")

    manager_service.assign_plan(
        manual_order.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=2),
    )
    manager_service.assign_plan(
        automatic_order.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=1),
    )

    for work_order_id in [manual_order.id, automatic_order.id, unassigned_order.id]:
        advance_to_production(process_service, work_order_id)

    manual_visible = process_service.list_visible_work_orders(ProcessStage.PRODUCTION, ProductionType.MANUAL)
    automatic_visible = process_service.list_visible_work_orders(ProcessStage.PRODUCTION, ProductionType.AUTOMATIC)

    assert [work_order.id for work_order in manual_visible] == [manual_order.id]
    assert [work_order.id for work_order in automatic_visible] == [automatic_order.id]


def test_manual_path_skips_hanging_stage_visibility(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    manual_order = create_ral_work_order(work_order_service, "Manual skip hanging")
    manager_service.assign_plan(
        manual_order.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    process_service.transition_stage(manual_order.id, ProcessStage.SURFACE_PREPARATION, StageStatus.IN_PROGRESS)
    process_service.transition_stage(manual_order.id, ProcessStage.SURFACE_PREPARATION, StageStatus.DONE)
    work_order = process_repository.get_work_order_with_stage_states(manual_order.id)

    assert work_order is not None
    assert process_service.is_visible_in_stage(work_order, ProcessStage.HANGING) is False
    assert process_service.is_visible_in_stage(work_order, ProcessStage.PRODUCTION, ProductionType.MANUAL) is True


def test_automatic_path_requires_hanging_before_production(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    automatic_order = create_ral_work_order(work_order_service, "Automatic requires hanging")
    manager_service.assign_plan(
        automatic_order.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=1),
    )
    process_service.transition_stage(automatic_order.id, ProcessStage.SURFACE_PREPARATION, StageStatus.IN_PROGRESS)
    process_service.transition_stage(automatic_order.id, ProcessStage.SURFACE_PREPARATION, StageStatus.DONE)
    work_order = process_repository.get_work_order_with_stage_states(automatic_order.id)

    assert work_order is not None
    assert process_service.is_visible_in_stage(work_order, ProcessStage.HANGING) is True
    assert process_service.is_visible_in_stage(work_order, ProcessStage.PRODUCTION, ProductionType.AUTOMATIC) is False


def test_automatic_hanging_finish_starts_production_automatically(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    automatic_order = create_ral_work_order(work_order_service, "Automatic auto start")
    manager_service.assign_plan(
        automatic_order.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=1),
    )
    process_service.transition_stage(automatic_order.id, ProcessStage.SURFACE_PREPARATION, StageStatus.IN_PROGRESS)
    process_service.transition_stage(automatic_order.id, ProcessStage.SURFACE_PREPARATION, StageStatus.DONE)
    process_service.transition_stage(automatic_order.id, ProcessStage.HANGING, StageStatus.IN_PROGRESS)
    process_service.finish_stage(automatic_order.id, ProcessStage.HANGING)
    work_order = process_repository.get_work_order_with_stage_states(automatic_order.id)

    assert work_order is not None
    production_state = next(stage for stage in work_order.stage_states if stage.stage == ProcessStage.PRODUCTION)
    assert production_state.status == StageStatus.IN_PROGRESS


def test_decoral_path_goes_after_packing_for_manual_orders(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    created = work_order_service.create_work_order(
        WorkOrderCreate(title="Decoral manual path", coating_type=CoatingType.DECORAL, total_quantity=100)
    )
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    process_service.transition_stage(created.id, ProcessStage.SURFACE_PREPARATION, StageStatus.IN_PROGRESS)
    process_service.transition_stage(created.id, ProcessStage.SURFACE_PREPARATION, StageStatus.DONE)
    process_service.transition_stage(created.id, ProcessStage.PRODUCTION, StageStatus.IN_PROGRESS)
    process_service.transition_stage(created.id, ProcessStage.PRODUCTION, StageStatus.DONE)
    process_service.transition_stage(created.id, ProcessStage.PACKING, StageStatus.IN_PROGRESS)

    response = process_service.complete_packing(created.id, ok_quantity=100, correction_quantity=0)
    work_order = process_repository.get_work_order_with_stage_states(created.id)

    assert response.stage_status.stage == ProcessStage.DECORAL_PRODUCTION
    assert work_order is not None
    assert work_order.completed_quantity == 0
    assert work_order.current_active_quantity == 100
    assert process_service.get_display_status(work_order).value == "DECORAL_PRODUCTION"


def test_decoral_production_finishes_order(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    created = work_order_service.create_work_order(
        WorkOrderCreate(title="Decoral finish", coating_type=CoatingType.DECORAL, total_quantity=100)
    )
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    process_service.transition_stage(created.id, ProcessStage.SURFACE_PREPARATION, StageStatus.IN_PROGRESS)
    process_service.transition_stage(created.id, ProcessStage.SURFACE_PREPARATION, StageStatus.DONE)
    process_service.transition_stage(created.id, ProcessStage.PRODUCTION, StageStatus.IN_PROGRESS)
    process_service.transition_stage(created.id, ProcessStage.PRODUCTION, StageStatus.DONE)
    process_service.transition_stage(created.id, ProcessStage.PACKING, StageStatus.IN_PROGRESS)
    process_service.complete_packing(created.id, ok_quantity=100, correction_quantity=0)
    process_service.transition_stage(created.id, ProcessStage.DECORAL_PRODUCTION, StageStatus.IN_PROGRESS)
    process_service.finish_stage(created.id, ProcessStage.DECORAL_PRODUCTION)
    work_order = process_repository.get_work_order_with_stage_states(created.id)

    assert work_order is not None
    assert work_order.completed_quantity == 100
    assert work_order.current_active_quantity == 0
    assert process_service.get_display_status(work_order).value == "READY"


def test_corrections_return_to_correct_production_type(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    manual_order = create_ral_work_order(work_order_service, "Manual correction")
    automatic_order = create_ral_work_order(work_order_service, "Automatic correction")
    manager_service.assign_plan(
        manual_order.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    manager_service.assign_plan(
        automatic_order.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=2),
    )
    advance_to_packing(process_service, manual_order.id)
    advance_to_packing(process_service, automatic_order.id)
    process_service.complete_packing(manual_order.id, ok_quantity=90, correction_quantity=10)
    process_service.complete_packing(automatic_order.id, ok_quantity=90, correction_quantity=10)
    manual_work_order = process_repository.get_work_order_with_stage_states(manual_order.id)
    automatic_work_order = process_repository.get_work_order_with_stage_states(automatic_order.id)

    assert manual_work_order is not None
    assert automatic_work_order is not None
    assert process_service.is_visible_in_stage(manual_work_order, ProcessStage.PRODUCTION, ProductionType.MANUAL) is True
    assert process_service.is_visible_in_stage(automatic_work_order, ProcessStage.PRODUCTION, ProductionType.AUTOMATIC) is True


def test_queue_position_exists_and_is_sortable(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, _ = build_services(db_session)

    first = create_ral_work_order(work_order_service, "Queue 1")
    second = create_ral_work_order(work_order_service, "Queue 2")
    third = create_ral_work_order(work_order_service, "Queue 3")

    manager_service.assign_plan(
        first.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=30),
    )
    manager_service.assign_plan(
        second.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=10),
    )
    manager_service.assign_plan(
        third.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=20),
    )

    visible = process_service.list_visible_work_orders(ProcessStage.SURFACE_PREPARATION)

    assert [work_order.queue_position for work_order in visible] == [10, 20, 30]


def test_unplanned_orders_are_hidden_from_process_visibility(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, _ = build_services(db_session)

    planned_order = create_ral_work_order(work_order_service, "Planned")
    unplanned_order = create_ral_work_order(work_order_service, "Unplanned")

    manager_service.assign_plan(
        planned_order.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )

    visible = process_service.list_visible_work_orders(ProcessStage.SURFACE_PREPARATION)

    assert [work_order.id for work_order in visible] == [planned_order.id]


def test_complete_packing_splits_ok_and_correction_quantities(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    created = create_ral_work_order(work_order_service, "Split packing")
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)

    response = process_service.complete_packing(created.id, ok_quantity=90, correction_quantity=10)
    work_order = process_repository.get_work_order_with_stage_states(created.id)

    assert response.stage_status.stage == ProcessStage.PRODUCTION
    assert work_order is not None
    assert work_order.completed_quantity == 90
    assert work_order.current_active_quantity == 10
    assert len(work_order.quantity_batches) == 2
    assert work_order.active_batch is not None
    assert work_order.active_batch.type.value == "CORRECTION"

    stage_states = {stage_state.stage: stage_state.status for stage_state in work_order.stage_states}
    assert stage_states[ProcessStage.SURFACE_PREPARATION] == StageStatus.DONE
    assert stage_states[ProcessStage.HANGING] == StageStatus.NOT_STARTED
    assert stage_states[ProcessStage.PRODUCTION] == StageStatus.NOT_STARTED
    assert stage_states[ProcessStage.PACKING] == StageStatus.NOT_STARTED


def test_complete_packing_full_ok_marks_work_order_ready(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    created = create_ral_work_order(work_order_service, "Full ok")
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)

    response = process_service.complete_packing(created.id, ok_quantity=100, correction_quantity=0)
    work_order = process_repository.get_work_order_with_stage_states(created.id)

    assert response.stage_status.stage == ProcessStage.PACKING
    assert work_order is not None
    assert work_order.completed_quantity == 100
    assert work_order.current_active_quantity == 0
    assert process_service.get_display_status(work_order).value == "READY"


def test_complete_packing_full_correction_returns_entire_batch(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    created = create_ral_work_order(work_order_service, "Full correction")
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)

    response = process_service.complete_packing(created.id, ok_quantity=0, correction_quantity=100)
    work_order = process_repository.get_work_order_with_stage_states(created.id)

    assert response.stage_status.stage == ProcessStage.PRODUCTION
    assert work_order is not None
    assert work_order.completed_quantity == 0
    assert work_order.current_active_quantity == 100
    assert work_order.active_batch is not None
    assert work_order.active_batch.type.value == "CORRECTION"


def test_multiple_packing_corrections_can_chain(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    created = create_ral_work_order(work_order_service, "Multiple corrections")
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)
    process_service.complete_packing(created.id, ok_quantity=70, correction_quantity=30)

    process_service.transition_stage(created.id, ProcessStage.PRODUCTION, StageStatus.IN_PROGRESS)
    process_service.transition_stage(created.id, ProcessStage.PRODUCTION, StageStatus.DONE)
    process_service.transition_stage(created.id, ProcessStage.PACKING, StageStatus.IN_PROGRESS)
    process_service.complete_packing(created.id, ok_quantity=20, correction_quantity=10)

    work_order = process_repository.get_work_order_with_stage_states(created.id)

    assert work_order is not None
    assert work_order.completed_quantity == 90
    assert work_order.current_active_quantity == 10
    assert len(work_order.quantity_batches) == 3


def test_fully_packed_order_cannot_reopen_any_stage(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, _ = build_services(db_session)

    created = create_ral_work_order(work_order_service, "No reopen after full pack")
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)
    process_service.complete_packing(created.id, ok_quantity=100, correction_quantity=0)

    with pytest.raises(InvalidProcessStageTransitionError) as exc_info:
        process_service.reopen_stage(created.id, ProcessStage.PACKING)

    assert str(exc_info.value) == "Cannot reopen process stages because the work order has no active quantity remaining."


def test_correction_active_batch_can_still_continue_workflow(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    created = create_ral_work_order(work_order_service, "Correction continues workflow")
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)
    process_service.complete_packing(created.id, ok_quantity=80, correction_quantity=20)

    started = process_service.start_stage(created.id, ProcessStage.PRODUCTION)
    process_service.finish_stage(created.id, ProcessStage.PRODUCTION)
    reopened = process_service.reopen_stage(created.id, ProcessStage.PRODUCTION)
    work_order = process_repository.get_work_order_with_stage_states(created.id)

    assert started.stage_status.status.value == StageStatus.IN_PROGRESS
    assert reopened.stage_status.status.value == StageStatus.IN_PROGRESS
    assert work_order is not None
    assert work_order.current_active_quantity == 20