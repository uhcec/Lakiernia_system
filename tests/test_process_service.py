from sqlalchemy.orm import Session

from app.process.enums import CoatingType, ProcessStage, ProductionType, StageStatus
from app.process.repository import ProcessRepository
from app.process.service import ProcessService
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import WorkOrderCreate
from app.work_orders.service import WorkOrderService


def build_services(db_session: Session) -> tuple[WorkOrderService, ProcessService, WorkOrderRepository, ProcessRepository]:
    work_order_repository = WorkOrderRepository(db_session)
    process_repository = ProcessRepository(db_session)
    return (
        WorkOrderService(work_order_repository),
        ProcessService(process_repository),
        work_order_repository,
        process_repository,
    )


def advance_to_production(process_service: ProcessService, work_order_id: int) -> None:
    process_service.transition_stage(work_order_id, ProcessStage.SURFACE_PREPARATION, StageStatus.IN_PROGRESS)
    process_service.transition_stage(work_order_id, ProcessStage.SURFACE_PREPARATION, StageStatus.DONE)
    process_service.transition_stage(work_order_id, ProcessStage.HANGING, StageStatus.IN_PROGRESS)
    process_service.transition_stage(work_order_id, ProcessStage.HANGING, StageStatus.DONE)


def test_creating_work_order_initializes_stage_states(db_session: Session) -> None:
    work_order_service, process_service, _, _ = build_services(db_session)

    created = work_order_service.create_work_order(WorkOrderCreate(title="Init stages"))
    stage_states = process_service.list_stage_states(created.id)

    assert [stage_state.stage for stage_state in stage_states] == [
        ProcessStage.SURFACE_PREPARATION,
        ProcessStage.HANGING,
        ProcessStage.PRODUCTION,
        ProcessStage.PACKING,
    ]
    assert all(stage_state.status == StageStatus.NOT_STARTED for stage_state in stage_states)


def test_stage_transitions_forward(db_session: Session) -> None:
    work_order_service, process_service, _, process_repository = build_services(db_session)

    created = work_order_service.create_work_order(WorkOrderCreate(title="Forward flow"))

    process_service.transition_stage(created.id, ProcessStage.SURFACE_PREPARATION, StageStatus.IN_PROGRESS)
    process_service.transition_stage(created.id, ProcessStage.SURFACE_PREPARATION, StageStatus.DONE)

    work_order = process_repository.get_work_order_with_stage_states(created.id)

    assert work_order is not None
    assert process_service.is_visible_in_stage(work_order, ProcessStage.HANGING)


def test_stage_transitions_backward(db_session: Session) -> None:
    work_order_service, process_service, _, process_repository = build_services(db_session)

    created = work_order_service.create_work_order(WorkOrderCreate(title="Backward flow"))

    process_service.transition_stage(created.id, ProcessStage.SURFACE_PREPARATION, StageStatus.IN_PROGRESS)
    process_service.transition_stage(created.id, ProcessStage.SURFACE_PREPARATION, StageStatus.DONE)
    process_service.transition_stage(created.id, ProcessStage.SURFACE_PREPARATION, StageStatus.IN_PROGRESS)
    process_service.transition_stage(created.id, ProcessStage.SURFACE_PREPARATION, StageStatus.NOT_STARTED)

    work_order = process_repository.get_work_order_with_stage_states(created.id)

    assert work_order is not None
    surface_stage = next(stage for stage in work_order.stage_states if stage.stage == ProcessStage.SURFACE_PREPARATION)
    assert surface_stage.status == StageStatus.NOT_STARTED


def test_decoral_orders_include_decoral_production_stage(db_session: Session) -> None:
    work_order_service, process_service, _, _ = build_services(db_session)

    created = work_order_service.create_work_order(
        WorkOrderCreate(title="Decoral order", coating_type=CoatingType.DECORAL)
    )
    stage_states = process_service.list_stage_states(created.id)

    assert ProcessStage.DECORAL_PRODUCTION in [stage_state.stage for stage_state in stage_states]


def test_ral_orders_skip_decoral_production_stage(db_session: Session) -> None:
    work_order_service, process_service, _, _ = build_services(db_session)

    created = work_order_service.create_work_order(
        WorkOrderCreate(title="RAL order", coating_type=CoatingType.RAL)
    )
    stage_states = process_service.list_stage_states(created.id)

    assert ProcessStage.DECORAL_PRODUCTION not in [stage_state.stage for stage_state in stage_states]


def test_production_type_affects_visibility_logic(db_session: Session) -> None:
    work_order_service, process_service, _, _ = build_services(db_session)

    manual_order = work_order_service.create_work_order(
        WorkOrderCreate(title="Manual order", production_type=ProductionType.MANUAL)
    )
    automatic_order = work_order_service.create_work_order(
        WorkOrderCreate(title="Automatic order", production_type=ProductionType.AUTOMATIC)
    )
    unassigned_order = work_order_service.create_work_order(WorkOrderCreate(title="Unassigned production"))

    for work_order_id in [manual_order.id, automatic_order.id, unassigned_order.id]:
        advance_to_production(process_service, work_order_id)

    manual_visible = process_service.list_visible_work_orders(ProcessStage.PRODUCTION, ProductionType.MANUAL)
    automatic_visible = process_service.list_visible_work_orders(ProcessStage.PRODUCTION, ProductionType.AUTOMATIC)

    assert [work_order.id for work_order in manual_visible] == [manual_order.id]
    assert [work_order.id for work_order in automatic_visible] == [automatic_order.id]


def test_queue_position_exists_and_is_sortable(db_session: Session) -> None:
    work_order_service, process_service, work_order_repository, _ = build_services(db_session)

    first = work_order_service.create_work_order(WorkOrderCreate(title="Queue 1"))
    second = work_order_service.create_work_order(WorkOrderCreate(title="Queue 2"))
    third = work_order_service.create_work_order(WorkOrderCreate(title="Queue 3"))

    first_model = work_order_repository.get_by_id(first.id)
    second_model = work_order_repository.get_by_id(second.id)
    third_model = work_order_repository.get_by_id(third.id)

    assert first_model is not None
    assert second_model is not None
    assert third_model is not None

    first_model.queue_position = 30
    second_model.queue_position = 10
    third_model.queue_position = 20
    work_order_repository.commit()

    visible = process_service.list_visible_work_orders(ProcessStage.SURFACE_PREPARATION)

    assert [work_order.queue_position for work_order in visible] == [10, 20, 30]