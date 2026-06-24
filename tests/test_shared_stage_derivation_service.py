"""Service-level tests for the shared-stage order derivation + line labels (N49-10).

These prove that the two physically shared stages (SURFACE_PREPARATION, PACKING) no longer rank by the
per-line ``queue_position`` (which would collide MANUAL vs AUTOMATIC on the same "Poz. N"), but expose a
backend-derived order and a line label the frontend renders instead.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
import pytest

from app.database.base import Base
from app.manager.schemas import WorkOrderPlanAssignRequest
from app.manager.service import ManagerService
from app.process.enums import ProcessStage, ProductionType, StageStatus
from app.process.repository import ProcessRepository
from app.process.service import ProcessService
from app.paints.schemas import PaintDeliveryCreate
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import WorkOrderCreate
from app.work_orders.service import WorkOrderService
from app.manager.repository import ManagerRepository


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


def _services(db_session: Session):
    return (
        WorkOrderService(WorkOrderRepository(db_session)),
        ProcessService(ProcessRepository(db_session)),
        ManagerService(ManagerRepository(db_session)),
    )


def _create(work_order_service: WorkOrderService, title: str, *, total_quantity: int = 10) -> int:
    created = work_order_service.create_work_order(
        WorkOrderCreate(
            title=title,
            coating_type="RAL",
            total_quantity=total_quantity,
            customer_name="ACME",
            ral_code="RAL 7016",
            paint_code="P-7016",
            paint_producer="AkzoNobel",
            received_date="2026-05-25",
            planned_pickup_date="2026-06-30",
            total_area_m2=24.0,
            profiles_to_count=True,
            accessories_to_count=True,
        )
    )
    return created.id


def test_surface_prep_lists_both_lines_with_labels_and_next_marker(db_session: Session) -> None:
    work_order_service, process_service, manager_service = _services(db_session)
    manual_id = _create(work_order_service, "Manual order")
    automatic_id = _create(work_order_service, "Automatic order")
    # Both are "Poz. 1" on their OWN line — the historical collision case.
    manager_service.assign_plan(manual_id, WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1))
    manager_service.assign_plan(automatic_id, WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=1))

    items = process_service.list_stage_work_orders(ProcessStage.SURFACE_PREPARATION)
    assert {item.id for item in items} == {manual_id, automatic_id}

    # Every row carries a line label, NOT a bare position.
    labels = {item.id: item.shared_stage_line_label for item in items}
    assert labels[manual_id] == "Manualna"
    assert labels[automatic_id] == "Automatyczna"

    # Exactly one head marked "NASTĘPNE" — with both buffers empty the tie goes to automatic.
    next_items = [item for item in items if item.is_next_at_shared_stage]
    assert len(next_items) == 1
    assert next_items[0].id == automatic_id
    assert items[0].id == automatic_id  # the derived order puts the NASTĘPNE row first


def test_surface_prep_feeds_the_starving_line_first(db_session: Session) -> None:
    work_order_service, process_service, manager_service = _services(db_session)
    # Automatic line already has a prepped-but-not-yet-painted order (big buffer); manual is starving.
    auto_prepped = _create(work_order_service, "Auto prepped", total_quantity=50)
    auto_waiting = _create(work_order_service, "Auto waiting", total_quantity=10)
    manual_waiting = _create(work_order_service, "Manual waiting", total_quantity=10)
    manager_service.assign_plan(auto_prepped, WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=1))
    manager_service.assign_plan(auto_waiting, WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=2))
    manager_service.assign_plan(manual_waiting, WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1))

    # Move the first automatic order past surface prep onto the line -> it becomes the buffer.
    process_service.transition_stage(auto_prepped, ProcessStage.SURFACE_PREPARATION, StageStatus.IN_PROGRESS)
    process_service.finish_stage(auto_prepped, ProcessStage.SURFACE_PREPARATION, counted_quantity=50)
    process_service.transition_stage(auto_prepped, ProcessStage.HANGING, StageStatus.IN_PROGRESS)
    process_service.finish_stage(auto_prepped, ProcessStage.HANGING)

    items = process_service.list_stage_work_orders(ProcessStage.SURFACE_PREPARATION)
    active = [item for item in items if item.stage_status.status.value != StageStatus.DONE]
    # Automatic's buffer (50 on the line) >> manual's (0), so the starving manual line is prepped first.
    assert active[0].id == manual_waiting
    assert active[0].is_next_at_shared_stage is True


def test_packing_shows_line_labels_not_positions(db_session: Session) -> None:
    work_order_service, process_service, manager_service = _services(db_session)
    manual_id = _create(work_order_service, "Manual to pack")
    manager_service.assign_plan(manual_id, WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1))

    # Drive the manual order to packing.
    process_service.transition_stage(manual_id, ProcessStage.SURFACE_PREPARATION, StageStatus.IN_PROGRESS)
    process_service.finish_stage(manual_id, ProcessStage.SURFACE_PREPARATION, counted_quantity=10)
    process_service.transition_stage(manual_id, ProcessStage.PRODUCTION, StageStatus.IN_PROGRESS)
    process_service.transition_stage(manual_id, ProcessStage.PRODUCTION, StageStatus.DONE)

    items = process_service.list_stage_work_orders(ProcessStage.PACKING)
    packing_item = next(item for item in items if item.id == manual_id)
    assert packing_item.shared_stage_line_label == "Manualna"
    # No "NASTĘPNE" numbering at packing.
    assert packing_item.is_next_at_shared_stage is False


def test_packing_orders_slot_holders_first(db_session: Session) -> None:
    work_order_service, process_service, manager_service = _services(db_session)
    waiting_id = _create(work_order_service, "Waiting to pack")
    packed_id = _create(work_order_service, "Being packed")
    manager_service.assign_plan(waiting_id, WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1))
    manager_service.assign_plan(packed_id, WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=2))

    for work_order_id in (waiting_id, packed_id):
        process_service.transition_stage(work_order_id, ProcessStage.SURFACE_PREPARATION, StageStatus.IN_PROGRESS)
        process_service.finish_stage(work_order_id, ProcessStage.SURFACE_PREPARATION, counted_quantity=10)
        process_service.transition_stage(work_order_id, ProcessStage.PRODUCTION, StageStatus.IN_PROGRESS)
        process_service.transition_stage(work_order_id, ProcessStage.PRODUCTION, StageStatus.DONE)

    # Start packing the second one so it holds the slot.
    process_service.start_packing(packed_id)

    items = process_service.list_stage_work_orders(ProcessStage.PACKING)
    active = [item for item in items if item.stage_status.status.value != StageStatus.DONE]
    # The slot holder (being packed) sorts ahead of the still-waiting order.
    assert active[0].id == packed_id
    assert active[0].holds_packing_slot is True
