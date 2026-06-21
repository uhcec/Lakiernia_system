from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import logging

from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
import pytest

from app.database.base import Base
from app.audit.context import StationContext
from app.audit.models import AuditEvent
from app.manager.repository import ManagerRepository
from app.manager.schemas import WorkOrderPlanAssignRequest, WorkOrderProductionTypeUpdateRequest
from app.manager.service import ManagerService
from app.process.enums import CoatingType, CorrectionKind, ProcessStage, ProductionType, QuantityBatchType, StageStatus
from app.process.models import ProcessResourceLock, StatOnlyCorrection
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


def finish_returned_correction_on_root(process_service, process_repository, root_id: int, *, quantity: int):
    # In the single-Decoral model, corrected pieces return to the root as a Decoral batch. This
    # finishes that returned batch (the parent's last Decoral work) to complete the order.
    root = process_repository.get_work_order_with_stage_states(root_id)
    returned_batch = next(
        b for b in root.quantity_batches if b.is_active and b.current_stage == ProcessStage.DECORAL_PRODUCTION
    )
    process_service.start_stage(root_id, ProcessStage.DECORAL_PRODUCTION, batch_id=returned_batch.id)
    return process_service.complete_decoral_production(
        root_id, ok_quantity=quantity, correction_quantity=0, batch_id=returned_batch.id
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


def test_operational_quantity_reflects_actual_received_after_surface_preparation(db_session: Session) -> None:
    # NA26: stations show the actual received (counted) quantity as the operational count, while
    # total_quantity / planned_quantity stay the ordered values (office/manager + audit).
    work_order_service, process_service, manager_service, _, _ = build_services(db_session)
    created = create_ral_work_order(work_order_service, "Operational quantity NA26")
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )

    process_service.start_stage(created.id, ProcessStage.SURFACE_PREPARATION)
    sp_done = process_service.finish_stage(created.id, ProcessStage.SURFACE_PREPARATION, counted_quantity=95)

    # Surface-prep read already reflects the counted operational quantity.
    assert sp_done.operational_quantity == 95
    assert sp_done.total_quantity == 100
    assert sp_done.planned_quantity == 100

    # Downstream station (manual production) shows the actual received quantity as operational,
    # not the ordered total.
    production_rows = process_service.list_stage_work_orders(ProcessStage.PRODUCTION)
    row = next(item for item in production_rows if item.id == created.id)
    assert row.operational_quantity == 95
    assert row.total_quantity == 100
    assert row.planned_quantity == 100


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


def test_reconcile_stage_states_drops_phantom_rows_per_route_NA42(db_session: Session) -> None:
    # NA42: once the production method is known at planning, the stage-state rows are trimmed to the
    # real route — AUTOMATIC has no PRODUCTION row (the line paints automatically), MANUAL has no
    # HANGING row. Switching the method later re-adds/removes the right rows.
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    auto = create_ral_work_order(work_order_service, "Auto NA42")
    manual = create_ral_work_order(work_order_service, "Manual NA42")
    manager_service.assign_plan(auto.id, WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=1))
    manager_service.assign_plan(manual.id, WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=2))

    auto_stages = {ss.stage for ss in process_repository.get_work_order_with_stage_states(auto.id).stage_states}
    manual_stages = {ss.stage for ss in process_repository.get_work_order_with_stage_states(manual.id).stage_states}
    assert ProcessStage.PRODUCTION not in auto_stages and ProcessStage.HANGING in auto_stages
    assert ProcessStage.HANGING not in manual_stages and ProcessStage.PRODUCTION in manual_stages

    # Switching AUTOMATIC -> MANUAL reconciles: PRODUCTION appears, HANGING goes away.
    manager_service.update_production_type(auto.id, WorkOrderProductionTypeUpdateRequest(production_type=ProductionType.MANUAL))
    switched_stages = {ss.stage for ss in process_repository.get_work_order_with_stage_states(auto.id).stage_states}
    assert ProcessStage.PRODUCTION in switched_stages and ProcessStage.HANGING not in switched_stages


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


def test_automatic_hanging_start_starts_production_and_packing(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    automatic_order = create_ral_work_order(work_order_service, "Automatic auto start")
    manager_service.assign_plan(
        automatic_order.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=1),
    )
    process_service.transition_stage(automatic_order.id, ProcessStage.SURFACE_PREPARATION, StageStatus.IN_PROGRESS)
    process_service.transition_stage(automatic_order.id, ProcessStage.SURFACE_PREPARATION, StageStatus.DONE)
    process_service.transition_stage(automatic_order.id, ProcessStage.HANGING, StageStatus.IN_PROGRESS)

    # The automatic line runs without a manual production step (NA42: AUTOMATIC has no PRODUCTION
    # stage), so PACKING begins the moment HANGING starts — the order starts packing immediately, not
    # merely holding a reservation. The automatic-production panel still shows it (preview view).
    before_finish = process_repository.get_work_order_with_stage_states(automatic_order.id)
    assert before_finish is not None
    assert process_service.is_visible_in_stage(before_finish, ProcessStage.PRODUCTION, ProductionType.AUTOMATIC) is True
    stages_before_finish = {stage.stage: stage.status for stage in before_finish.stage_states}
    assert ProcessStage.PRODUCTION not in stages_before_finish  # NA42: automatic has no PRODUCTION row
    assert stages_before_finish[ProcessStage.PACKING] == StageStatus.IN_PROGRESS
    # ...and the order already reports as being in packing for office/list views.
    assert process_service.get_display_status(before_finish).value == "PACKING"

    # But packing completion is still blocked until HANGING is DONE (start now, finish after hanging).
    with pytest.raises(InvalidProcessStageTransitionError):
        process_service.complete_packing(
            automatic_order.id,
            counted_quantity=before_finish.current_active_quantity,
            ok_quantity=before_finish.current_active_quantity,
            correction_quantity=0,
            station_context=StationContext(station_id=StationId.PACKING),
        )

    process_service.finish_stage(automatic_order.id, ProcessStage.HANGING)
    work_order = process_repository.get_work_order_with_stage_states(automatic_order.id)

    assert work_order is not None
    stages_after_finish = {stage.stage: stage.status for stage in work_order.stage_states}
    assert ProcessStage.PRODUCTION not in stages_after_finish  # NA42: automatic has no PRODUCTION row
    assert stages_after_finish[ProcessStage.PACKING] == StageStatus.IN_PROGRESS


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


def test_decoral_correction_returns_to_root_decoral_scenario1_merge(db_session: Session) -> None:
    # Scenario 1: the correction is fixed BEFORE the root finishes Decoral. The corrected pieces
    # rejoin the root's single in-progress Decoral batch (it grows), the child closes without its
    # own Decoral, and finishing the grown batch completes the whole order.
    work_order_service, process_service, manager_service, work_order_repository, process_repository = build_services(db_session)

    parent = work_order_service.create_work_order(
        build_work_order_create(title="Decoral return sc1", coating_type=CoatingType.DECORAL, total_quantity=10)
    )
    manager_service.assign_plan(parent.id, WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1))
    advance_to_packing(process_service, parent.id)
    response = complete_packing(process_service, parent.id, ok_quantity=8, correction_quantity=2)
    root_decoral_batch = response.batch_id

    child = next(wo for wo in work_order_repository.list(limit=50, offset=0) if wo.is_correction)
    manager_service.assign_plan(child.id, WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=2))
    advance_to_packing(process_service, child.id)
    complete_packing(process_service, child.id, ok_quantity=2, correction_quantity=0)

    child_after = process_repository.get_work_order_with_stage_states(child.id)
    assert child_after is not None
    assert child_after.completed_quantity == child_after.total_quantity == 2
    assert child_after.current_active_quantity == 0

    root = process_repository.get_work_order_with_stage_states(parent.id)
    assert root is not None
    active = [b for b in root.quantity_batches if b.is_active]
    assert len(active) == 1
    assert active[0].current_stage == ProcessStage.DECORAL_PRODUCTION
    assert active[0].quantity == 10  # grown from 8 to 10
    assert root.completed_quantity == 0

    process_service.start_stage(parent.id, ProcessStage.DECORAL_PRODUCTION, batch_id=root_decoral_batch)
    process_service.complete_decoral_production(parent.id, ok_quantity=10, correction_quantity=0, batch_id=root_decoral_batch)

    final = process_repository.get_work_order_with_stage_states(parent.id)
    assert final is not None
    assert final.completed_quantity == 10
    assert process_service.get_display_status(final).value == "READY"


def test_decoral_correction_returns_to_root_decoral_scenario2_park(db_session: Session) -> None:
    # Scenario 2: the root finishes Decoral of the OK pieces BEFORE the correction returns. The order
    # parks (not READY, waiting), then the returned pieces start a fresh Decoral batch on the root
    # which, once finished, completes the whole order.
    work_order_service, process_service, manager_service, work_order_repository, process_repository = build_services(db_session)

    parent = work_order_service.create_work_order(
        build_work_order_create(title="Decoral return sc2", coating_type=CoatingType.DECORAL, total_quantity=10)
    )
    manager_service.assign_plan(parent.id, WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1))
    advance_to_packing(process_service, parent.id)
    response = complete_packing(process_service, parent.id, ok_quantity=8, correction_quantity=2)
    root_decoral_batch = response.batch_id
    child = next(wo for wo in work_order_repository.list(limit=50, offset=0) if wo.is_correction)

    # Finish the OK Decoral first -> order parks (waiting for the correction).
    process_service.start_stage(parent.id, ProcessStage.DECORAL_PRODUCTION, batch_id=root_decoral_batch)
    process_service.complete_decoral_production(parent.id, ok_quantity=8, correction_quantity=0, batch_id=root_decoral_batch)

    parked = process_repository.get_work_order_with_stage_states(parent.id)
    assert parked is not None
    assert parked.completed_quantity == 8
    assert process_service.get_display_status(parked).value == "WAITING_FOR_CORRECTIONS"

    # Correction returns -> a fresh Decoral batch appears on the root.
    manager_service.assign_plan(child.id, WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=2))
    advance_to_packing(process_service, child.id)
    complete_packing(process_service, child.id, ok_quantity=2, correction_quantity=0)

    root = process_repository.get_work_order_with_stage_states(parent.id)
    assert root is not None
    active = [b for b in root.quantity_batches if b.is_active]
    assert len(active) == 1
    assert active[0].current_stage == ProcessStage.DECORAL_PRODUCTION
    assert active[0].quantity == 2
    assert root.completed_quantity == 8

    returned_batch = active[0].id
    process_service.start_stage(parent.id, ProcessStage.DECORAL_PRODUCTION, batch_id=returned_batch)
    process_service.complete_decoral_production(parent.id, ok_quantity=2, correction_quantity=0, batch_id=returned_batch)

    final = process_repository.get_work_order_with_stage_states(parent.id)
    assert final is not None
    assert final.completed_quantity == 10
    assert process_service.get_display_status(final).value == "READY"


def test_nested_decoral_correction_numbers_reference_root(db_session: Session) -> None:
    # First correction of root 0001 -> "P0001"; a correction of that correction -> "P0001-2"
    # (root-relative suffix), so correction numbers never consume the main client sequence.
    work_order_service, process_service, manager_service, work_order_repository, _ = build_services(db_session)

    parent = work_order_service.create_work_order(
        build_work_order_create(title="Nested decoral numbering", coating_type=CoatingType.DECORAL, total_quantity=10)
    )
    manager_service.assign_plan(
        parent.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, parent.id)
    complete_packing(process_service, parent.id, ok_quantity=7, correction_quantity=3)

    child = next(wo for wo in work_order_repository.list(limit=50, offset=0) if wo.is_correction)
    assert child.order_number == f"P{parent.order_number}"
    assert child.parent_order_id == parent.id

    # The child fails its own QC: its OK pieces return to the root and the bad pieces spawn another
    # correction, which is a FLAT child of the root numbered with the next suffix.
    manager_service.assign_plan(
        child.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=2),
    )
    advance_to_packing(process_service, child.id)
    complete_packing(process_service, child.id, ok_quantity=2, correction_quantity=1)

    second_correction = next(
        wo for wo in work_order_repository.list(limit=50, offset=0) if wo.is_correction and wo.id != child.id
    )
    assert second_correction.order_number == f"P{parent.order_number}-2"
    assert second_correction.parent_order_id == parent.id  # flat child of the root, not of the child


def test_cannot_change_production_type_after_production_started(db_session: Session) -> None:
    # D1 audit gap: the guard that prevents the automatic/manual tangle (changing production type
    # after work has started) had no direct regression test.
    work_order_service, process_service, manager_service, _, _ = build_services(db_session)
    created = create_ral_work_order(work_order_service, "Lock production type")
    manager_service.assign_plan(
        created.id, WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1)
    )
    advance_to_production(process_service, created.id)  # surface prep done; production not started yet
    process_service.transition_stage(created.id, ProcessStage.PRODUCTION, StageStatus.IN_PROGRESS)

    with pytest.raises(InvalidManagerPlanningError):
        manager_service.update_production_type(
            created.id, WorkOrderProductionTypeUpdateRequest(production_type=ProductionType.AUTOMATIC)
        )

    unchanged = process_service.get_work_order_process(created.id)
    assert unchanged.production_type == ProductionType.MANUAL


def test_decoral_automatic_correction_returns_to_root_and_completes_S08(db_session: Session) -> None:
    # S08: DECORAL + AUTOMATIC correction. The child takes the automatic route (HANGING -> PACKING),
    # closes at packing, and its OK pieces rejoin the ROOT's single Decoral pass — no own Decoral.
    work_order_service, process_service, manager_service, work_order_repository, process_repository = build_services(db_session)

    parent = work_order_service.create_work_order(
        build_work_order_create(title="Decoral automat S08", coating_type=CoatingType.DECORAL, total_quantity=10)
    )
    manager_service.assign_plan(parent.id, WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=1))
    advance_to_packing(process_service, parent.id)
    response = complete_packing(process_service, parent.id, ok_quantity=8, correction_quantity=2)
    root_decoral_batch = response.batch_id

    child = next(wo for wo in work_order_repository.list(limit=50, offset=0) if wo.is_correction)
    manager_service.assign_plan(child.id, WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=2))
    advance_to_packing(process_service, child.id)
    complete_packing(process_service, child.id, ok_quantity=2, correction_quantity=0)

    child_after = process_repository.get_work_order_with_stage_states(child.id)
    assert child_after is not None
    assert child_after.completed_quantity == child_after.total_quantity == 2

    root = process_repository.get_work_order_with_stage_states(parent.id)
    assert root is not None
    active = [b for b in root.quantity_batches if b.is_active]
    assert len(active) == 1
    assert active[0].current_stage == ProcessStage.DECORAL_PRODUCTION
    assert active[0].quantity == 10  # 8 OK + 2 returned, merged onto the single root Decoral batch

    process_service.start_stage(parent.id, ProcessStage.DECORAL_PRODUCTION, batch_id=root_decoral_batch)
    process_service.complete_decoral_production(parent.id, ok_quantity=10, correction_quantity=0, batch_id=root_decoral_batch)

    final = process_repository.get_work_order_with_stage_states(parent.id)
    assert final is not None
    assert final.completed_quantity == 10
    assert process_service.get_display_status(final).value == "READY"


def test_corrected_order_reports_cumulative_paint_across_chain_NA32(db_session: Session) -> None:
    # NA32: a corrected automatic order must report the CUMULATIVE paint consumption of the whole
    # correction chain, not just the last round. advance_to_packing records 1.0 kg per automatic pass,
    # so the DECORAL parent (1.0 kg) plus its automatic correction child (1.0 kg) must roll up to 2.0 kg
    # on the parent's read model, even though the per-round gate field is reset between rounds.
    work_order_service, process_service, manager_service, work_order_repository, _ = build_services(db_session)

    parent = work_order_service.create_work_order(
        build_work_order_create(title="Decoral NA32 rollup", coating_type=CoatingType.DECORAL, total_quantity=10)
    )
    manager_service.assign_plan(parent.id, WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=1))
    advance_to_packing(process_service, parent.id)
    complete_packing(process_service, parent.id, ok_quantity=8, correction_quantity=2)

    child = next(wo for wo in work_order_repository.list(limit=50, offset=0) if wo.is_correction)
    manager_service.assign_plan(child.id, WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=2))
    advance_to_packing(process_service, child.id)

    # Parent paint (1.0) + child paint (1.0) roll up on the parent; the child reports only its own.
    assert work_order_service.get_work_order(parent.id).consumed_paint_quantity_kg == 2.0
    assert work_order_service.get_work_order(child.id).consumed_paint_quantity_kg == 1.0


def test_nested_decoral_corrections_complete_to_ready_S11(db_session: Session) -> None:
    # S11: a correction-of-a-correction. Every child closes at packing and returns OK to the root's
    # single Decoral pass; the order is READY only once all flat descendants close and the root's
    # grown Decoral batch finishes.
    work_order_service, process_service, manager_service, work_order_repository, process_repository = build_services(db_session)

    parent = work_order_service.create_work_order(
        build_work_order_create(title="Decoral nested S11", coating_type=CoatingType.DECORAL, total_quantity=10)
    )
    manager_service.assign_plan(parent.id, WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1))
    advance_to_packing(process_service, parent.id)
    response = complete_packing(process_service, parent.id, ok_quantity=7, correction_quantity=3)
    root_decoral_batch = response.batch_id

    parent_after_split = process_repository.get_work_order_with_stage_states(parent.id)
    assert parent_after_split is not None
    assert process_service.is_decoral_incomplete(parent_after_split) is True  # "N" marker while open

    # First correction: fixes 2, fails 1 -> 2 return to root Decoral, a flat second correction is made.
    child = next(wo for wo in work_order_repository.list(limit=50, offset=0) if wo.is_correction)
    manager_service.assign_plan(child.id, WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=2))
    advance_to_packing(process_service, child.id)
    complete_packing(process_service, child.id, ok_quantity=2, correction_quantity=1)

    second = next(wo for wo in work_order_repository.list(limit=50, offset=0) if wo.is_correction and wo.id != child.id)
    assert second.parent_order_id == parent.id  # flat child of the root

    # Second correction: all 1 piece OK -> returns to the root Decoral.
    manager_service.assign_plan(second.id, WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=3))
    advance_to_packing(process_service, second.id)
    complete_packing(process_service, second.id, ok_quantity=1, correction_quantity=0)

    root = process_repository.get_work_order_with_stage_states(parent.id)
    assert root is not None
    active = [b for b in root.quantity_batches if b.is_active]
    assert len(active) == 1
    assert active[0].quantity == 10  # 7 + 2 + 1 merged onto the single root Decoral batch

    process_service.start_stage(parent.id, ProcessStage.DECORAL_PRODUCTION, batch_id=root_decoral_batch)
    process_service.complete_decoral_production(parent.id, ok_quantity=10, correction_quantity=0, batch_id=root_decoral_batch)

    final = process_repository.get_work_order_with_stage_states(parent.id)
    assert final is not None
    assert final.completed_quantity == 10
    assert process_service.get_display_status(final).value == "READY"


def test_complete_decoral_production_ok_finishes_tracked_ok_batch(db_session: Session) -> None:
    # The frontend completes Decoral via complete_decoral_production. The OK batch that split off at
    # packing finishes here; the parent stays not-READY until its open correction child closes.
    work_order_service, process_service, manager_service, work_order_repository, process_repository = build_services(db_session)

    created = work_order_service.create_work_order(
        build_work_order_create(title="Decoral complete ok", coating_type=CoatingType.DECORAL, total_quantity=10)
    )
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)
    response = complete_packing(process_service, created.id, ok_quantity=7, correction_quantity=3)

    process_service.start_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=response.batch_id)
    process_service.complete_decoral_production(created.id, ok_quantity=7, correction_quantity=0, batch_id=response.batch_id)

    parent = process_repository.get_work_order_with_stage_states(created.id)
    assert parent is not None
    assert parent.completed_quantity == 7
    assert process_service.get_display_status(parent).value == "WAITING_FOR_CORRECTIONS"


def test_complete_decoral_production_with_correction_resets_to_planning(db_session: Session) -> None:
    # A defect found at the Decoral stage (last stage for DECORAL) uses the unified batch-reset:
    # ok goes to completed and the same order returns to planning for the correction round.
    work_order_service, process_service, manager_service, work_order_repository, process_repository = build_services(db_session)

    created = work_order_service.create_work_order(
        build_work_order_create(title="Decoral stage correction", coating_type=CoatingType.DECORAL, total_quantity=10)
    )
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    # No correction at packing -> whole batch advances to Decoral.
    advance_to_packing(process_service, created.id)
    response = complete_packing(process_service, created.id, ok_quantity=10, correction_quantity=0)

    process_service.start_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=response.batch_id)
    # Decoral QC: 8 ok, 2 need correction.
    process_service.complete_decoral_production(
        created.id,
        ok_quantity=8,
        correction_quantity=2,
        correction_profiles_quantity=2,
        correction_accessories_quantity=0,
        correction_reason_category="za grubo",
        batch_id=response.batch_id,
    )

    after = process_repository.get_work_order_with_stage_states(created.id)
    assert after is not None
    assert after.completed_quantity == 8
    # No child order is created at the Decoral stage; the same order returns to planning (batch-reset).
    assert [wo for wo in work_order_repository.list(limit=20, offset=0) if wo.is_correction] == []
    assert process_service.get_display_status(after).value == "TO_BE_PLANNED"
    active_correction = after.active_batch
    assert active_correction is not None
    assert active_correction.parent_batch_id is not None
    assert active_correction.quantity == 2


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

    # Correction child redoes the base coat (production -> packing) and its OK pieces return to the
    # root's Decoral (single Decoral pass); finishing the returned batch completes the order.
    advance_to_packing(process_service, correction_order.id)
    complete_packing(process_service, correction_order.id, ok_quantity=3, correction_quantity=0)
    finish_returned_correction_on_root(process_service, process_repository, created.id, quantity=3)

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
    assert ProcessStage.HANGING not in stage_states  # NA42: MANUAL has no HANGING row
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
    # Correction child returns its OK pieces to the root's Decoral (single pass); no own Decoral.
    advance_to_packing(process_service, correction_order.id)
    complete_packing(process_service, correction_order.id, ok_quantity=3, correction_quantity=0)
    finish_returned_correction_on_root(process_service, process_repository, created.id, quantity=3)

    merged_parent = process_repository.get_work_order_with_stage_states(created.id)
    completed_correction = process_repository.get_work_order_with_stage_states(correction_order.id)

    assert merged_parent is not None
    assert completed_correction is not None
    assert merged_parent.completed_quantity == 10
    assert process_service.get_display_status(merged_parent).value == "READY"
    assert completed_correction.parent_order_id == created.id


@contextmanager
def capture_logs(logger_name: str, level: int = logging.WARNING):
    """Capture records from a specific logger via a directly-attached handler.

    pytest's ``caplog`` relies on propagation to the root handler, which is unreliable once another
    test in the suite toggles ``logging.disable`` / a logger's propagation (see
    test_request_traceability.py). Attaching our own handler — mirroring that test's proven pattern —
    captures regardless of global logging state.
    """
    captured: list[logging.LogRecord] = []

    class _ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    target = logging.getLogger(logger_name)
    handler = _ListHandler()
    handler.setLevel(level)
    previous_level = target.level
    previous_disabled = target.disabled
    previous_global_disable = logging.root.manager.disable
    target.addHandler(handler)
    target.setLevel(level)
    target.disabled = False
    logging.disable(logging.NOTSET)
    try:
        yield captured
    finally:
        target.removeHandler(handler)
        target.setLevel(previous_level)
        target.disabled = previous_disabled
        logging.disable(previous_global_disable)


# NA19 — finalize must not silently mask a quantity-conservation leak.
def test_finalize_does_not_warn_when_quantities_match(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)

    created = work_order_service.create_work_order(
        build_work_order_create(title="Clean finalize", coating_type=CoatingType.RAL, total_quantity=10)
    )
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)

    with capture_logs("app.process.service") as records:
        complete_packing(process_service, created.id, ok_quantity=10, correction_quantity=0)

    final = process_repository.get_work_order_with_stage_states(created.id)
    assert final is not None
    assert final.completed_quantity == 10 == final.total_quantity
    assert process_service.get_display_status(final).value == "READY"
    # Normal case: quantities reconcile, so the safety-net warning must stay silent.
    assert not any("quantity gap" in record.getMessage() for record in records)


def test_finalize_warns_and_forces_total_when_quantity_gap(db_session: Session) -> None:
    work_order_service, process_service, manager_service, work_order_repository, process_repository = build_services(db_session)

    # Drive a DECORAL correction child fully back into its parent (finalize via the correction_orders
    # branch), so we have a legitimately finalizable parent to probe.
    created = work_order_service.create_work_order(
        build_work_order_create(title="Leaky finalize", coating_type=CoatingType.DECORAL, total_quantity=10)
    )
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)
    complete_packing(process_service, created.id, ok_quantity=7, correction_quantity=3)

    correction_order = next(wo for wo in work_order_repository.list(limit=20, offset=0) if wo.is_correction)
    manager_service.assign_plan(
        correction_order.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=2),
    )
    decoral_batch = next(
        item.batch_id
        for item in process_service.list_stage_work_orders(ProcessStage.DECORAL_PRODUCTION)
        if item.id == created.id
    )
    process_service.start_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=decoral_batch)
    process_service.finish_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=decoral_batch)
    advance_to_packing(process_service, correction_order.id)
    complete_packing(process_service, correction_order.id, ok_quantity=3, correction_quantity=0)
    finish_returned_correction_on_root(process_service, process_repository, created.id, quantity=3)

    merged_parent = process_repository.get_work_order_with_stage_states(created.id)
    assert merged_parent is not None
    assert merged_parent.completed_quantity == 10

    # Simulate a quantity-conservation leak that should never happen: completed drifts below total
    # while the order is otherwise finalizable. The safety net must surface it, not hide it.
    merged_parent.completed_quantity = 9
    process_repository.commit()

    with capture_logs("app.process.service") as records:
        process_service._finalize_completion_chain_if_ready(merged_parent)

    refreshed = process_repository.get_work_order_with_stage_states(created.id)
    assert refreshed is not None
    assert refreshed.completed_quantity == 10  # forced back to total
    gap_warnings = [record for record in records if "quantity gap" in record.getMessage()]
    assert len(gap_warnings) == 1
    assert "completed=9" in gap_warnings[0].getMessage()


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
    winner_id = next(iter(in_progress_ids))
    # The winning automatic also reserves a packing slot at hanging start (NA22a).
    assert {(lock.resource_key, lock.work_order_id) for lock in resource_locks} == {
        ("HANGING", winner_id),
        ("PACKING:1", winner_id),
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


def test_finished_returned_correction_decoral_batch_cannot_be_reopened_after_ready(db_session: Session) -> None:
    # Once corrected pieces return to the root's Decoral and that batch finishes (order READY), the
    # finished returned Decoral batch cannot be reopened.
    work_order_service, process_service, manager_service, work_order_repository, process_repository = build_services(db_session)

    created = work_order_service.create_work_order(
        build_work_order_create(title="Reject reopen finished returned batch", coating_type=CoatingType.DECORAL, total_quantity=10)
    )
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    advance_to_packing(process_service, created.id)
    root_response = complete_packing(process_service, created.id, ok_quantity=7, correction_quantity=3)

    correction = next(work_order for work_order in work_order_repository.list(limit=20, offset=0) if work_order.is_correction)
    manager_service.assign_plan(
        correction.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=2),
    )
    process_service.start_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=root_response.batch_id)
    process_service.finish_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=root_response.batch_id)

    advance_to_packing(process_service, correction.id)
    complete_packing(process_service, correction.id, ok_quantity=3, correction_quantity=0)

    root = process_repository.get_work_order_with_stage_states(created.id)
    returned_batch = next(b for b in root.quantity_batches if b.is_active and b.current_stage == ProcessStage.DECORAL_PRODUCTION)
    process_service.start_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=returned_batch.id)
    process_service.complete_decoral_production(created.id, ok_quantity=3, correction_quantity=0, batch_id=returned_batch.id)

    before_parent = process_repository.get_work_order_with_stage_states(created.id)
    assert before_parent is not None
    assert process_service.get_display_status(before_parent).value == "READY"

    with pytest.raises(InvalidProcessStageTransitionError) as exc_info:
        process_service.reopen_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=returned_batch.id)

    after_parent = process_repository.get_work_order_with_stage_states(created.id)

    assert str(exc_info.value) == "Finished tracked batches cannot be reopened."
    assert after_parent is not None
    assert after_parent.completed_quantity == before_parent.completed_quantity == 10
    assert after_parent.current_active_quantity == before_parent.current_active_quantity == 0
    assert process_service.get_display_status(after_parent).value == "READY"


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

    # Automatic correction redoes base coat and its OK pieces return to the root's Decoral.
    advance_to_packing(process_service, correction_order.id)
    complete_packing(process_service, correction_order.id, ok_quantity=3, correction_quantity=0)
    finish_returned_correction_on_root(process_service, process_repository, created.id, quantity=3)

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
        work_order for work_order in work_order_repository.list(limit=20, offset=0) if work_order.is_correction
    )
    manager_service.assign_plan(
        first_correction.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=2),
    )

    process_service.start_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=root_response.batch_id)
    process_service.finish_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=root_response.batch_id)

    # First correction redoes base coat; 2 OK return to root Decoral, 1 spawns a flat second
    # correction of the root. Finish the returned 2 on the root; order still waits for the last 1.
    advance_to_packing(process_service, first_correction.id)
    complete_packing(process_service, first_correction.id, ok_quantity=2, correction_quantity=1)
    finish_returned_correction_on_root(process_service, process_repository, created.id, quantity=2)

    second_correction = next(
        work_order
        for work_order in work_order_repository.list(limit=20, offset=0)
        if work_order.is_correction and work_order.id != first_correction.id
    )
    manager_service.assign_plan(
        second_correction.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=3),
    )
    advance_to_packing(process_service, second_correction.id)
    complete_packing(process_service, second_correction.id, ok_quantity=1, correction_quantity=0)
    finish_returned_correction_on_root(process_service, process_repository, created.id, quantity=1)

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
        work_order for work_order in work_order_repository.list(limit=20, offset=0) if work_order.is_correction
    )
    manager_service.assign_plan(
        first_correction.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=2),
    )

    process_service.start_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=root_response.batch_id)
    process_service.finish_stage(created.id, ProcessStage.DECORAL_PRODUCTION, batch_id=root_response.batch_id)

    advance_to_packing(process_service, first_correction.id)
    complete_packing(process_service, first_correction.id, ok_quantity=2, correction_quantity=1)
    finish_returned_correction_on_root(process_service, process_repository, created.id, quantity=2)

    second_correction = next(
        work_order
        for work_order in work_order_repository.list(limit=20, offset=0)
        if work_order.is_correction and work_order.id != first_correction.id
    )
    manager_service.assign_plan(
        second_correction.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=3),
    )
    advance_to_packing(process_service, second_correction.id)
    complete_packing(process_service, second_correction.id, ok_quantity=1, correction_quantity=0)
    finish_returned_correction_on_root(process_service, process_repository, created.id, quantity=1)

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


def test_completed_order_cannot_be_sent_backwards_manual_NA30(db_session: Session) -> None:
    """NA30: a completed (READY) order must reject re-opening an earlier stage.

    Without the completion invariant a forward transition on a fully-packed order succeeded and left
    a contradictory state (an earlier stage IN_PROGRESS while PACKING was DONE).
    """
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    created = create_ral_work_order(work_order_service, "NA30 manual completion invariant")
    manager_service.assign_plan(
        created.id, WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1)
    )
    advance_to_packing(process_service, created.id)
    complete_packing(process_service, created.id, ok_quantity=100, correction_quantity=0)

    completed = process_repository.get_work_order_with_stage_states(created.id)
    assert process_service.get_display_status(completed).value == "READY"

    # Re-opening PRODUCTION on a completed order must raise, not silently flip it back.
    with pytest.raises(InvalidProcessStageTransitionError) as exc_info:
        process_service.transition_stage(created.id, ProcessStage.PRODUCTION, StageStatus.IN_PROGRESS)
    assert "already" in str(exc_info.value).lower()

    # The higher-level start_stage entry point is guarded too.
    with pytest.raises(InvalidProcessStageTransitionError):
        process_service.start_stage(created.id, ProcessStage.PRODUCTION)

    # State is untouched: PRODUCTION and PACKING both remain DONE.
    after = process_repository.get_work_order_with_stage_states(created.id)
    production = next(s for s in after.stage_states if s.stage == ProcessStage.PRODUCTION)
    packing = next(s for s in after.stage_states if s.stage == ProcessStage.PACKING)
    assert production.status == StageStatus.DONE
    assert packing.status == StageStatus.DONE
    assert process_service.get_display_status(after).value == "READY"


def test_completed_order_cannot_be_sent_backwards_automatic_hanging_NA30(db_session: Session) -> None:
    """NA30 (original report): an AUTOMATIC order, once packed, must reject re-opening HANGING."""
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    created = create_ral_work_order(work_order_service, "NA30 automatic completion invariant")
    manager_service.assign_plan(
        created.id, WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=1)
    )
    advance_to_packing(process_service, created.id)
    complete_packing(process_service, created.id, ok_quantity=100, correction_quantity=0)

    completed = process_repository.get_work_order_with_stage_states(created.id)
    assert process_service.get_display_status(completed).value == "READY"

    with pytest.raises(InvalidProcessStageTransitionError) as exc_info:
        process_service.transition_stage(created.id, ProcessStage.HANGING, StageStatus.IN_PROGRESS)
    assert "already" in str(exc_info.value).lower()

    after = process_repository.get_work_order_with_stage_states(created.id)
    hanging = next(s for s in after.stage_states if s.stage == ProcessStage.HANGING)
    packing = next(s for s in after.stage_states if s.stage == ProcessStage.PACKING)
    assert hanging.status == StageStatus.DONE
    assert packing.status == StageStatus.DONE


def test_select_correction_kind_seam_NA40(db_session: Session) -> None:
    """NA40: the single correction seam classifies the kind by coating + packing path.

    Pins the classifier so NA34's stat-only kind is added as one more branch here, not a parallel flow.
    """
    work_order_service, process_service, _, _, _ = build_services(db_session)
    ral_created = work_order_service.create_work_order(
        build_work_order_create(title="NA40 RAL kind", coating_type=CoatingType.RAL)
    )
    decoral_created = work_order_service.create_work_order(
        build_work_order_create(title="NA40 DECORAL kind", coating_type=CoatingType.DECORAL)
    )
    # Classify against the ORM work orders (the seam runs on these in production).
    ral = process_service.get_work_order_process(ral_created.id)
    decoral = process_service.get_work_order_process(decoral_created.id)
    assert ral.coating_type == CoatingType.RAL
    assert decoral.coating_type == CoatingType.DECORAL

    # Plain (non-tracked) packing path: DECORAL spins off a child "P" order; RAL replans in place.
    assert process_service._select_correction_kind(ral, tracked_batch=False) == CorrectionKind.REPLAN_IN_PLACE
    assert process_service._select_correction_kind(decoral, tracked_batch=False) == CorrectionKind.SPIN_OFF_CHILD
    # Tracked-batch packing always replans in place, regardless of coating.
    assert process_service._select_correction_kind(ral, tracked_batch=True) == CorrectionKind.REPLAN_IN_PLACE
    assert process_service._select_correction_kind(decoral, tracked_batch=True) == CorrectionKind.REPLAN_IN_PLACE


def test_stat_only_correction_ral_completes_as_is_NA34(db_session: Session) -> None:
    """NA34: a RAL "fixed on the spot" correction logs a statistic and completes the order as-is.

    No CORRECTION batch, no child, no return to planning: completed == total (the corrected pieces are
    good), the order is READY, and the corrections reason report counts the stat-only correction.
    """
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    created = create_ral_work_order(work_order_service, "NA34 RAL stat-only")
    manager_service.assign_plan(
        created.id, WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1)
    )
    advance_to_packing(process_service, created.id)

    process_service.complete_packing(
        created.id,
        counted_quantity=100,
        ok_quantity=90,
        correction_quantity=10,
        correction_profiles_quantity=10,
        correction_accessories_quantity=0,
        correction_reason_category="niedomalowanie",
        stat_only_correction=True,
    )

    work_order = process_repository.get_work_order_with_stage_states(created.id)
    assert process_service.get_display_status(work_order).value == "READY"
    assert work_order.completed_quantity == work_order.total_quantity == 100
    assert work_order.current_active_quantity == 0
    # No replan and no child: not sent back to planning, no CORRECTION batch, no correction orders.
    assert work_order.production_type is not None  # still planned (was not reset to planning)
    assert not any(b.type == QuantityBatchType.CORRECTION for b in work_order.quantity_batches)
    assert work_order.correction_orders == []

    # The stat-only correction is recorded once and shows up in the corrections reason report.
    stat_rows = db_session.query(StatOnlyCorrection).filter_by(work_order_id=created.id).all()
    assert len(stat_rows) == 1
    assert stat_rows[0].correction_quantity == 10
    assert stat_rows[0].correction_reason_category == "niedomalowanie"
    report = {row[0]: (row[1], row[2]) for row in manager_service.repository.list_correction_reason_report()}
    assert report.get("niedomalowanie") == (1, 10)


def test_stat_only_correction_requires_quantity_at_schema(db_session: Session) -> None:
    """NA34: stat-only with zero correction quantity is rejected at the request schema."""
    from pydantic import ValidationError

    from app.process.schemas import PackingCompleteRequest

    with pytest.raises(ValidationError):
        PackingCompleteRequest(counted_quantity=10, ok_quantity=10, correction_quantity=0, stat_only_correction=True)


def test_stat_only_correction_decoral_keeps_single_decoral_no_child_NA34(db_session: Session) -> None:
    """NA34: a DECORAL stat-only correction logs the stat and keeps the pieces on the single Decoral
    pass — no child "P" order, no decoral-incomplete marker."""
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    created = work_order_service.create_work_order(
        build_work_order_create(title="NA34 DECORAL stat-only", coating_type=CoatingType.DECORAL, total_quantity=100)
    )
    manager_service.assign_plan(
        created.id, WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1)
    )
    advance_to_packing(process_service, created.id)

    process_service.complete_packing(
        created.id,
        counted_quantity=100,
        ok_quantity=92,
        correction_quantity=8,
        correction_profiles_quantity=8,
        correction_accessories_quantity=0,
        correction_reason_category="za grubo",
        stat_only_correction=True,
    )

    work_order = process_repository.get_work_order_with_stage_states(created.id)
    # No child order spun off and no decoral-incomplete ("N") marker.
    assert work_order.correction_orders == []
    assert not process_service.is_decoral_incomplete(work_order)
    # The whole counted quantity continues on the single Decoral pass: the order is now at the Decoral
    # stage (not READY, not replanned) with all 100 pieces on one active batch (nothing spun off).
    assert process_service.get_display_status(work_order).value == "DECORAL_PRODUCTION"
    active_batches = [b for b in work_order.quantity_batches if b.is_active]
    assert len(active_batches) == 1
    assert active_batches[0].quantity == 100
    # Stat recorded once, counted in the report.
    assert db_session.query(StatOnlyCorrection).filter_by(work_order_id=created.id).count() == 1
    report = {row[0]: (row[1], row[2]) for row in manager_service.repository.list_correction_reason_report()}
    assert report.get("za grubo") == (1, 8)
