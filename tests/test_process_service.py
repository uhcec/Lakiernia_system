from concurrent.futures import ThreadPoolExecutor
import json

from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
import pytest

from app.database.base import Base
from app.audit.context import StationContext
from app.audit.models import AuditEvent
from app.manager.repository import ManagerRepository
from app.manager.schemas import WorkOrderPlanAssignRequest
from app.manager.service import ManagerService
from app.process.enums import CoatingType, ProcessStage, ProductionType, QuantityBatchType, StageStatus
from app.process.models import ProcessResourceLock
from app.process.repository import ProcessRepository
from app.process.service import ProcessService
from app.paints.schemas import PaintDeliveryCreate
from app.shared.enums import QueueNamespace, StationId, WorkOrderStatus
from app.shared.exceptions import InvalidManagerPlanningError, InvalidProcessStageTransitionError
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import WorkOrderCreate
from app.work_orders.service import WorkOrderService


def build_work_order_create(
    *,
    title: str,
    coating_type: CoatingType = CoatingType.RAL,
    total_quantity: int = 100,
) -> WorkOrderCreate:
    return WorkOrderCreate(
        title=title,
        coating_type=coating_type,
        total_quantity=total_quantity,
        customer_name="ACME",
        ral_code="RAL 7016",
        paint_code="P-7016",
        paint_producer="AkzoNobel",
        received_date="2026-05-25",
        total_area_m2=24.0,
        profiles_to_count=True,
        accessories_to_count=True,
    )


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
    is_correction_round = (
        work_order.active_batch is not None
        and work_order.active_batch.parent_batch_id is not None
    )
    if work_order.is_correction or is_correction_round:
        if work_order.production_type != ProductionType.MANUAL:
            process_service.transition_stage(work_order_id, ProcessStage.HANGING, StageStatus.IN_PROGRESS)
            process_service.finish_stage(work_order_id, ProcessStage.HANGING)
        return

    process_service.transition_stage(work_order_id, ProcessStage.SURFACE_PREPARATION, StageStatus.IN_PROGRESS)
    process_service.transition_stage(work_order_id, ProcessStage.SURFACE_PREPARATION, StageStatus.DONE)
    if work_order.production_type != ProductionType.MANUAL:
        process_service.transition_stage(work_order_id, ProcessStage.HANGING, StageStatus.IN_PROGRESS)
        process_service.finish_stage(work_order_id, ProcessStage.HANGING)


def advance_to_packing(process_service: ProcessService, work_order_id: int) -> None:
    advance_to_production(process_service, work_order_id)
    work_order = process_service.get_work_order_process(work_order_id)
    if work_order.production_type == ProductionType.MANUAL:
        production_state = next(stage for stage in work_order.stage_states if stage.stage == ProcessStage.PRODUCTION)
        if production_state.status == StageStatus.NOT_STARTED:
            process_service.transition_stage(work_order_id, ProcessStage.PRODUCTION, StageStatus.IN_PROGRESS)
        process_service.transition_stage(work_order_id, ProcessStage.PRODUCTION, StageStatus.DONE)
    elif work_order.production_type == ProductionType.AUTOMATIC:
        process_service.paint_service.record_delivery(
            PaintDeliveryCreate(
                ral_code=work_order.ral_code,
                paint_producer=work_order.paint_producer,
                paint_code=work_order.paint_code or "P-UNKNOWN",
                quantity_kg=100.0,
            )
        )
        process_service.record_automatic_paint_consumption(work_order_id, consumed_paint_quantity_kg=1.0)
    work_order = process_service.get_work_order_process(work_order_id)
    packing_state = next(stage for stage in work_order.stage_states if stage.stage == ProcessStage.PACKING)
    if packing_state.status == StageStatus.NOT_STARTED:
        process_service.transition_stage(work_order_id, ProcessStage.PACKING, StageStatus.IN_PROGRESS)


def create_ral_work_order(work_order_service: WorkOrderService, title: str):
    return work_order_service.create_work_order(build_work_order_create(title=title, coating_type=CoatingType.RAL, total_quantity=100))


def complete_packing(
    process_service: ProcessService,
    work_order_id: int,
    *,
    ok_quantity: int,
    correction_quantity: int,
    correction_profiles_quantity: int | None = None,
    correction_accessories_quantity: int | None = None,
    correction_reason_category: str | None = None,
    correction_reason_note: str | None = None,
):
    return process_service.complete_packing(
        work_order_id,
        counted_quantity=ok_quantity + correction_quantity,
        ok_quantity=ok_quantity,
        correction_quantity=correction_quantity,
        correction_profiles_quantity=(
            correction_profiles_quantity if correction_profiles_quantity is not None else correction_quantity
        ) if correction_quantity > 0 else None,
        correction_accessories_quantity=(
            correction_accessories_quantity if correction_accessories_quantity is not None else 0
        ) if correction_quantity > 0 else None,
        correction_reason_category=(correction_reason_category or "niedomalowanie") if correction_quantity > 0 else None,
        correction_reason_note=correction_reason_note if correction_quantity > 0 else None,
    )


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


def test_start_stage_records_station_audit_event(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, _ = build_services(db_session)
    created = create_ral_work_order(work_order_service, "Audit stage")
    manager_service.assign_plan(created.id, WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1))

    process_service.start_stage(
        created.id,
        ProcessStage.SURFACE_PREPARATION,
        counted_quantity=100,
        station_context=StationContext(station_id=StationId.SURFACE_PREPARATION),
    )

    event = db_session.scalar(select(AuditEvent).where(AuditEvent.event_type == "process.stage.started"))

    assert event is not None
    assert event.station_id == StationId.SURFACE_PREPARATION
    assert event.work_order_id == created.id
    assert event.target_type == "process_stage"
    assert json.loads(event.details_json or "{}") == {
        "stage": "SURFACE_PREPARATION",
        "target_status": "IN_PROGRESS",
        "batch_id": None,
    }


def test_surface_preparation_start_does_not_require_counted_quantity_but_finish_does(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, _ = build_services(db_session)
    created = create_ral_work_order(work_order_service, "Surface count on finish")
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )

    start_response = process_service.start_stage(created.id, ProcessStage.SURFACE_PREPARATION)

    assert start_response.stage_status.status.value == StageStatus.IN_PROGRESS
    assert start_response.counted_quantity is None

    with pytest.raises(InvalidProcessStageTransitionError) as exc_info:
        process_service.finish_stage(created.id, ProcessStage.SURFACE_PREPARATION)

    assert str(exc_info.value) == "Counted quantity is required to finish surface preparation."


def test_surface_preparation_finish_persists_counted_quantity(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    created = create_ral_work_order(work_order_service, "Surface finish count")
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )

    process_service.start_stage(created.id, ProcessStage.SURFACE_PREPARATION)
    response = process_service.finish_stage(created.id, ProcessStage.SURFACE_PREPARATION, counted_quantity=95)
    work_order = process_repository.get_work_order_with_stage_states(created.id)

    assert response.stage_status.status.value == StageStatus.DONE
    assert response.counted_quantity == 95
    assert response.quantity_difference == -5
    assert work_order is not None
    surface_state = next(stage for stage in work_order.stage_states if stage.stage == ProcessStage.SURFACE_PREPARATION)
    assert surface_state.counted_quantity == 95


def test_office_and_manager_read_models_expose_surface_preparation_discrepancy(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, _ = build_services(db_session)
    created = create_ral_work_order(work_order_service, "Office manager discrepancy")
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )

    process_service.start_stage(created.id, ProcessStage.SURFACE_PREPARATION)
    process_service.finish_stage(created.id, ProcessStage.SURFACE_PREPARATION, counted_quantity=95)

    office_read = work_order_service.get_work_order(created.id)
    manager_read = manager_service.list_planned_work_orders()[0]

    assert office_read.surface_preparation_counted_quantity == 95
    assert office_read.surface_preparation_quantity_difference == -5
    assert manager_read.surface_preparation_counted_quantity == 95
    assert manager_read.surface_preparation_quantity_difference == -5


def test_packing_correction_records_packing_and_correction_audit_events(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, _ = build_services(db_session)
    created = create_ral_work_order(work_order_service, "Audit packing")
    manager_service.assign_plan(created.id, WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1))
    advance_to_packing(process_service, created.id)

    process_service.complete_packing(
        created.id,
        counted_quantity=100,
        ok_quantity=70,
        correction_quantity=30,
        correction_profiles_quantity=25,
        correction_accessories_quantity=5,
        correction_reason_category="wtrącenia",
        correction_reason_note="widoczne punkty",
        station_context=StationContext(station_id=StationId.PACKING),
    )

    events = db_session.scalars(
        select(AuditEvent)
        .where(AuditEvent.station_id == StationId.PACKING)
        .order_by(AuditEvent.id.asc())
    ).all()
    event_types = [event.event_type for event in events]

    assert "work_order.returned_to_correction_planning" in event_types
    assert "process.packing.completed" in event_types
    packing_event = next(event for event in events if event.event_type == "process.packing.completed")
    correction_event = next(event for event in events if event.event_type == "work_order.returned_to_correction_planning")
    assert json.loads(packing_event.details_json or "{}") == {
        "stage": "PACKING",
        "batch_id": 1,
        "counted_quantity": 100,
        "ok_quantity": 70,
        "correction_quantity": 30,
        "correction_profiles_quantity": 25,
        "correction_accessories_quantity": 5,
    }
    correction_details = json.loads(correction_event.details_json or "{}")
    assert correction_details["correction_reason_category"] == "wtrącenia"
    assert correction_details["ok_quantity"] == 70
    assert correction_details["correction_quantity"] == 30


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
        build_work_order_create(title="Decoral order", coating_type=CoatingType.DECORAL, total_quantity=100)
    )
    stage_states = process_service.list_stage_states(created.id)

    assert ProcessStage.DECORAL_PRODUCTION in [stage_state.stage for stage_state in stage_states]


def test_ral_orders_skip_decoral_production_stage(db_session: Session) -> None:
    work_order_service, process_service, _, _, _ = build_services(db_session)

    created = work_order_service.create_work_order(
        build_work_order_create(title="RAL order", coating_type=CoatingType.RAL, total_quantity=100)
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

    advance_to_production(process_service, manual_order.id)
    advance_to_production(process_service, automatic_order.id)
    process_service.transition_stage(unassigned_order.id, ProcessStage.SURFACE_PREPARATION, StageStatus.IN_PROGRESS)
    process_service.transition_stage(unassigned_order.id, ProcessStage.SURFACE_PREPARATION, StageStatus.DONE)

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


def test_automatic_path_is_visible_in_production_preview_when_ready_for_hanging(db_session: Session) -> None:
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
    assert process_service.is_visible_in_stage(work_order, ProcessStage.PRODUCTION, ProductionType.AUTOMATIC) is True


def test_automatic_hanging_finish_makes_production_visible(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    automatic_order = create_ral_work_order(work_order_service, "Automatic auto start")
    manager_service.assign_plan(
        automatic_order.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=1),
    )
    process_service.transition_stage(automatic_order.id, ProcessStage.SURFACE_PREPARATION, StageStatus.IN_PROGRESS)
    process_service.transition_stage(automatic_order.id, ProcessStage.SURFACE_PREPARATION, StageStatus.DONE)
    process_service.transition_stage(automatic_order.id, ProcessStage.HANGING, StageStatus.IN_PROGRESS)
    before_finish = process_repository.get_work_order_with_stage_states(automatic_order.id)
    assert before_finish is not None
    assert process_service.is_visible_in_stage(before_finish, ProcessStage.PRODUCTION, ProductionType.AUTOMATIC) is True
    production_state_before_finish = next(stage for stage in before_finish.stage_states if stage.stage == ProcessStage.PRODUCTION)
    assert production_state_before_finish.status == StageStatus.NOT_STARTED

    process_service.finish_stage(automatic_order.id, ProcessStage.HANGING)
    work_order = process_repository.get_work_order_with_stage_states(automatic_order.id)

    assert work_order is not None
    production_state = next(stage for stage in work_order.stage_states if stage.stage == ProcessStage.PRODUCTION)
    assert production_state.status == StageStatus.IN_PROGRESS


def test_automatic_hanging_finish_marks_hanging_done(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, _ = build_services(db_session)

    automatic_order = create_ral_work_order(work_order_service, "Automatic hanging blocked")
    manager_service.assign_plan(
        automatic_order.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=1),
    )
    process_service.transition_stage(automatic_order.id, ProcessStage.SURFACE_PREPARATION, StageStatus.IN_PROGRESS)
    process_service.transition_stage(automatic_order.id, ProcessStage.SURFACE_PREPARATION, StageStatus.DONE)
    process_service.transition_stage(automatic_order.id, ProcessStage.HANGING, StageStatus.IN_PROGRESS)

    response = process_service.finish_stage(automatic_order.id, ProcessStage.HANGING)

    assert response.stage_status.stage == ProcessStage.HANGING
    assert response.stage_status.status.value == StageStatus.DONE


def test_automatic_hanging_finish_recovers_from_stale_automatic_line_lock(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    automatic_order = create_ral_work_order(work_order_service, "Automatic stale line lock")
    stale_owner = create_ral_work_order(work_order_service, "Stale line lock owner")
    manager_service.assign_plan(
        automatic_order.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=1),
    )
    manager_service.assign_plan(
        stale_owner.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=2),
    )
    process_service.transition_stage(automatic_order.id, ProcessStage.SURFACE_PREPARATION, StageStatus.IN_PROGRESS)
    process_service.transition_stage(automatic_order.id, ProcessStage.SURFACE_PREPARATION, StageStatus.DONE)
    process_service.transition_stage(automatic_order.id, ProcessStage.HANGING, StageStatus.IN_PROGRESS)

    process_repository.acquire_resource_lock("AUTOMATIC_LINE", stale_owner.id)

    response = process_service.finish_stage(automatic_order.id, ProcessStage.HANGING)
    refreshed_lock = process_repository.get_resource_lock("AUTOMATIC_LINE")

    assert response.stage_status.stage == ProcessStage.HANGING
    assert response.stage_status.status.value == StageStatus.DONE
    assert refreshed_lock is not None
    assert refreshed_lock.work_order_id == automatic_order.id


def test_decoral_path_goes_after_packing_for_manual_orders(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    created = work_order_service.create_work_order(
        build_work_order_create(title="Decoral manual path", coating_type=CoatingType.DECORAL, total_quantity=100)
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

    response = complete_packing(process_service, created.id, ok_quantity=100, correction_quantity=0)
    work_order = process_repository.get_work_order_with_stage_states(created.id)

    assert response.stage_status.stage == ProcessStage.DECORAL_PRODUCTION
    assert work_order is not None
    assert work_order.completed_quantity == 0
    assert work_order.current_active_quantity == 100
    assert process_service.get_display_status(work_order).value == "DECORAL_PRODUCTION"


# docs/WORKFLOW.md scenario S03 (DECORAL + MANUAL + none)
def test_decoral_production_finishes_order(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    created = work_order_service.create_work_order(
        build_work_order_create(title="Decoral finish", coating_type=CoatingType.DECORAL, total_quantity=100)
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
    complete_packing(process_service, created.id, ok_quantity=100, correction_quantity=0)
    process_service.transition_stage(created.id, ProcessStage.DECORAL_PRODUCTION, StageStatus.IN_PROGRESS)
    process_service.finish_stage(created.id, ProcessStage.DECORAL_PRODUCTION)
    work_order = process_repository.get_work_order_with_stage_states(created.id)

    assert work_order is not None
    assert work_order.completed_quantity == 100
    assert work_order.current_active_quantity == 0
    assert process_service.get_display_status(work_order).value == "READY"


def test_automatic_production_preview_cannot_be_started_directly(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, _ = build_services(db_session)

    automatic_order = create_ral_work_order(work_order_service, "Automatic preview")
    manager_service.assign_plan(
        automatic_order.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=1),
    )
    advance_to_production(process_service, automatic_order.id)

    with pytest.raises(InvalidProcessStageTransitionError) as exc_info:
        process_service.start_stage(automatic_order.id, ProcessStage.PRODUCTION)

    assert str(exc_info.value) == ProcessService.AUTOMATIC_PRODUCTION_MANUAL_ACTION_ERROR


def test_corrections_reset_order_to_unplanned_state(db_session: Session) -> None:
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
    complete_packing(process_service, manual_order.id, ok_quantity=90, correction_quantity=10)
    complete_packing(process_service, automatic_order.id, ok_quantity=90, correction_quantity=10)
    manual_work_order = process_repository.get_work_order_with_stage_states(manual_order.id)
    automatic_work_order = process_repository.get_work_order_with_stage_states(automatic_order.id)

    assert manual_work_order is not None
    assert automatic_work_order is not None
    assert manual_work_order.completed_quantity == 90
    assert automatic_work_order.completed_quantity == 90
    assert manual_work_order.current_active_quantity == 10
    assert automatic_work_order.current_active_quantity == 10
    assert process_service.get_display_status(manual_work_order).value == "TO_BE_PLANNED"
    assert process_service.get_display_status(automatic_work_order).value == "TO_BE_PLANNED"
    assert manual_work_order.production_type is None
    assert automatic_work_order.production_type is None
    assert process_service.is_visible_in_stage(manual_work_order, ProcessStage.PRODUCTION, ProductionType.MANUAL) is False
    assert process_service.is_visible_in_stage(automatic_work_order, ProcessStage.HANGING) is False


def test_decoral_automatic_mixed_split_waits_for_correction_child(db_session: Session) -> None:
    work_order_service, process_service, manager_service, work_order_repository, process_repository = build_services(db_session)

    created = work_order_service.create_work_order(
        build_work_order_create(title="Decoral automatic parallel", coating_type=CoatingType.DECORAL, total_quantity=10)
    )
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=1),
    )
    advance_to_packing(process_service, created.id)

    complete_packing(
        process_service,
        created.id,
        ok_quantity=7,
        correction_quantity=3,
        correction_reason_category="za grubo",
        correction_reason_note="pomiar na końcu partii",
    )

    work_order = process_repository.get_work_order_with_stage_states(created.id)
    hanging_rows = process_service.list_stage_work_orders(ProcessStage.HANGING)
    decoral_rows = process_service.list_stage_work_orders(ProcessStage.DECORAL_PRODUCTION)
    correction_orders = [work_order for work_order in work_order_repository.list(limit=20, offset=0) if work_order.is_correction]

    assert work_order is not None
    active_batches = [batch for batch in work_order.quantity_batches if batch.is_active]
    assert len(active_batches) == 1
    assert active_batches[0].current_stage == ProcessStage.DECORAL_PRODUCTION
    assert active_batches[0].quantity == 7
    assert hanging_rows == []
    assert [item.id for item in decoral_rows] == [created.id]
    assert process_service.get_display_status(work_order).value == "DECORAL_PRODUCTION"
    assert process_service.get_waiting_ok_quantity(work_order) == 7
    assert len(correction_orders) == 1
    assert correction_orders[0].parent_order_id == created.id
    assert correction_orders[0].total_quantity == 3
    assert correction_orders[0].correction_reason_category == "za grubo"
    assert correction_orders[0].correction_reason_note == "pomiar na końcu partii"


def test_station_and_correction_rows_derive_profile_accessory_quantities_from_operational_quantity(
    db_session: Session,
) -> None:
    work_order_service, process_service, manager_service, work_order_repository, _ = build_services(db_session)

    created = work_order_service.create_work_order(
        WorkOrderCreate(
            title="Correction category quantities",
            coating_type=CoatingType.DECORAL,
            total_quantity=10,
            customer_name="ACME",
            ral_code="RAL 7016",
            paint_code="P-7016",
            paint_producer="AkzoNobel",
            received_date="2026-05-25",
            total_area_m2=5.0,
            profiles_quantity=10,
            profiles_to_count=False,
            accessories_quantity=0,
            accessories_to_count=False,
        )
    )
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)

    complete_packing(process_service, created.id, ok_quantity=7, correction_quantity=3)

    decoral_rows = process_service.list_stage_work_orders(ProcessStage.DECORAL_PRODUCTION)
    correction_orders = [work_order for work_order in work_order_repository.list(limit=20, offset=0) if work_order.is_correction]

    assert [row.id for row in decoral_rows] == [created.id]
    assert decoral_rows[0].profiles_quantity == 7
    assert decoral_rows[0].profiles_to_count is False
    assert decoral_rows[0].accessories_quantity == 0
    assert decoral_rows[0].accessories_to_count is False
    assert len(correction_orders) == 1
    assert correction_orders[0].total_quantity == 3
    assert correction_orders[0].profiles_quantity == 3
    assert correction_orders[0].profiles_to_count is False
    assert correction_orders[0].accessories_quantity == 0
    assert correction_orders[0].accessories_to_count is False


def test_mixed_profile_accessory_partial_rows_preserve_explicit_correction_category_split(
    db_session: Session,
) -> None:
    work_order_service, process_service, manager_service, work_order_repository, _ = build_services(db_session)

    created = work_order_service.create_work_order(
        WorkOrderCreate(
            title="Mixed category correction quantities",
            coating_type=CoatingType.DECORAL,
            total_quantity=10,
            customer_name="ACME",
            ral_code="RAL 7016",
            paint_code="P-7016",
            paint_producer="AkzoNobel",
            received_date="2026-05-25",
            total_area_m2=5.0,
            profiles_quantity=8,
            profiles_to_count=False,
            accessories_quantity=2,
            accessories_to_count=False,
        )
    )
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)

    complete_packing(
        process_service,
        created.id,
        ok_quantity=7,
        correction_quantity=3,
        correction_profiles_quantity=1,
        correction_accessories_quantity=2,
    )

    decoral_rows = process_service.list_stage_work_orders(ProcessStage.DECORAL_PRODUCTION)
    correction_orders = [work_order for work_order in work_order_repository.list(limit=20, offset=0) if work_order.is_correction]

    assert [row.id for row in decoral_rows] == [created.id]
    assert decoral_rows[0].profiles_quantity is None
    assert decoral_rows[0].profiles_to_count is True
    assert decoral_rows[0].accessories_quantity is None
    assert decoral_rows[0].accessories_to_count is True
    assert len(correction_orders) == 1
    assert correction_orders[0].total_quantity == 3
    assert correction_orders[0].profiles_quantity == 1
    assert correction_orders[0].profiles_to_count is False
    assert correction_orders[0].accessories_quantity == 2
    assert correction_orders[0].accessories_to_count is False


def test_decoral_split_moves_ok_quantity_to_decoral_and_child_to_painting_flow(db_session: Session) -> None:
    work_order_service, process_service, manager_service, work_order_repository, process_repository = build_services(db_session)

    created = work_order_service.create_work_order(
        build_work_order_create(title="Decoral split route", coating_type=CoatingType.DECORAL, total_quantity=10)
    )
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)

    response = complete_packing(process_service, created.id, ok_quantity=7, correction_quantity=3)

    parent = process_repository.get_work_order_with_stage_states(created.id)
    correction_order = next(work_order for work_order in work_order_repository.list(limit=20, offset=0) if work_order.is_correction)

    assert parent is not None
    assert response.stage_status.stage == ProcessStage.DECORAL_PRODUCTION
    assert response.batch_id is not None
    assert process_service.get_display_status(parent).value == "DECORAL_PRODUCTION"
    assert [item.id for item in process_service.list_stage_work_orders(ProcessStage.DECORAL_PRODUCTION)] == [created.id]

    manager_service.assign_plan(
        correction_order.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=2),
    )
    planned_correction = process_repository.get_work_order_with_stage_states(correction_order.id)

    assert planned_correction is not None
    assert process_service.get_display_status(planned_correction).value == "PRODUCTION_MANUAL"
    stage_states = {stage_state.stage: stage_state.status for stage_state in planned_correction.stage_states}
    assert stage_states[ProcessStage.SURFACE_PREPARATION] == StageStatus.DONE
    assert stage_states[ProcessStage.PRODUCTION] == StageStatus.NOT_STARTED


def test_correction_round_cannot_enter_surface_preparation(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    created = create_ral_work_order(work_order_service, "Correction skips surface prep")
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)
    complete_packing(process_service, created.id, ok_quantity=90, correction_quantity=10)
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )

    with pytest.raises(InvalidProcessStageTransitionError) as exc_info:
        process_service.start_stage(created.id, ProcessStage.SURFACE_PREPARATION, counted_quantity=10)

    planned_correction = process_repository.get_work_order_with_stage_states(created.id)
    assert str(exc_info.value) == "Correction rounds do not go through surface preparation."
    assert planned_correction is not None
    stage_states = {stage_state.stage: stage_state.status for stage_state in planned_correction.stage_states}
    assert stage_states[ProcessStage.SURFACE_PREPARATION] == StageStatus.DONE
    assert stage_states[ProcessStage.PRODUCTION] == StageStatus.NOT_STARTED


def test_decoral_parent_stays_not_ready_when_ok_decoral_finishes_but_correction_is_open(db_session: Session) -> None:
    work_order_service, process_service, manager_service, work_order_repository, process_repository = build_services(db_session)

    created = work_order_service.create_work_order(
        build_work_order_create(title="Decoral parent waits", coating_type=CoatingType.DECORAL, total_quantity=10)
    )
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)

    response = complete_packing(process_service, created.id, ok_quantity=7, correction_quantity=3)
    correction_order = next(work_order for work_order in work_order_repository.list(limit=20, offset=0) if work_order.is_correction)
    manager_service.assign_plan(
        correction_order.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=2),
    )

    process_service.start_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=response.batch_id)
    process_service.finish_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=response.batch_id)

    parent = process_repository.get_work_order_with_stage_states(created.id)

    assert parent is not None
    assert parent.completed_quantity == 7
    assert process_service.get_display_status(parent).value == "WAITING_FOR_CORRECTIONS"


def test_decoral_parent_becomes_ready_after_ok_decoral_and_correction_merge(db_session: Session) -> None:
    work_order_service, process_service, manager_service, work_order_repository, process_repository = build_services(db_session)

    created = work_order_service.create_work_order(
        build_work_order_create(title="Decoral split merge", coating_type=CoatingType.DECORAL, total_quantity=10)
    )
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)

    response = complete_packing(process_service, created.id, ok_quantity=7, correction_quantity=3)
    correction_order = next(work_order for work_order in work_order_repository.list(limit=20, offset=0) if work_order.is_correction)
    manager_service.assign_plan(
        correction_order.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=2),
    )

    process_service.start_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=response.batch_id)
    process_service.finish_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=response.batch_id)

    process_service.start_stage(correction_order.id, ProcessStage.PRODUCTION)
    process_service.finish_stage(correction_order.id, ProcessStage.PRODUCTION)
    process_service.start_stage(correction_order.id, ProcessStage.PACKING)
    process_service.complete_packing(
        correction_order.id,
        counted_quantity=3,
        ok_quantity=3,
        correction_quantity=0,
    )
    process_service.start_stage(correction_order.id, ProcessStage.DECORAL_PRODUCTION)
    process_service.finish_stage(correction_order.id, ProcessStage.DECORAL_PRODUCTION)

    parent = process_repository.get_work_order_with_stage_states(created.id)

    assert parent is not None
    assert parent.completed_quantity == 10
    assert process_service.get_display_status(parent).value == "READY"


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


def test_incomplete_order_cannot_be_forced_into_stage_queue_by_direct_update(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    visible_order = create_ral_work_order(work_order_service, "Visible planned")
    incomplete_order = work_order_service.create_work_order(
        build_work_order_create(title="Incomplete planned", coating_type=CoatingType.RAL, total_quantity=100).model_copy(
            update={"is_incomplete_on_arrival": True}
        )
    )

    manager_service.assign_plan(
        visible_order.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )

    persisted_incomplete = process_repository.get_work_order_with_stage_states(incomplete_order.id)
    assert persisted_incomplete is not None
    persisted_incomplete.production_type = ProductionType.MANUAL
    persisted_incomplete.queue_position = 2

    with pytest.raises(IntegrityError):
        process_repository.commit()
    process_repository.rollback()

    visible = process_service.list_visible_work_orders(ProcessStage.SURFACE_PREPARATION)

    assert [work_order.id for work_order in visible] == [visible_order.id]


def test_complete_packing_splits_ok_and_correction_quantities(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    created = create_ral_work_order(work_order_service, "Split packing")
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)

    response = complete_packing(process_service, created.id, ok_quantity=90, correction_quantity=10)
    work_order = process_repository.get_work_order_with_stage_states(created.id)

    assert response.stage_status.stage == ProcessStage.PACKING
    assert work_order is not None
    assert work_order.completed_quantity == 90
    assert work_order.total_quantity == 100
    assert work_order.current_active_quantity == 10
    assert len(work_order.quantity_batches) == 2
    assert process_service.get_display_status(work_order).value == "TO_BE_PLANNED"
    assert work_order.production_type is None
    assert work_order.queue_position is None

    stage_states = {stage_state.stage: stage_state.status for stage_state in work_order.stage_states}
    assert stage_states[ProcessStage.SURFACE_PREPARATION] == StageStatus.DONE
    assert stage_states[ProcessStage.HANGING] == StageStatus.NOT_STARTED
    assert stage_states[ProcessStage.PRODUCTION] == StageStatus.NOT_STARTED
    assert stage_states[ProcessStage.PACKING] == StageStatus.NOT_STARTED


# docs/WORKFLOW.md scenario S01 (RAL + MANUAL + none)
def test_complete_packing_full_ok_marks_work_order_ready(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    created = create_ral_work_order(work_order_service, "Full ok")
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)

    response = complete_packing(process_service, created.id, ok_quantity=100, correction_quantity=0)
    work_order = process_repository.get_work_order_with_stage_states(created.id)

    assert response.stage_status.stage == ProcessStage.PACKING
    assert work_order is not None
    assert work_order.completed_quantity == 100
    assert work_order.current_active_quantity == 0
    assert process_service.get_display_status(work_order).value == "READY"


def test_complete_packing_full_correction_resets_order_to_planning(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    created = create_ral_work_order(work_order_service, "Full correction")
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)

    response = complete_packing(process_service, created.id, ok_quantity=0, correction_quantity=100)
    work_order = process_repository.get_work_order_with_stage_states(created.id)

    assert response.stage_status.stage == ProcessStage.PACKING
    assert work_order is not None
    assert work_order.completed_quantity == 0
    assert work_order.total_quantity == 100
    assert work_order.current_active_quantity == 100
    assert len(work_order.quantity_batches) == 2
    assert process_service.get_display_status(work_order).value == "TO_BE_PLANNED"
    assert work_order.production_type is None
    assert work_order.queue_position is None


def test_multiple_packing_correction_rounds_accumulate_on_same_order(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    created = create_ral_work_order(work_order_service, "Multiple corrections")
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)
    complete_packing(process_service, created.id, ok_quantity=70, correction_quantity=30)

    # Re-plan for second correction round
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=2),
    )
    advance_to_packing(process_service, created.id)
    complete_packing(process_service, created.id, ok_quantity=20, correction_quantity=10)

    work_order = process_repository.get_work_order_with_stage_states(created.id)

    assert work_order is not None
    assert work_order.completed_quantity == 90
    assert work_order.total_quantity == 100
    assert work_order.current_active_quantity == 10
    assert len(work_order.quantity_batches) == 3
    assert process_service.get_display_status(work_order).value == "TO_BE_PLANNED"


# docs/WORKFLOW.md scenario S05 (RAL + MANUAL + correction after packing)
def test_completed_ral_correction_round_finalizes_order(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    created = work_order_service.create_work_order(
        build_work_order_create(title="RAL correction merge", coating_type=CoatingType.RAL, total_quantity=10)
    )
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)
    complete_packing(process_service, created.id, ok_quantity=7, correction_quantity=3)

    work_order = process_repository.get_work_order_with_stage_states(created.id)
    assert work_order is not None
    assert work_order.completed_quantity == 7
    assert process_service.get_display_status(work_order).value == "TO_BE_PLANNED"

    # Re-plan parent for correction round
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=2),
    )
    advance_to_packing(process_service, created.id)
    complete_packing(process_service, created.id, ok_quantity=3, correction_quantity=0)

    final_work_order = process_repository.get_work_order_with_stage_states(created.id)

    assert final_work_order is not None
    assert final_work_order.completed_quantity == 10
    assert final_work_order.total_quantity == 10
    assert process_service.get_display_status(final_work_order).value == "READY"


# docs/WORKFLOW.md scenario S09 (RAL + MANUAL + multi-round correction)
def test_multi_round_ral_correction_cycles_on_same_order_until_ready(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    created = work_order_service.create_work_order(
        build_work_order_create(title="RAL multi-round correction merge", coating_type=CoatingType.RAL, total_quantity=10)
    )
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)
    complete_packing(process_service, created.id, ok_quantity=7, correction_quantity=3)

    work_order = process_repository.get_work_order_with_stage_states(created.id)
    assert work_order.completed_quantity == 7
    assert work_order.current_active_quantity == 3
    assert process_service.get_display_status(work_order).value == "TO_BE_PLANNED"

    # Round 2
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=2),
    )
    advance_to_packing(process_service, created.id)
    complete_packing(process_service, created.id, ok_quantity=2, correction_quantity=1)

    work_order = process_repository.get_work_order_with_stage_states(created.id)
    assert work_order.completed_quantity == 9
    assert work_order.current_active_quantity == 1
    assert process_service.get_display_status(work_order).value == "TO_BE_PLANNED"

    # Round 3 - final
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=3),
    )
    advance_to_packing(process_service, created.id)
    complete_packing(process_service, created.id, ok_quantity=1, correction_quantity=0)

    final = process_repository.get_work_order_with_stage_states(created.id)
    assert final is not None
    assert process_service.get_display_status(final).value == "READY"
    assert final.completed_quantity == 10
    assert final.current_active_quantity == 0


# docs/WORKFLOW.md scenario S07 (DECORAL + MANUAL + correction after packing)
def test_completed_decoral_correction_child_merges_back_into_parent(db_session: Session) -> None:
    work_order_service, process_service, manager_service, work_order_repository, process_repository = build_services(db_session)

    created = work_order_service.create_work_order(
        build_work_order_create(title="Decoral correction merge", coating_type=CoatingType.DECORAL, total_quantity=10)
    )
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)
    complete_packing(process_service, created.id, ok_quantity=7, correction_quantity=3)

    parent_work_order = process_repository.get_work_order_with_stage_states(created.id)
    correction_order = next(work_order for work_order in work_order_repository.list(limit=20, offset=0) if work_order.is_correction)

    assert parent_work_order is not None
    assert process_service.get_display_status(parent_work_order).value == "DECORAL_PRODUCTION"
    assert [item.id for item in process_service.list_stage_work_orders(ProcessStage.DECORAL_PRODUCTION)] == [created.id]

    manager_service.assign_plan(
        correction_order.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=2),
    )
    decoral_batch = next(
        item.batch_id for item in process_service.list_stage_work_orders(ProcessStage.DECORAL_PRODUCTION) if item.id == created.id
    )
    process_service.start_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=decoral_batch)
    process_service.finish_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=decoral_batch)
    process_service.start_stage(correction_order.id, ProcessStage.PRODUCTION)
    process_service.finish_stage(correction_order.id, ProcessStage.PRODUCTION)
    process_service.start_stage(correction_order.id, ProcessStage.PACKING)
    complete_packing(process_service, correction_order.id, ok_quantity=3, correction_quantity=0)
    process_service.start_stage(correction_order.id, ProcessStage.DECORAL_PRODUCTION)
    process_service.finish_stage(correction_order.id, ProcessStage.DECORAL_PRODUCTION)

    merged_parent = process_repository.get_work_order_with_stage_states(created.id)
    completed_correction = process_repository.get_work_order_with_stage_states(correction_order.id)

    assert merged_parent is not None
    assert completed_correction is not None
    assert merged_parent.completed_quantity == 10
    assert process_service.get_display_status(merged_parent).value == "READY"
    assert completed_correction.parent_order_id == created.id


def test_fully_packed_order_cannot_reopen_any_stage(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, _ = build_services(db_session)

    created = create_ral_work_order(work_order_service, "No reopen after full pack")
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)
    complete_packing(process_service, created.id, ok_quantity=100, correction_quantity=0)

    with pytest.raises(InvalidProcessStageTransitionError) as exc_info:
        process_service.reopen_stage(created.id, ProcessStage.PACKING)

    assert str(exc_info.value) == "Cannot reopen process stages because the work order has no active quantity remaining."


def test_order_in_correction_round_cannot_reopen_stages_before_replanning(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    created = create_ral_work_order(work_order_service, "Correction continues workflow")
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)
    complete_packing(process_service, created.id, ok_quantity=80, correction_quantity=20)

    work_order = process_repository.get_work_order_with_stage_states(created.id)

    assert work_order is not None
    assert work_order.current_active_quantity == 20

    with pytest.raises(InvalidProcessStageTransitionError) as exc_info:
        process_service.reopen_stage(created.id, ProcessStage.PRODUCTION)

    assert "Cannot reopen stage PRODUCTION from NOT_STARTED" in str(exc_info.value)


def test_duplicate_packing_completion_is_idempotent_and_does_not_create_second_correction_batch(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    created = create_ral_work_order(work_order_service, "Duplicate packing completion")
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)

    first_response = complete_packing(process_service, created.id, ok_quantity=90, correction_quantity=10)
    second_response = complete_packing(process_service, created.id, ok_quantity=90, correction_quantity=10)

    parent = process_repository.get_work_order_with_stage_states(created.id)

    assert first_response.stage_status.stage == ProcessStage.PACKING
    assert second_response.stage_status.stage == ProcessStage.PACKING
    assert parent is not None
    assert parent.completed_quantity == 90
    assert parent.current_active_quantity == 10
    assert len(parent.quantity_batches) == 2


def test_duplicate_decoral_stage_finish_is_idempotent_and_does_not_double_apply_quantity(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    created = work_order_service.create_work_order(
        build_work_order_create(title="Duplicate decoral finish", coating_type=CoatingType.DECORAL, total_quantity=10)
    )
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)
    complete_packing(process_service, created.id, ok_quantity=10, correction_quantity=0)

    process_service.start_stage(created.id, ProcessStage.DECORAL_PRODUCTION)
    first_response = process_service.finish_stage(created.id, ProcessStage.DECORAL_PRODUCTION)
    second_response = process_service.finish_stage(created.id, ProcessStage.DECORAL_PRODUCTION)
    work_order = process_repository.get_work_order_with_stage_states(created.id)

    assert first_response.stage_status.stage == ProcessStage.DECORAL_PRODUCTION
    assert second_response.stage_status.stage == ProcessStage.DECORAL_PRODUCTION
    assert work_order is not None
    assert work_order.completed_quantity == 10
    assert work_order.current_active_quantity == 0
    assert process_service.get_display_status(work_order).value == "READY"


def test_repeated_packing_completion_does_not_create_duplicate_correction_batch(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    created = create_ral_work_order(work_order_service, "Repeated correction split")
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)

    complete_packing(process_service, created.id, ok_quantity=80, correction_quantity=20)
    complete_packing(process_service, created.id, ok_quantity=80, correction_quantity=20)

    work_order = process_repository.get_work_order_with_stage_states(created.id)

    assert len(work_order.quantity_batches) == 2
    active_batches = [b for b in work_order.quantity_batches if b.is_active]
    assert len(active_batches) == 1
    assert active_batches[0].quantity == 20


def test_parallel_packing_completion_is_serialized_and_does_not_duplicate_child_creation(tmp_path) -> None:
    database_path = tmp_path / "parallel_process_actions.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    Base.metadata.create_all(bind=engine)

    try:
        setup_session = session_factory()
        try:
            work_order_service, process_service, manager_service, _, _ = build_services(setup_session)
            created = create_ral_work_order(work_order_service, "Parallel packing completion")
            manager_service.assign_plan(
                created.id,
                WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
            )
            advance_to_packing(process_service, created.id)
        finally:
            setup_session.close()

        def run_completion():
            session = session_factory()
            try:
                process_service = ProcessService(ProcessRepository(session))
                return complete_packing(process_service, created.id, ok_quantity=85, correction_quantity=15)
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            first_future = executor.submit(run_completion)
            second_future = executor.submit(run_completion)
            first_response = first_future.result()
            second_response = second_future.result()

        verify_session = session_factory()
        try:
            process_repository = ProcessRepository(verify_session)
            parent = process_repository.get_work_order_with_stage_states(created.id)
        finally:
            verify_session.close()
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

    assert first_response.stage_status.stage == ProcessStage.PACKING
    assert second_response.stage_status.stage == ProcessStage.PACKING
    assert parent is not None
    assert parent.completed_quantity == 85
    assert parent.current_active_quantity == 15
    assert len(parent.quantity_batches) == 2


def test_parallel_automatic_hanging_start_allows_only_one_order_to_acquire_hanging(tmp_path) -> None:
    database_path = tmp_path / "parallel_hanging_resource.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    Base.metadata.create_all(bind=engine)

    try:
        setup_session = session_factory()
        try:
            work_order_service, process_service, manager_service, _, process_repository = build_services(setup_session)
            first = create_ral_work_order(work_order_service, "Automatic line parallel A")
            second = create_ral_work_order(work_order_service, "Automatic line parallel B")
            manager_service.assign_plan(
                first.id,
                WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=1),
            )
            manager_service.assign_plan(
                second.id,
                WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=2),
            )
            process_service.transition_stage(first.id, ProcessStage.SURFACE_PREPARATION, StageStatus.IN_PROGRESS)
            process_service.transition_stage(first.id, ProcessStage.SURFACE_PREPARATION, StageStatus.DONE)
            process_service.transition_stage(second.id, ProcessStage.SURFACE_PREPARATION, StageStatus.IN_PROGRESS)
            process_service.transition_stage(second.id, ProcessStage.SURFACE_PREPARATION, StageStatus.DONE)
            first_state = next(
                stage_state
                for stage_state in process_repository.get_work_order_with_stage_states(first.id).stage_states
                if stage_state.stage == ProcessStage.HANGING
            )
            second_state = next(
                stage_state
                for stage_state in process_repository.get_work_order_with_stage_states(second.id).stage_states
                if stage_state.stage == ProcessStage.HANGING
            )
            assert first_state.status == StageStatus.NOT_STARTED
            assert second_state.status == StageStatus.NOT_STARTED
        finally:
            setup_session.close()

        def run_start(work_order_id: int):
            session = session_factory()
            try:
                process_service = ProcessService(ProcessRepository(session))
                try:
                    process_service.start_stage(work_order_id, ProcessStage.HANGING)
                    return "started"
                except InvalidProcessStageTransitionError as exc:
                    return str(exc)
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            first_future = executor.submit(run_start, first.id)
            second_future = executor.submit(run_start, second.id)
            results = {first_future.result(), second_future.result()}

        verify_session = session_factory()
        try:
            process_repository = ProcessRepository(verify_session)
            first_order = process_repository.get_work_order_with_stage_states(first.id)
            second_order = process_repository.get_work_order_with_stage_states(second.id)
            resource_locks = verify_session.scalars(select(ProcessResourceLock)).all()
        finally:
            verify_session.close()
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

    assert "started" in results
    assert "Hanging resource is already occupied by another active job." in results
    assert first_order is not None
    assert second_order is not None
    in_progress_ids = {
        work_order.id
        for work_order in (first_order, second_order)
        if next(stage for stage in work_order.stage_states if stage.stage == ProcessStage.HANGING).status == StageStatus.IN_PROGRESS
    }
    assert len(in_progress_ids) == 1
    assert {(lock.resource_key, lock.work_order_id) for lock in resource_locks} == {
        ("HANGING", next(iter(in_progress_ids))),
    }


def test_finished_decoral_tracked_batch_cannot_be_reopened_and_quantities_remain_unchanged(db_session: Session) -> None:
    work_order_service, process_service, manager_service, work_order_repository, process_repository = build_services(db_session)

    created = work_order_service.create_work_order(
        build_work_order_create(title="Reject reopen finished decoral batch", coating_type=CoatingType.DECORAL, total_quantity=10)
    )
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)
    response = complete_packing(process_service, created.id, ok_quantity=7, correction_quantity=3)

    process_service.start_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=response.batch_id)
    process_service.finish_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=response.batch_id)

    before_parent = process_repository.get_work_order_with_stage_states(created.id)
    correction_order = next(work_order for work_order in work_order_repository.list(limit=20, offset=0) if work_order.is_correction)

    assert before_parent is not None

    with pytest.raises(InvalidProcessStageTransitionError) as exc_info:
        process_service.reopen_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=response.batch_id)

    after_parent = process_repository.get_work_order_with_stage_states(created.id)
    after_correction = process_repository.get_work_order_with_stage_states(correction_order.id)

    assert str(exc_info.value) == "Finished tracked batches cannot be reopened."
    assert after_parent is not None
    assert after_correction is not None
    assert after_parent.completed_quantity == before_parent.completed_quantity == 7
    assert after_parent.current_active_quantity == before_parent.current_active_quantity == 0
    assert process_service.get_display_status(after_parent).value == process_service.get_display_status(before_parent).value
    assert after_correction.parent_order_id == created.id


def test_finished_correction_child_tracked_batch_cannot_be_reopened_and_parent_ready_remains_unchanged(db_session: Session) -> None:
    work_order_service, process_service, manager_service, work_order_repository, process_repository = build_services(db_session)

    created = work_order_service.create_work_order(
        build_work_order_create(title="Reject reopen finished correction child batch", coating_type=CoatingType.DECORAL, total_quantity=10)
    )
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)
    root_response = complete_packing(process_service, created.id, ok_quantity=7, correction_quantity=3)

    first_correction = next(work_order for work_order in work_order_repository.list(limit=20, offset=0) if work_order.is_correction)
    manager_service.assign_plan(
        first_correction.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=2),
    )
    process_service.start_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=root_response.batch_id)
    process_service.finish_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=root_response.batch_id)

    advance_to_packing(process_service, first_correction.id)
    first_child_response = complete_packing(process_service, first_correction.id, ok_quantity=2, correction_quantity=1)

    second_correction = next(
        work_order
        for work_order in work_order_repository.list(limit=20, offset=0)
        if work_order.is_correction and work_order.parent_order_id == first_correction.id
    )
    manager_service.assign_plan(
        second_correction.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=3),
    )
    process_service.start_stage(first_correction.id, ProcessStage.DECORAL_PRODUCTION, batch_id=first_child_response.batch_id)
    process_service.finish_stage(first_correction.id, ProcessStage.DECORAL_PRODUCTION, batch_id=first_child_response.batch_id)

    advance_to_packing(process_service, second_correction.id)
    complete_packing(process_service, second_correction.id, ok_quantity=1, correction_quantity=0)
    process_service.transition_stage(second_correction.id, ProcessStage.DECORAL_PRODUCTION, StageStatus.IN_PROGRESS)
    process_service.finish_stage(second_correction.id, ProcessStage.DECORAL_PRODUCTION)

    before_parent = process_repository.get_work_order_with_stage_states(created.id)
    before_child = process_repository.get_work_order_with_stage_states(first_correction.id)

    assert before_parent is not None
    assert before_child is not None
    assert process_service.get_display_status(before_parent).value == "READY"

    with pytest.raises(InvalidProcessStageTransitionError) as exc_info:
        process_service.reopen_stage(first_correction.id, ProcessStage.DECORAL_PRODUCTION, batch_id=first_child_response.batch_id)

    after_parent = process_repository.get_work_order_with_stage_states(created.id)
    after_child = process_repository.get_work_order_with_stage_states(first_correction.id)

    assert str(exc_info.value) == "Finished tracked batches cannot be reopened."
    assert after_parent is not None
    assert after_child is not None
    assert after_parent.completed_quantity == before_parent.completed_quantity == 10
    assert after_parent.current_active_quantity == before_parent.current_active_quantity == 0
    assert process_service.get_display_status(after_parent).value == "READY"
    assert process_service.get_display_status(after_child).value == process_service.get_display_status(before_child).value
    assert after_child.completed_quantity == before_child.completed_quantity
    assert after_child.current_active_quantity == before_child.current_active_quantity


def test_incomplete_quantity_never_displays_as_ready(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    created = create_ral_work_order(work_order_service, "Legacy incomplete quantity")
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    work_order = process_repository.get_work_order_with_stage_states(created.id)

    assert work_order is not None

    work_order.completed_quantity = 96
    work_order.current_active_batch_id = None
    for batch in work_order.quantity_batches:
        batch.is_active = False

    process_repository.commit()

    refreshed = process_repository.get_work_order_with_stage_states(created.id)

    assert refreshed is not None
    assert process_service.get_display_status(refreshed).value != "READY"


def test_read_model_status_is_derived_even_if_stored_status_drifts(db_session: Session) -> None:
    work_order_service, _, _, work_order_repository, _ = build_services(db_session)

    created = create_ral_work_order(work_order_service, "Status drift ignored")
    stored = work_order_repository.get_by_id(created.id)

    assert stored is not None

    stored.status = WorkOrderStatus.FINISHED
    work_order_repository.commit()

    refreshed = work_order_service.get_work_order(created.id)

    assert refreshed.process_status.value == "TO_BE_PLANNED"
    assert refreshed.status.value == WorkOrderStatus.ENTERED


def test_incomplete_marker_cannot_be_forced_into_manager_or_stage_views(db_session: Session) -> None:
    work_order_service, process_service, manager_service, work_order_repository, _ = build_services(db_session)

    visible_order = create_ral_work_order(work_order_service, "Visible planned manager")
    hidden_order = work_order_service.create_work_order(
        build_work_order_create(title="Hidden incomplete manager", coating_type=CoatingType.RAL, total_quantity=100).model_copy(
            update={"is_incomplete_on_arrival": True}
        )
    )

    manager_service.assign_plan(
        visible_order.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )

    stored = work_order_repository.get_by_id(hidden_order.id)
    assert stored is not None
    stored.production_type = ProductionType.MANUAL
    stored.queue_position = 2

    with pytest.raises(IntegrityError):
        work_order_repository.commit()
    work_order_repository.rollback()

    planned_ids = [item.id for item in manager_service.list_planned_work_orders()]
    stage_ids = [item.id for item in process_service.list_stage_work_orders(ProcessStage.SURFACE_PREPARATION)]

    assert visible_order.id in planned_ids
    assert hidden_order.id not in planned_ids
    assert hidden_order.id not in stage_ids


def test_inconsistent_incomplete_row_cannot_be_planned(db_session: Session) -> None:
    work_order_service, _, manager_service, work_order_repository, _ = build_services(db_session)

    created = work_order_service.create_work_order(
        build_work_order_create(title="Inconsistent incomplete planning")
    )
    stored = work_order_repository.get_by_id(created.id)

    assert stored is not None

    stored.status = WorkOrderStatus.INCOMPLETE
    stored.is_incomplete_on_arrival = False
    work_order_repository.commit()

    with pytest.raises(InvalidManagerPlanningError) as exc_info:
        manager_service.assign_plan(
            created.id,
            WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
        )

    assert str(exc_info.value) == "Cannot plan incomplete order. Mark as complete first."


def test_planned_row_cannot_be_marked_incomplete_by_direct_update(db_session: Session) -> None:
    work_order_service, process_service, manager_service, work_order_repository, _ = build_services(db_session)

    created = create_ral_work_order(work_order_service, "Inconsistent incomplete stage")
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    stored = work_order_repository.get_by_id(created.id)

    assert stored is not None

    stored.status = WorkOrderStatus.INCOMPLETE
    stored.is_incomplete_on_arrival = False

    with pytest.raises(IntegrityError):
        work_order_repository.commit()
    work_order_repository.rollback()

    visible_ids = [item.id for item in process_service.list_stage_work_orders(ProcessStage.SURFACE_PREPARATION)]

    assert created.id in visible_ids


# docs/WORKFLOW.md scenario S04 (DECORAL + AUTOMATIC + none)
def test_s04_decoral_automatic_no_correction_reaches_ready(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    created = work_order_service.create_work_order(
        build_work_order_create(title="S04 Decoral automatic no correction", coating_type=CoatingType.DECORAL, total_quantity=10)
    )
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=1),
    )

    advance_to_packing(process_service, created.id)
    complete_packing(process_service, created.id, ok_quantity=10, correction_quantity=0)
    process_service.transition_stage(created.id, ProcessStage.DECORAL_PRODUCTION, StageStatus.IN_PROGRESS)
    process_service.finish_stage(created.id, ProcessStage.DECORAL_PRODUCTION)

    work_order = process_repository.get_work_order_with_stage_states(created.id)

    assert work_order is not None
    assert process_service.get_display_status(work_order).value == "READY"
    assert work_order.completed_quantity == 10
    assert work_order.current_active_quantity == 0


# docs/WORKFLOW.md scenario S08 (DECORAL + AUTOMATIC + correction after packing)
def test_s08_decoral_automatic_correction_split_and_merge(db_session: Session) -> None:
    work_order_service, process_service, manager_service, work_order_repository, process_repository = build_services(db_session)

    created = work_order_service.create_work_order(
        build_work_order_create(title="S08 Decoral automatic correction", coating_type=CoatingType.DECORAL, total_quantity=10)
    )
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=1),
    )

    advance_to_packing(process_service, created.id)
    parent_response = complete_packing(process_service, created.id, ok_quantity=7, correction_quantity=3)
    correction_order = next(
        work_order for work_order in work_order_repository.list(limit=20, offset=0) if work_order.parent_order_id == created.id
    )
    manager_service.assign_plan(
        correction_order.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=2),
    )

    process_service.start_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=parent_response.batch_id)
    process_service.finish_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=parent_response.batch_id)

    advance_to_packing(process_service, correction_order.id)
    complete_packing(process_service, correction_order.id, ok_quantity=3, correction_quantity=0)
    process_service.transition_stage(correction_order.id, ProcessStage.DECORAL_PRODUCTION, StageStatus.IN_PROGRESS)
    process_service.finish_stage(correction_order.id, ProcessStage.DECORAL_PRODUCTION)

    parent_work_order = process_repository.get_work_order_with_stage_states(created.id)
    child_work_order = process_repository.get_work_order_with_stage_states(correction_order.id)

    assert parent_work_order is not None
    assert child_work_order is not None
    assert process_service.get_display_status(parent_work_order).value == "READY"
    assert process_service.get_display_status(child_work_order).value == "READY"
    assert parent_work_order.completed_quantity == parent_work_order.total_quantity
    assert parent_work_order.current_active_quantity == 0
    assert child_work_order.completed_quantity == child_work_order.total_quantity
    assert child_work_order.current_active_quantity == 0


# docs/WORKFLOW.md scenario S10 (RAL + AUTOMATIC + multi-round correction)
def test_s10_ral_automatic_multi_round_correction_cycles_on_same_order(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    created = create_ral_work_order(work_order_service, "S10 RAL automatic multi-round")
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=1),
    )

    advance_to_packing(process_service, created.id)
    complete_packing(process_service, created.id, ok_quantity=70, correction_quantity=30)

    work_order = process_repository.get_work_order_with_stage_states(created.id)
    assert work_order.completed_quantity == 70
    assert work_order.current_active_quantity == 30
    assert process_service.get_display_status(work_order).value == "TO_BE_PLANNED"

    # Round 2 - automatic correction
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=2),
    )
    advance_to_packing(process_service, created.id)
    complete_packing(process_service, created.id, ok_quantity=20, correction_quantity=10)

    work_order = process_repository.get_work_order_with_stage_states(created.id)
    assert work_order.completed_quantity == 90
    assert work_order.current_active_quantity == 10
    assert process_service.get_display_status(work_order).value == "TO_BE_PLANNED"

    # Round 3 - final
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=3),
    )
    advance_to_packing(process_service, created.id)
    complete_packing(process_service, created.id, ok_quantity=10, correction_quantity=0)

    final = process_repository.get_work_order_with_stage_states(created.id)
    assert final is not None
    assert process_service.get_display_status(final).value == "READY"
    assert final.completed_quantity == 100
    assert final.current_active_quantity == 0


# docs/WORKFLOW.md scenario S11 (DECORAL + MANUAL + multi-round correction)
def test_s11_decoral_manual_multi_round_correction_chain_merges(db_session: Session) -> None:
    work_order_service, process_service, manager_service, work_order_repository, process_repository = build_services(db_session)

    created = work_order_service.create_work_order(
        build_work_order_create(title="S11 Decoral manual multi-round", coating_type=CoatingType.DECORAL, total_quantity=10)
    )
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )

    advance_to_packing(process_service, created.id)
    root_response = complete_packing(process_service, created.id, ok_quantity=7, correction_quantity=3)

    first_correction = next(
        work_order for work_order in work_order_repository.list(limit=20, offset=0) if work_order.parent_order_id == created.id
    )
    manager_service.assign_plan(
        first_correction.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=2),
    )

    process_service.start_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=root_response.batch_id)
    process_service.finish_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=root_response.batch_id)

    advance_to_packing(process_service, first_correction.id)
    first_child_response = complete_packing(process_service, first_correction.id, ok_quantity=2, correction_quantity=1)
    process_service.start_stage(first_correction.id, ProcessStage.DECORAL_PRODUCTION, batch_id=first_child_response.batch_id)
    process_service.finish_stage(first_correction.id, ProcessStage.DECORAL_PRODUCTION, batch_id=first_child_response.batch_id)

    second_correction = next(
        work_order
        for work_order in work_order_repository.list(limit=20, offset=0)
        if work_order.parent_order_id == first_correction.id
    )
    manager_service.assign_plan(
        second_correction.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=3),
    )
    advance_to_packing(process_service, second_correction.id)
    complete_packing(process_service, second_correction.id, ok_quantity=1, correction_quantity=0)
    process_service.transition_stage(second_correction.id, ProcessStage.DECORAL_PRODUCTION, StageStatus.IN_PROGRESS)
    process_service.finish_stage(second_correction.id, ProcessStage.DECORAL_PRODUCTION)

    parent_work_order = process_repository.get_work_order_with_stage_states(created.id)
    completed_first_correction = process_repository.get_work_order_with_stage_states(first_correction.id)
    completed_second_correction = process_repository.get_work_order_with_stage_states(second_correction.id)

    assert parent_work_order is not None
    assert completed_first_correction is not None
    assert completed_second_correction is not None
    assert process_service.get_display_status(parent_work_order).value == "READY"
    assert process_service.get_display_status(completed_first_correction).value == "READY"
    assert process_service.get_display_status(completed_second_correction).value == "READY"
    assert parent_work_order.completed_quantity == parent_work_order.total_quantity
    assert parent_work_order.current_active_quantity == 0
    assert completed_first_correction.completed_quantity == completed_first_correction.total_quantity
    assert completed_first_correction.current_active_quantity == 0
    assert completed_second_correction.completed_quantity == completed_second_correction.total_quantity
    assert completed_second_correction.current_active_quantity == 0


# docs/WORKFLOW.md scenario S12 (DECORAL + AUTOMATIC + multi-round correction)
def test_s12_decoral_automatic_multi_round_correction_chain_merges(db_session: Session) -> None:
    work_order_service, process_service, manager_service, work_order_repository, process_repository = build_services(db_session)

    created = work_order_service.create_work_order(
        build_work_order_create(title="S12 Decoral automatic multi-round", coating_type=CoatingType.DECORAL, total_quantity=10)
    )
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=1),
    )

    advance_to_packing(process_service, created.id)
    root_response = complete_packing(process_service, created.id, ok_quantity=7, correction_quantity=3)

    first_correction = next(
        work_order for work_order in work_order_repository.list(limit=20, offset=0) if work_order.parent_order_id == created.id
    )
    manager_service.assign_plan(
        first_correction.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=2),
    )

    process_service.start_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=root_response.batch_id)
    process_service.finish_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=root_response.batch_id)

    advance_to_packing(process_service, first_correction.id)
    first_child_response = complete_packing(process_service, first_correction.id, ok_quantity=2, correction_quantity=1)
    process_service.start_stage(first_correction.id, ProcessStage.DECORAL_PRODUCTION, batch_id=first_child_response.batch_id)
    process_service.finish_stage(first_correction.id, ProcessStage.DECORAL_PRODUCTION, batch_id=first_child_response.batch_id)

    second_correction = next(
        work_order
        for work_order in work_order_repository.list(limit=20, offset=0)
        if work_order.parent_order_id == first_correction.id
    )
    manager_service.assign_plan(
        second_correction.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=3),
    )
    advance_to_packing(process_service, second_correction.id)
    complete_packing(process_service, second_correction.id, ok_quantity=1, correction_quantity=0)
    process_service.transition_stage(second_correction.id, ProcessStage.DECORAL_PRODUCTION, StageStatus.IN_PROGRESS)
    process_service.finish_stage(second_correction.id, ProcessStage.DECORAL_PRODUCTION)

    parent_work_order = process_repository.get_work_order_with_stage_states(created.id)
    completed_first_correction = process_repository.get_work_order_with_stage_states(first_correction.id)
    completed_second_correction = process_repository.get_work_order_with_stage_states(second_correction.id)

    assert parent_work_order is not None
    assert completed_first_correction is not None
    assert completed_second_correction is not None
    assert process_service.get_display_status(parent_work_order).value == "READY"
    assert process_service.get_display_status(completed_first_correction).value == "READY"
    assert process_service.get_display_status(completed_second_correction).value == "READY"
    assert parent_work_order.completed_quantity == parent_work_order.total_quantity
    assert parent_work_order.current_active_quantity == 0
    assert completed_first_correction.completed_quantity == completed_first_correction.total_quantity
    assert completed_first_correction.current_active_quantity == 0
    assert completed_second_correction.completed_quantity == completed_second_correction.total_quantity
    assert completed_second_correction.current_active_quantity == 0
