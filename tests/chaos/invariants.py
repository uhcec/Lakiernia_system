from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.process.enums import ProcessDisplayStatus
from app.process.repository import ProcessRepository
from app.process.service import ProcessService
from app.shared.enums import WorkOrderStatus
from app.work_orders.schemas import WorkOrderCreate
from app.work_orders.models import WorkOrder
from tests.chaos.harness import ALLOWED_CHAOS_STATUS_CODES, ChaosEvent


def assert_no_raw_500s(events: list[ChaosEvent]) -> None:
    disallowed = [event for event in events if event.status_code not in ALLOWED_CHAOS_STATUS_CODES]
    assert not disallowed, f"Unexpected HTTP statuses in chaos run: {[(event.actor, event.path, event.status_code) for event in disallowed]}"


def assert_no_duplicate_queue_positions(db_session: Session) -> None:
    planned_orders = db_session.scalars(
        select(WorkOrder).where(WorkOrder.production_type.is_not(None), WorkOrder.queue_position.is_not(None))
    ).all()
    duplicates = [
        position
        for position, count in Counter(order.queue_position for order in planned_orders if order.queue_position is not None).items()
        if count > 1
    ]
    assert not duplicates, f"Duplicate planned queue positions detected: {duplicates}"


def assert_incomplete_orders_cannot_enter_queue(db_session: Session) -> None:
    queued_incomplete = db_session.scalars(
        select(WorkOrder).where(
            WorkOrder.production_type.is_not(None),
            WorkOrder.queue_position.is_not(None),
            (WorkOrder.is_incomplete_on_arrival.is_(True) | (WorkOrder.status == WorkOrderStatus.INCOMPLETE)),
        )
    ).all()
    assert not queued_incomplete, f"Incomplete work orders entered the queue: {[order.id for order in queued_incomplete]}"


def assert_planned_orders_have_valid_intake_data(db_session: Session) -> None:
    planned_orders = db_session.scalars(
        select(WorkOrder).where(WorkOrder.production_type.is_not(None), WorkOrder.queue_position.is_not(None))
    ).all()

    invalid_planned_orders: list[int] = []
    for work_order in planned_orders:
        try:
            WorkOrderCreate.model_validate(
                {
                    "title": work_order.title,
                    "total_quantity": work_order.total_quantity,
                    "description": work_order.description,
                    "customer_name": work_order.customer_name,
                    "ral_code": work_order.ral_code,
                    "paint_producer": work_order.paint_producer,
                    "coating_type": work_order.coating_type,
                    "received_date": work_order.received_date,
                    "planned_pickup_date": work_order.planned_pickup_date,
                    "total_area_m2": work_order.total_area_m2,
                    "is_incomplete_on_arrival": work_order.is_incomplete_on_arrival,
                    "profiles_quantity": work_order.profiles_quantity,
                    "profiles_to_count": work_order.profiles_to_count,
                    "accessories_quantity": work_order.accessories_quantity,
                    "accessories_to_count": work_order.accessories_to_count,
                    "notes": work_order.notes,
                }
            )
        except Exception:
            invalid_planned_orders.append(work_order.id)

    assert not invalid_planned_orders, f"Planned work orders contain invalid intake data: {invalid_planned_orders}"


def assert_completed_quantity_within_total(db_session: Session) -> None:
    work_orders = db_session.scalars(select(WorkOrder)).all()
    invalid = [order.id for order in work_orders if order.completed_quantity > order.total_quantity]
    assert not invalid, f"Orders exceeded total quantity: {invalid}"


def assert_ready_only_when_fully_complete(db_session: Session) -> None:
    process_service = ProcessService(ProcessRepository(db_session))
    work_orders = db_session.scalars(
        select(WorkOrder).options(selectinload(WorkOrder.quantity_batches), selectinload(WorkOrder.correction_orders))
    ).all()

    invalid_ready: list[int] = []
    for work_order in work_orders:
        if process_service.get_display_status(work_order) != ProcessDisplayStatus.READY:
            continue
        has_open_correction = any(process_service.get_display_status(child) != ProcessDisplayStatus.READY for child in work_order.correction_orders)
        if (
            work_order.completed_quantity != work_order.total_quantity
            or work_order.current_active_quantity != 0
            or has_open_correction
        ):
            invalid_ready.append(work_order.id)

    assert not invalid_ready, f"READY orders violate completion invariants: {invalid_ready}"


def assert_no_broken_parent_child_state(db_session: Session) -> None:
    work_orders = db_session.scalars(select(WorkOrder)).all()
    by_id = {work_order.id: work_order for work_order in work_orders}
    broken: list[int] = []

    for work_order in work_orders:
        if work_order.parent_order_id is not None:
            if not work_order.is_correction or work_order.parent_order_id not in by_id or work_order.parent_order_id == work_order.id:
                broken.append(work_order.id)
        if work_order.is_correction and work_order.parent_order_id is None:
            broken.append(work_order.id)

    assert not broken, f"Broken correction parent/child state detected: {broken}"


def assert_no_duplicate_direct_correction_children(db_session: Session) -> None:
    work_orders = db_session.scalars(select(WorkOrder).options(selectinload(WorkOrder.correction_orders))).all()
    duplicated_parent_ids = [
        work_order.id
        for work_order in work_orders
        if not work_order.is_correction and len(work_order.correction_orders) > 1
    ]
    assert not duplicated_parent_ids, f"Duplicate direct correction children detected for parents: {duplicated_parent_ids}"


def assert_parent_child_quantities_conserved(db_session: Session) -> None:
    process_service = ProcessService(ProcessRepository(db_session))
    work_orders = db_session.scalars(
        select(WorkOrder).options(selectinload(WorkOrder.correction_orders), selectinload(WorkOrder.quantity_batches))
    ).all()

    invalid_quantity_relationships: list[int] = []
    for work_order in work_orders:
        child_total = sum(child.total_quantity for child in work_order.correction_orders)
        if child_total > work_order.total_quantity:
            invalid_quantity_relationships.append(work_order.id)
            continue

        if work_order.correction_orders and work_order.current_active_quantity == 0:
            represented_quantity = (
                work_order.completed_quantity
                + process_service.get_waiting_ok_quantity(work_order)
                + process_service.get_pending_correction_quantity(work_order)
            )
            if represented_quantity != work_order.total_quantity:
                invalid_quantity_relationships.append(work_order.id)

    assert not invalid_quantity_relationships, (
        f"Parent/child quantities are not conserved for work orders: {invalid_quantity_relationships}"
    )


def assert_ready_not_set_while_correction_open(db_session: Session) -> None:
    process_service = ProcessService(ProcessRepository(db_session))
    work_orders = db_session.scalars(select(WorkOrder).options(selectinload(WorkOrder.correction_orders))).all()

    invalid_ready: list[int] = []
    for work_order in work_orders:
        if process_service.get_display_status(work_order) != ProcessDisplayStatus.READY:
            continue
        if any(process_service.get_display_status(child) != ProcessDisplayStatus.READY for child in work_order.correction_orders):
            invalid_ready.append(work_order.id)

    assert not invalid_ready, f"READY set while correction child still open for parents: {invalid_ready}"


def assert_single_active_hanging_and_automatic_line(db_session: Session) -> None:
    process_service = ProcessService(ProcessRepository(db_session))
    work_orders = db_session.scalars(
        select(WorkOrder).options(selectinload(WorkOrder.stage_states), selectinload(WorkOrder.quantity_batches))
    ).all()

    active_hanging_ids: list[int] = []
    active_automatic_line_ids: list[int] = []

    for work_order in work_orders:
        hanging_state = next((stage for stage in work_order.stage_states if stage.stage.value == "HANGING"), None)
        packing_state = next((stage for stage in work_order.stage_states if stage.stage.value == "PACKING"), None)
        has_active_hanging_batch = any(
            batch.is_active
            and batch.current_stage is not None
            and batch.current_stage.value == "HANGING"
            and batch.current_stage_status is not None
            and batch.current_stage_status.value == "IN_PROGRESS"
            for batch in work_order.quantity_batches
        )
        has_active_packing_batch = any(
            batch.is_active
            and batch.current_stage is not None
            and batch.current_stage.value == "PACKING"
            and batch.current_stage_status is not None
            and batch.current_stage_status.value == "IN_PROGRESS"
            for batch in work_order.quantity_batches
        )

        if hanging_state is not None and (hanging_state.status.value == "IN_PROGRESS" or has_active_hanging_batch):
            active_hanging_ids.append(work_order.id)

        if work_order.production_type is not None and work_order.production_type.value == "AUTOMATIC":
            occupies_automatic_line = (
                hanging_state is not None
                and packing_state is not None
                and hanging_state.status.value == "IN_PROGRESS"
                and packing_state.status.value != "DONE"
            ) or has_active_hanging_batch or has_active_packing_batch
            if occupies_automatic_line:
                active_automatic_line_ids.append(work_order.id)

        _ = process_service.get_display_status(work_order)

    assert len(active_hanging_ids) <= 1, f"More than one active hanging job detected: {active_hanging_ids}"
    assert len(active_automatic_line_ids) <= 1, f"More than one automatic-line job detected: {active_automatic_line_ids}"


def assert_global_invariants(db_session: Session, events: list[ChaosEvent]) -> None:
    assert_no_raw_500s(events)
    assert_no_duplicate_queue_positions(db_session)
    assert_incomplete_orders_cannot_enter_queue(db_session)
    assert_planned_orders_have_valid_intake_data(db_session)
    assert_completed_quantity_within_total(db_session)
    assert_ready_only_when_fully_complete(db_session)
    assert_no_broken_parent_child_state(db_session)
    assert_no_duplicate_direct_correction_children(db_session)
    assert_parent_child_quantities_conserved(db_session)
    assert_ready_not_set_while_correction_open(db_session)
    assert_single_active_hanging_and_automatic_line(db_session)
