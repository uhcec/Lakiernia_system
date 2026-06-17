"""Single packing-station exclusivity (WORKFLOW.md / validation-checklist #9).

Only one work order may be physically *started* at packing at a time. The ``PACKING`` resource
lock is the operator's claim, taken by ``start_packing`` (and defensively at completion) and
released once packing leaves IN_PROGRESS. Automatic orders that are only waiting at packing must
not hold the claim.
"""

from sqlalchemy.orm import Session

import pytest

from app.manager.schemas import WorkOrderPlanAssignRequest
from app.process.enums import ProcessStage, ProductionType, StageStatus
from app.process.models import ProcessResourceLock
from app.process.service import ProcessService
from app.shared.exceptions import InvalidProcessStageTransitionError

from tests.test_process_service import (
    advance_to_packing,
    build_services,
    complete_packing,
    create_ral_work_order,
)

PACKING_KEY = ProcessService.PACKING_RESOURCE_KEY


def _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, title: str, position: int):
    created = create_ral_work_order(work_order_service, title)
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=position),
    )
    advance_to_packing(process_service, created.id)
    return created


def _packing_lock_owner(process_repository) -> int | None:
    lock = process_repository.get_resource_lock(PACKING_KEY)
    return lock.work_order_id if lock is not None else None


def test_start_packing_claims_station_and_flags_being_packed(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    order = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Claim A", 1)

    response = process_service.start_packing(order.id)

    assert response.is_being_packed is True
    assert _packing_lock_owner(process_repository) == order.id


def test_second_order_cannot_start_packing_while_station_claimed(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    first = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Busy A", 1)
    second = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Busy B", 2)

    process_service.start_packing(first.id)

    with pytest.raises(InvalidProcessStageTransitionError) as excinfo:
        process_service.start_packing(second.id)

    assert "zaj" in str(excinfo.value).lower()  # "zajęte"
    assert _packing_lock_owner(process_repository) == first.id


def test_completing_packing_releases_claim_for_next_order(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    first = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Release A", 1)
    second = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Release B", 2)

    process_service.start_packing(first.id)
    complete_packing(process_service, first.id, ok_quantity=100, correction_quantity=0)

    assert _packing_lock_owner(process_repository) is None

    response = process_service.start_packing(second.id)
    assert response.is_being_packed is True
    assert _packing_lock_owner(process_repository) == second.id


def test_complete_packing_blocked_while_other_order_holds_claim(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    first = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Guard A", 1)
    second = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Guard B", 2)

    process_service.start_packing(first.id)

    with pytest.raises(InvalidProcessStageTransitionError):
        complete_packing(process_service, second.id, ok_quantity=100, correction_quantity=0)

    # First order's claim is untouched and it can still complete normally.
    assert _packing_lock_owner(process_repository) == first.id
    complete_packing(process_service, first.id, ok_quantity=100, correction_quantity=0)
    assert _packing_lock_owner(process_repository) is None


def test_complete_packing_without_prior_claim_still_works_and_leaves_no_lock(db_session: Session) -> None:
    # Back-compat: direct completion (no explicit start) auto-claims for the duration and releases.
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    order = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Direct", 1)

    complete_packing(process_service, order.id, ok_quantity=100, correction_quantity=0)

    assert _packing_lock_owner(process_repository) is None


def test_start_packing_is_idempotent_for_same_order(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    order = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Idempotent", 1)

    process_service.start_packing(order.id)
    response = process_service.start_packing(order.id)

    assert response.is_being_packed is True
    assert _packing_lock_owner(process_repository) == order.id


def test_start_packing_recovers_stale_claim_from_finished_owner(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    finished = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Stale", 1)
    waiting = _plan_and_advance_manual_to_packing(work_order_service, process_service, manager_service, "Fresh", 2)

    # Finish the first order's packing, then forge a stale lock owned by the now-finished order.
    complete_packing(process_service, finished.id, ok_quantity=100, correction_quantity=0)
    db_session.add(ProcessResourceLock(resource_key=PACKING_KEY, work_order_id=finished.id))
    db_session.flush()

    response = process_service.start_packing(waiting.id)

    assert response.is_being_packed is True
    assert _packing_lock_owner(process_repository) == waiting.id


def test_automatic_order_waiting_at_packing_does_not_hold_claim(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    created = create_ral_work_order(work_order_service, "Auto waiting")
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=1),
    )
    advance_to_packing(process_service, created.id)

    # Automatic packing is IN_PROGRESS implicitly after hanging finishes, but nobody has claimed it.
    work_order = process_service.get_work_order_process(created.id)
    packing_state = next(s for s in work_order.stage_states if s.stage == ProcessStage.PACKING)
    assert packing_state.status == StageStatus.IN_PROGRESS
    assert _packing_lock_owner(process_repository) is None

    items = process_service.list_stage_work_orders(ProcessStage.PACKING)
    matching = [item for item in items if item.id == created.id and item.stage_status.stage == ProcessStage.PACKING]
    assert matching, "automatic order should be visible at packing once hanging is done"
    assert all(item.is_being_packed is False for item in matching)

    # Explicitly claiming it then flags it as being packed.
    response = process_service.start_packing(created.id)
    assert response.is_being_packed is True
    assert _packing_lock_owner(process_repository) == created.id
