"""Packing capacity / slot model (WORKFLOW.md / validation-checklist #9, NA16 + NA22).

Default behavior is single-station exclusivity (one work order packs at a time). An AUTOMATIC order
reserves a packing slot the moment HANGING starts (NA22a), so a manual order cannot take the slot and
block the un-pausable automatic line; a manual operator may *override* to open an additional slot up to
the configured cap N (NA22b). Slots are tracked as ``PACKING:1..N`` resource locks.
"""

from sqlalchemy.orm import Session

import pytest

from app.manager.schemas import WorkOrderPlanAssignRequest
from app.process.enums import ProcessStage, ProductionType, StageStatus
from app.process.models import ProcessResourceLock
from app.shared.exceptions import InvalidProcessStageTransitionError

from tests.test_process_service import (
    advance_to_packing,
    build_services,
    complete_packing,
    create_ral_work_order,
)

PACKING_SLOT_PREFIX = "PACKING:"


def _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, title: str, position: int):
    created = create_ral_work_order(work_order_service, title)
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=position),
    )
    advance_to_packing(process_service, created.id)
    return created


def _slot_owner_ids(process_repository) -> set[int]:
    return {lock.work_order_id for lock in process_repository.list_resource_locks_with_prefix(PACKING_SLOT_PREFIX)}


def test_start_packing_claims_a_slot_and_flags_being_packed(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    order = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Claim A", 1)

    response = process_service.start_packing(order.id)

    assert response.is_being_packed is True
    assert response.holds_packing_slot is True
    assert _slot_owner_ids(process_repository) == {order.id}


def test_second_order_cannot_start_packing_without_override(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    first = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Busy A", 1)
    second = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Busy B", 2)

    process_service.start_packing(first.id)

    with pytest.raises(InvalidProcessStageTransitionError) as excinfo:
        process_service.start_packing(second.id)  # default (no override) requires a free station

    assert "zaj" in str(excinfo.value).lower()
    assert _slot_owner_ids(process_repository) == {first.id}


def test_manual_override_opens_a_second_packing_slot(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    first = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Slot A", 1)
    second = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Slot B", 2)

    process_service.start_packing(first.id)
    response = process_service.start_packing(second.id, override=True)  # default cap N=2

    assert response.is_being_packed is True
    assert _slot_owner_ids(process_repository) == {first.id, second.id}


def test_override_blocked_when_all_slots_full(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    a = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Full A", 1)
    b = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Full B", 2)
    c = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Full C", 3)

    process_service.start_packing(a.id)
    process_service.start_packing(b.id, override=True)  # opens 2nd slot (N=2)

    with pytest.raises(InvalidProcessStageTransitionError) as excinfo:
        process_service.start_packing(c.id, override=True)  # all N=2 slots full

    assert "wszystkie" in str(excinfo.value).lower()
    assert _slot_owner_ids(process_repository) == {a.id, b.id}


def test_packing_slot_capacity_is_configurable(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    a = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Cap A", 1)
    b = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Cap B", 2)

    # Cap of 1 → even an override cannot open a second slot.
    monkeypatch.setattr(process_service, "_packing_slot_count", lambda: 1)
    process_service.start_packing(a.id)
    with pytest.raises(InvalidProcessStageTransitionError):
        process_service.start_packing(b.id, override=True)
    assert _slot_owner_ids(process_repository) == {a.id}


def test_completing_packing_releases_slot_for_next_order(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    first = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Release A", 1)
    second = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Release B", 2)

    process_service.start_packing(first.id)
    complete_packing(process_service, first.id, ok_quantity=100, correction_quantity=0)
    assert _slot_owner_ids(process_repository) == set()

    response = process_service.start_packing(second.id)
    assert response.is_being_packed is True
    assert _slot_owner_ids(process_repository) == {second.id}


def test_complete_packing_blocked_while_other_order_holds_the_only_slot(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    first = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Guard A", 1)
    second = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Guard B", 2)

    monkeypatch.setattr(process_service, "_packing_slot_count", lambda: 1)  # single station
    process_service.start_packing(first.id)

    with pytest.raises(InvalidProcessStageTransitionError):
        complete_packing(process_service, second.id, ok_quantity=100, correction_quantity=0)

    assert _slot_owner_ids(process_repository) == {first.id}
    complete_packing(process_service, first.id, ok_quantity=100, correction_quantity=0)
    assert _slot_owner_ids(process_repository) == set()


def test_complete_packing_without_prior_claim_leaves_no_slot(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    order = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Direct", 1)

    complete_packing(process_service, order.id, ok_quantity=100, correction_quantity=0)

    assert _slot_owner_ids(process_repository) == set()


def test_start_packing_is_idempotent_for_same_order(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    order = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Idempotent", 1)

    process_service.start_packing(order.id)
    response = process_service.start_packing(order.id)

    assert response.is_being_packed is True
    assert _slot_owner_ids(process_repository) == {order.id}


def test_start_packing_recovers_stale_slot_from_finished_owner(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    finished = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Stale", 1)
    waiting = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Fresh", 2)

    monkeypatch.setattr(process_service, "_packing_slot_count", lambda: 1)
    complete_packing(process_service, finished.id, ok_quantity=100, correction_quantity=0)
    # Forge a stale slot owned by the now-finished order.
    db_session.add(ProcessResourceLock(resource_key="PACKING:1", work_order_id=finished.id))
    db_session.flush()

    response = process_service.start_packing(waiting.id)

    assert response.is_being_packed is True
    assert _slot_owner_ids(process_repository) == {waiting.id}


def test_automatic_order_reserves_packing_slot_at_hanging_start(db_session: Session) -> None:
    # NA22a: an automatic order holds a packing slot from hanging start, so a manual order is blocked
    # unless it overrides. advance_to_packing drives surface + hanging for automatic.
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    automatic = create_ral_work_order(work_order_service, "Auto reserve")
    manager_service.assign_plan(
        automatic.id, WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=1)
    )
    advance_to_packing(process_service, automatic.id)

    # The automatic order holds a slot even though packing is only implicitly in progress.
    assert automatic.id in _slot_owner_ids(process_repository)

    manual = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Manual blocked", 2)
    with pytest.raises(InvalidProcessStageTransitionError):
        process_service.start_packing(manual.id)  # blocked by the automatic reservation

    # ...but the manual operator can override to open a second slot.
    process_service.start_packing(manual.id, override=True)
    assert _slot_owner_ids(process_repository) == {automatic.id, manual.id}


def test_automatic_releases_packing_slot_after_completion(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    automatic = create_ral_work_order(work_order_service, "Auto release")
    manager_service.assign_plan(
        automatic.id, WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=1)
    )
    advance_to_packing(process_service, automatic.id)
    assert automatic.id in _slot_owner_ids(process_repository)

    complete_packing(process_service, automatic.id, ok_quantity=100, correction_quantity=0)
    assert _slot_owner_ids(process_repository) == set()
