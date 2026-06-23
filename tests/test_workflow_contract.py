import pytest
from sqlalchemy.orm import Session

from app.manager.repository import ManagerRepository
from app.manager.schemas import WorkOrderPlanAssignRequest
from app.manager.service import ManagerService
from app.process.enums import CoatingType, ProcessStage, ProductionType, StageStatus
from app.process.repository import ProcessRepository
from app.process.service import ProcessService
from app.shared.enums import QueueNamespace, WorkOrderKind
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


def build_work_order_create(
    *,
    title: str,
    coating_type: CoatingType,
    total_quantity: int,
    work_order_kind: WorkOrderKind = WorkOrderKind.STANDARD,
    is_ocynk: bool = False,
) -> WorkOrderCreate:
    return WorkOrderCreate(
        title=title,
        coating_type=coating_type,
        work_order_kind=work_order_kind,
        is_ocynk=is_ocynk,
        total_quantity=total_quantity,
        customer_name="ACME",
        ral_code="RAL 7016",
        paint_code="P-7016",
        paint_producer="AkzoNobel",
        received_date="2026-05-25",
        planned_pickup_date="2026-06-01",
        total_area_m2=24.0,
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
    work_order_kind: WorkOrderKind = WorkOrderKind.STANDARD,
    is_ocynk: bool = False,
) -> int:
    created = work_order_service.create_work_order(
        build_work_order_create(
            title=title,
            coating_type=coating_type,
            total_quantity=total_quantity,
            work_order_kind=work_order_kind,
            is_ocynk=is_ocynk,
        )
    )
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=production_type, queue_position=queue_position),
    )
    return created.id


def test_przemalowanka_is_independent_and_skips_surface_preparation(db_session: Session) -> None:
    work_order_service, process_service, manager_service, work_order_repository, process_repository = build_services(db_session)

    work_order_id = create_planned_work_order(
        work_order_service,
        manager_service,
        title="Contract Przemalowanka",
        coating_type=CoatingType.RAL,
        production_type=ProductionType.MANUAL,
        queue_position=1,
        work_order_kind=WorkOrderKind.PRZEMALOWANKA,
    )

    work_order = process_repository.get_work_order_with_stage_states(work_order_id)
    assert work_order is not None
    assert work_order.work_order_kind == WorkOrderKind.PRZEMALOWANKA
    assert work_order.is_correction is False
    assert work_order.parent_order_id is None
    assert work_order.queue_namespace == QueueNamespace.MAIN
    assert ProcessStage.SURFACE_PREPARATION not in process_service.get_stage_sequence_for_work_order(work_order)
    assert process_service.get_display_status(work_order).value == "PRODUCTION_MANUAL"
    assert work_order_id not in [
        item.id
        for item in process_service.list_visible_work_orders(ProcessStage.SURFACE_PREPARATION, include_done=True)
    ]
    assert work_order_id in [
        item.id
        for item in process_service.list_visible_work_orders(
            ProcessStage.PRODUCTION,
            production_type=ProductionType.MANUAL,
            include_done=True,
        )
    ]

    with pytest.raises(InvalidProcessStageTransitionError) as exc_info:
        process_service.start_stage(work_order_id, ProcessStage.SURFACE_PREPARATION)

    assert str(exc_info.value) == "Przemalowanka work orders do not go through surface preparation."

    production_start = process_service.start_stage(work_order_id, ProcessStage.PRODUCTION)
    assert production_start.stage_status.status.value == StageStatus.IN_PROGRESS


def test_ocynk_marker_preserves_ral_decoral_route_semantics(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    work_order_id = create_planned_work_order(
        work_order_service,
        manager_service,
        title="Contract Ocynk Decoral",
        coating_type=CoatingType.DECORAL,
        production_type=ProductionType.MANUAL,
        queue_position=1,
        is_ocynk=True,
    )

    work_order = process_repository.get_work_order_with_stage_states(work_order_id)
    assert work_order is not None
    assert work_order.is_ocynk is True
    assert process_service.get_stage_sequence_for_work_order(work_order) == [
        ProcessStage.SURFACE_PREPARATION,
        ProcessStage.PRODUCTION,
        ProcessStage.PACKING,
        ProcessStage.DECORAL_PRODUCTION,
    ]

    read_model = work_order_service.get_work_order(work_order_id)
    assert read_model.is_ocynk is True
    assert read_model.work_order_kind.value == WorkOrderKind.STANDARD


def advance_to_packing(process_service: ProcessService, work_order_id: int) -> None:
    work_order = process_service.get_work_order_process(work_order_id)
    is_correction_round = (
        work_order.active_batch is not None
        and work_order.active_batch.parent_batch_id is not None
    )
    if not work_order.is_correction and not is_correction_round:
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
        correction_profiles_quantity=correction_quantity if correction_quantity > 0 else None,
        correction_accessories_quantity=0 if correction_quantity > 0 else None,
        correction_reason_category="niedomalowanie" if correction_quantity > 0 else None,
    )


def test_s05_ral_manual_correction_round_cycles_parent_to_ready(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

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
    assert process_service.get_display_status(parent_after_split).value == "TO_BE_PLANNED"
    assert parent_after_split.completed_quantity == 7
    assert parent_after_split.current_active_quantity == 3

    manager_service.assign_plan(
        parent_id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, parent_id)
    complete_packing(process_service, parent_id, ok_quantity=3, correction_quantity=0)

    parent_final = process_repository.get_work_order_with_stage_states(parent_id)

    assert parent_final is not None
    assert process_service.get_display_status(parent_final).value == "READY"
    assert parent_final.completed_quantity == parent_final.total_quantity
    assert parent_final.current_active_quantity == 0


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
    assert s05_parent.completed_quantity + s05_parent.current_active_quantity == s05_parent.total_quantity

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
    # Corrected pieces return to the root's single Decoral pass; finish that returned batch.
    s07_root = process_repository.get_work_order_with_stage_states(s07_id)
    s07_returned = next(
        b for b in s07_root.quantity_batches if b.is_active and b.current_stage == ProcessStage.DECORAL_PRODUCTION
    )
    process_service.start_stage(s07_id, ProcessStage.DECORAL_PRODUCTION, batch_id=s07_returned.id)
    process_service.complete_decoral_production(s07_id, ok_quantity=3, correction_quantity=0, batch_id=s07_returned.id)

    s07_parent_final = process_repository.get_work_order_with_stage_states(s07_id)

    assert s07_parent_final is not None
    assert process_service.get_display_status(s07_parent_final).value == "READY"
    assert s07_parent_final.completed_quantity == s07_parent_final.total_quantity
    assert s07_parent_final.current_active_quantity == 0