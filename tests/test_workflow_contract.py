from sqlalchemy.orm import Session

from app.manager.repository import ManagerRepository
from app.manager.schemas import WorkOrderPlanAssignRequest
from app.manager.service import ManagerService
from app.process.enums import CoatingType, ProcessStage, ProductionType, StageStatus
from app.process.repository import ProcessRepository
from app.process.service import ProcessService
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


def build_work_order_create(
    *,
    title: str,
    coating_type: CoatingType,
    total_quantity: int,
) -> WorkOrderCreate:
    return WorkOrderCreate(
        title=title,
        coating_type=coating_type,
        total_quantity=total_quantity,
        customer_name="ACME",
        ral_code="RAL 7016",
        paint_producer="AkzoNobel",
        received_date="2026-05-25",
        profiles_to_count=True,
        accessories_to_count=True,
    )


def create_planned_work_order(
    work_order_service: WorkOrderService,
    manager_service: ManagerService,
    *,
    title: str,
    coating_type: CoatingType,
    production_type: ProductionType,
    queue_position: int,
    total_quantity: int = 10,
) -> int:
    created = work_order_service.create_work_order(
        build_work_order_create(title=title, coating_type=coating_type, total_quantity=total_quantity)
    )
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=production_type, queue_position=queue_position),
    )
    return created.id


def advance_to_packing(process_service: ProcessService, work_order_id: int) -> None:
    work_order = process_service.get_work_order_process(work_order_id)
    if not work_order.is_correction:
        process_service.transition_stage(work_order_id, ProcessStage.SURFACE_PREPARATION, StageStatus.IN_PROGRESS)
        process_service.transition_stage(work_order_id, ProcessStage.SURFACE_PREPARATION, StageStatus.DONE)
    if work_order.production_type == ProductionType.AUTOMATIC:
        process_service.transition_stage(work_order_id, ProcessStage.HANGING, StageStatus.IN_PROGRESS)
        return

    process_service.transition_stage(work_order_id, ProcessStage.PRODUCTION, StageStatus.IN_PROGRESS)
    process_service.transition_stage(work_order_id, ProcessStage.PRODUCTION, StageStatus.DONE)
    process_service.transition_stage(work_order_id, ProcessStage.PACKING, StageStatus.IN_PROGRESS)


def complete_packing(
    process_service: ProcessService,
    work_order_id: int,
    *,
    ok_quantity: int,
    correction_quantity: int,
):
    return process_service.complete_packing(
        work_order_id,
        counted_quantity=ok_quantity + correction_quantity,
        ok_quantity=ok_quantity,
        correction_quantity=correction_quantity,
    )


def test_s05_ral_manual_correction_child_close_merges_parent(db_session: Session) -> None:
    work_order_service, process_service, manager_service, work_order_repository, process_repository = build_services(db_session)

    parent_id = create_planned_work_order(
        work_order_service,
        manager_service,
        title="Contract S05 full close",
        coating_type=CoatingType.RAL,
        production_type=ProductionType.MANUAL,
        queue_position=1,
    )
    advance_to_packing(process_service, parent_id)
    complete_packing(process_service, parent_id, ok_quantity=7, correction_quantity=3)

    parent_after_split = process_repository.get_work_order_with_stage_states(parent_id)
    assert parent_after_split is not None
    assert process_service.get_display_status(parent_after_split).value == "WAITING_FOR_CORRECTIONS"

    correction_order = next(
        item for item in work_order_repository.list(limit=20, offset=0) if item.parent_order_id == parent_id
    )
    manager_service.assign_plan(
        correction_order.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=2),
    )
    advance_to_packing(process_service, correction_order.id)
    complete_packing(process_service, correction_order.id, ok_quantity=3, correction_quantity=0)

    parent_final = process_repository.get_work_order_with_stage_states(parent_id)
    child_final = process_repository.get_work_order_with_stage_states(correction_order.id)

    assert parent_final is not None
    assert child_final is not None
    assert process_service.get_display_status(parent_final).value == "READY"
    assert process_service.get_display_status(child_final).value == "READY"
    assert parent_final.completed_quantity == parent_final.total_quantity
    assert parent_final.current_active_quantity == 0
    assert process_service.get_waiting_ok_quantity(parent_final) == 0
    assert process_service.get_pending_correction_quantity(parent_final) == 0
    assert child_final.completed_quantity == child_final.total_quantity
    assert child_final.current_active_quantity == 0


def test_workflow_contract_core_invariants(db_session: Session) -> None:
    """High-level regression contract from docs/WORKFLOW.md using S01, S05, and S07."""
    work_order_service, process_service, manager_service, work_order_repository, process_repository = build_services(db_session)

    # S01: RAL + MANUAL + no correction -> READY only when fully complete.
    s01_id = create_planned_work_order(
        work_order_service,
        manager_service,
        title="Contract S01",
        coating_type=CoatingType.RAL,
        production_type=ProductionType.MANUAL,
        queue_position=1,
    )
    advance_to_packing(process_service, s01_id)
    complete_packing(process_service, s01_id, ok_quantity=10, correction_quantity=0)
    s01 = process_repository.get_work_order_with_stage_states(s01_id)

    assert s01 is not None
    assert process_service.get_display_status(s01).value == "READY"
    assert s01.completed_quantity == s01.total_quantity
    assert s01.current_active_quantity == 0

    # S05: RAL + MANUAL + correction split -> quantity conservation and parent not READY with open correction.
    s05_id = create_planned_work_order(
        work_order_service,
        manager_service,
        title="Contract S05",
        coating_type=CoatingType.RAL,
        production_type=ProductionType.MANUAL,
        queue_position=2,
    )
    advance_to_packing(process_service, s05_id)
    complete_packing(process_service, s05_id, ok_quantity=7, correction_quantity=3)
    s05_parent = process_repository.get_work_order_with_stage_states(s05_id)

    assert s05_parent is not None
    assert process_service.get_display_status(s05_parent).value != "READY"
    assert s05_parent.completed_quantity + process_service.get_waiting_ok_quantity(s05_parent) + process_service.get_pending_correction_quantity(s05_parent) == s05_parent.total_quantity

    # S07: DECORAL + MANUAL + correction split -> parent stays non-READY while correction open, READY only after full close.
    s07_id = create_planned_work_order(
        work_order_service,
        manager_service,
        title="Contract S07",
        coating_type=CoatingType.DECORAL,
        production_type=ProductionType.MANUAL,
        queue_position=3,
    )
    advance_to_packing(process_service, s07_id)
    parent_pack_response = complete_packing(process_service, s07_id, ok_quantity=7, correction_quantity=3)
    s07_parent = process_repository.get_work_order_with_stage_states(s07_id)

    assert s07_parent is not None
    assert process_service.get_display_status(s07_parent).value != "READY"

    process_service.start_stage(s07_id, ProcessStage.DECORAL_PRODUCTION, batch_id=parent_pack_response.batch_id)
    process_service.finish_stage(s07_id, ProcessStage.DECORAL_PRODUCTION, batch_id=parent_pack_response.batch_id)
    s07_parent_after_ok_batch = process_repository.get_work_order_with_stage_states(s07_id)

    assert s07_parent_after_ok_batch is not None
    assert process_service.get_display_status(s07_parent_after_ok_batch).value != "READY"

    s07_correction = next(
        item for item in work_order_repository.list(limit=20, offset=0) if item.parent_order_id == s07_id
    )
    manager_service.assign_plan(
        s07_correction.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=4),
    )
    advance_to_packing(process_service, s07_correction.id)
    complete_packing(process_service, s07_correction.id, ok_quantity=3, correction_quantity=0)
    process_service.transition_stage(s07_correction.id, ProcessStage.DECORAL_PRODUCTION, StageStatus.IN_PROGRESS)
    process_service.finish_stage(s07_correction.id, ProcessStage.DECORAL_PRODUCTION)

    s07_parent_final = process_repository.get_work_order_with_stage_states(s07_id)

    assert s07_parent_final is not None
    assert process_service.get_display_status(s07_parent_final).value == "READY"
    assert s07_parent_final.completed_quantity == s07_parent_final.total_quantity
    assert s07_parent_final.current_active_quantity == 0