"""Explicit end-to-end coverage of the WORKFLOW.md scenario matrix S01-S12.

Each test drives one matrix row to its terminal state and asserts the documented outcome (final
status READY, completed == total, no active quantity). This pins every row of the matrix to code so a
future change that breaks a scenario fails loudly here, mapped 1:1 to the spec table.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.manager.schemas import WorkOrderPlanAssignRequest
from app.process.enums import CoatingType, ProcessStage, ProductionType, StageStatus
from app.work_orders.schemas import WorkOrderCreate

from tests.test_process_service import (
    advance_to_packing,
    build_services,
    complete_packing,
)


Q = 10


def _create(work_order_service, title: str, coating: CoatingType):
    return work_order_service.create_work_order(
        WorkOrderCreate(
            title=title,
            coating_type=coating,
            total_quantity=Q,
            customer_name="ACME",
            ral_code="RAL 7016" if coating == CoatingType.RAL else "D-200",
            paint_code="P-7016",
            paint_producer="AkzoNobel",
            received_date=date(2026, 5, 27),
            total_area_m2=24.0,
            profiles_quantity=Q,
            accessories_quantity=0,
        )
    )


def _plan(manager_service, work_order_id: int, production_type: ProductionType, position: int = 1):
    manager_service.assign_plan(
        work_order_id, WorkOrderPlanAssignRequest(production_type=production_type, queue_position=position)
    )


def _finish_root_decoral(process_service, process_repository, root_id: int):
    """Finish the root's Decoral pass until READY.

    Handles both shapes: a tracked Decoral batch (correction merges return OK pieces this way) and the
    plain non-batch Decoral stage (a no-correction DECORAL order). Loops because correction merges can
    leave more than one batch.
    """
    while True:
        root = process_repository.get_work_order_with_stage_states(root_id)
        batch = next(
            (
                b
                for b in root.quantity_batches
                if b.is_active and b.current_stage == ProcessStage.DECORAL_PRODUCTION
            ),
            None,
        )
        if batch is not None:
            process_service.start_stage(root_id, ProcessStage.DECORAL_PRODUCTION, batch_id=batch.id)
            process_service.complete_decoral_production(
                root_id, ok_quantity=batch.quantity, correction_quantity=0, batch_id=batch.id
            )
            continue
        if process_service.get_display_status(root).value == "DECORAL_PRODUCTION":
            process_service.transition_stage(root_id, ProcessStage.DECORAL_PRODUCTION, StageStatus.IN_PROGRESS)
            process_service.finish_stage(root_id, ProcessStage.DECORAL_PRODUCTION)
            continue
        return


def _assert_ready(process_service, process_repository, work_order_id: int):
    work_order = process_repository.get_work_order_with_stage_states(work_order_id)
    assert work_order is not None
    assert process_service.get_display_status(work_order).value == "READY"
    assert work_order.completed_quantity == work_order.total_quantity == Q
    assert work_order.current_active_quantity == 0


def _latest_correction_child(work_order_repository, parent_id: int, exclude: set[int]):
    return next(
        wo
        for wo in work_order_repository.list(limit=50, offset=0)
        if wo.is_correction and wo.parent_order_id == parent_id and wo.id not in exclude
    )


# --- No correction ---------------------------------------------------------------------------------

def test_s01_ral_manual_no_correction(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    order = _create(work_order_service, "S01", CoatingType.RAL)
    _plan(manager_service, order.id, ProductionType.MANUAL)
    advance_to_packing(process_service, order.id)
    complete_packing(process_service, order.id, ok_quantity=Q, correction_quantity=0)
    _assert_ready(process_service, process_repository, order.id)


def test_s02_ral_automatic_no_correction(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    order = _create(work_order_service, "S02", CoatingType.RAL)
    _plan(manager_service, order.id, ProductionType.AUTOMATIC)
    advance_to_packing(process_service, order.id)
    complete_packing(process_service, order.id, ok_quantity=Q, correction_quantity=0)
    _assert_ready(process_service, process_repository, order.id)


def test_s03_decoral_manual_no_correction(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    order = _create(work_order_service, "S03", CoatingType.DECORAL)
    _plan(manager_service, order.id, ProductionType.MANUAL)
    advance_to_packing(process_service, order.id)
    complete_packing(process_service, order.id, ok_quantity=Q, correction_quantity=0)  # -> DECORAL pass
    _finish_root_decoral(process_service, process_repository, order.id)
    _assert_ready(process_service, process_repository, order.id)


def test_s04_decoral_automatic_no_correction(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    order = _create(work_order_service, "S04", CoatingType.DECORAL)
    _plan(manager_service, order.id, ProductionType.AUTOMATIC)
    advance_to_packing(process_service, order.id)
    complete_packing(process_service, order.id, ok_quantity=Q, correction_quantity=0)
    _finish_root_decoral(process_service, process_repository, order.id)
    _assert_ready(process_service, process_repository, order.id)


# --- RAL correction (in-place batch reset, no child) ----------------------------------------------

def _ral_correction_round(work_order_service, process_service, manager_service, process_repository, production_type):
    order = _create(work_order_service, "RALc", CoatingType.RAL)
    _plan(manager_service, order.id, production_type)
    advance_to_packing(process_service, order.id)
    # 7 OK, 3 to correction -> same order resets to planning with a CORRECTION batch (no child).
    complete_packing(process_service, order.id, ok_quantity=7, correction_quantity=3)
    refreshed = process_repository.get_work_order_with_stage_states(order.id)
    assert refreshed.production_type is None  # reset to planning
    assert not any(wo.is_correction for wo in work_order_service.repository.list(limit=50, offset=0))  # no child
    # Re-plan the correction round and finish it fully.
    _plan(manager_service, order.id, production_type, position=2)
    advance_to_packing(process_service, order.id)
    complete_packing(process_service, order.id, ok_quantity=3, correction_quantity=0)
    return order


def test_s05_ral_manual_correction(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    order = _ral_correction_round(work_order_service, process_service, manager_service, process_repository, ProductionType.MANUAL)
    _assert_ready(process_service, process_repository, order.id)


def test_s06_ral_automatic_correction(db_session: Session) -> None:
    work_order_service, process_service, manager_service, _, process_repository = build_services(db_session)
    order = _ral_correction_round(work_order_service, process_service, manager_service, process_repository, ProductionType.AUTOMATIC)
    _assert_ready(process_service, process_repository, order.id)


def test_s09_ral_manual_multi_round_correction(db_session: Session) -> None:
    work_order_service, process_service, manager_service, work_order_repository, process_repository = build_services(db_session)
    order = _create(work_order_service, "S09", CoatingType.RAL)
    _plan(manager_service, order.id, ProductionType.MANUAL)
    advance_to_packing(process_service, order.id)
    complete_packing(process_service, order.id, ok_quantity=7, correction_quantity=3)
    _plan(manager_service, order.id, ProductionType.MANUAL, position=2)
    advance_to_packing(process_service, order.id)
    complete_packing(process_service, order.id, ok_quantity=2, correction_quantity=1)  # 2nd round
    _plan(manager_service, order.id, ProductionType.MANUAL, position=3)
    advance_to_packing(process_service, order.id)
    complete_packing(process_service, order.id, ok_quantity=1, correction_quantity=0)
    # Each round was a new CORRECTION batch on the same order; no child orders.
    assert not any(wo.is_correction for wo in work_order_repository.list(limit=50, offset=0))
    _assert_ready(process_service, process_repository, order.id)


def test_s10_ral_automatic_multi_round_correction(db_session: Session) -> None:
    work_order_service, process_service, manager_service, work_order_repository, process_repository = build_services(db_session)
    order = _create(work_order_service, "S10", CoatingType.RAL)
    _plan(manager_service, order.id, ProductionType.AUTOMATIC)
    advance_to_packing(process_service, order.id)
    complete_packing(process_service, order.id, ok_quantity=7, correction_quantity=3)
    _plan(manager_service, order.id, ProductionType.AUTOMATIC, position=2)
    advance_to_packing(process_service, order.id)
    complete_packing(process_service, order.id, ok_quantity=2, correction_quantity=1)
    _plan(manager_service, order.id, ProductionType.AUTOMATIC, position=3)
    advance_to_packing(process_service, order.id)
    complete_packing(process_service, order.id, ok_quantity=1, correction_quantity=0)
    assert not any(wo.is_correction for wo in work_order_repository.list(limit=50, offset=0))
    _assert_ready(process_service, process_repository, order.id)


# --- DECORAL correction (child order; OK returns to the root's single Decoral pass) ----------------

def _decoral_correction(work_order_service, process_service, manager_service, work_order_repository, process_repository, child_production_type):
    parent = _create(work_order_service, "DECc", CoatingType.DECORAL)
    _plan(manager_service, parent.id, ProductionType.MANUAL)
    advance_to_packing(process_service, parent.id)
    # 8 OK continue on the root Decoral pass; 3... use 8/2 so child=2.
    complete_packing(process_service, parent.id, ok_quantity=8, correction_quantity=2)
    child = _latest_correction_child(work_order_repository, parent.id, exclude=set())
    _plan(manager_service, child.id, child_production_type, position=2)
    advance_to_packing(process_service, child.id)
    complete_packing(process_service, child.id, ok_quantity=2, correction_quantity=0)  # returns to root Decoral
    _finish_root_decoral(process_service, process_repository, parent.id)
    return parent


def test_s07_decoral_manual_correction(db_session: Session) -> None:
    work_order_service, process_service, manager_service, work_order_repository, process_repository = build_services(db_session)
    parent = _decoral_correction(work_order_service, process_service, manager_service, work_order_repository, process_repository, ProductionType.MANUAL)
    _assert_ready(process_service, process_repository, parent.id)


def test_s08_decoral_automatic_correction(db_session: Session) -> None:
    work_order_service, process_service, manager_service, work_order_repository, process_repository = build_services(db_session)
    parent = _decoral_correction(work_order_service, process_service, manager_service, work_order_repository, process_repository, ProductionType.AUTOMATIC)
    _assert_ready(process_service, process_repository, parent.id)


def _decoral_multi_round(work_order_service, process_service, manager_service, work_order_repository, process_repository, child_production_type):
    parent = _create(work_order_service, "DECm", CoatingType.DECORAL)
    _plan(manager_service, parent.id, ProductionType.MANUAL)
    advance_to_packing(process_service, parent.id)
    complete_packing(process_service, parent.id, ok_quantity=7, correction_quantity=3)  # 7 to root Decoral
    child = _latest_correction_child(work_order_repository, parent.id, exclude=set())
    _plan(manager_service, child.id, child_production_type, position=2)
    advance_to_packing(process_service, child.id)
    complete_packing(process_service, child.id, ok_quantity=2, correction_quantity=1)  # 2 return, 1 -> new child
    second = _latest_correction_child(work_order_repository, parent.id, exclude={child.id})
    _plan(manager_service, second.id, child_production_type, position=3)
    advance_to_packing(process_service, second.id)
    complete_packing(process_service, second.id, ok_quantity=1, correction_quantity=0)  # last piece returns
    _finish_root_decoral(process_service, process_repository, parent.id)
    return parent


def test_s11_decoral_manual_multi_round_correction(db_session: Session) -> None:
    work_order_service, process_service, manager_service, work_order_repository, process_repository = build_services(db_session)
    parent = _decoral_multi_round(work_order_service, process_service, manager_service, work_order_repository, process_repository, ProductionType.MANUAL)
    _assert_ready(process_service, process_repository, parent.id)


def test_s12_decoral_automatic_multi_round_correction(db_session: Session) -> None:
    work_order_service, process_service, manager_service, work_order_repository, process_repository = build_services(db_session)
    parent = _decoral_multi_round(work_order_service, process_service, manager_service, work_order_repository, process_repository, ProductionType.AUTOMATIC)
    _assert_ready(process_service, process_repository, parent.id)
