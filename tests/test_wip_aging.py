"""Live WIP-aging ("stuck orders") view.

Lists work orders currently IN_PROGRESS (from live stage states) ordered by how long they have sat
in their current stage, with the durable age timestamp taken from the stage-transition log. Cohort
is live state, so a correction reset cannot leave a stale "stuck" row.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

import pytest

from app.audit.context import StationContext
from app.manager.repository import ManagerRepository
from app.manager.schemas import WorkOrderPlanAssignRequest
from app.manager.service import ManagerService
from app.process.enums import CoatingType, ProcessStage, ProductionType, StageStatus
from app.process.models import StageTransitionEvent, WorkOrderStageState
from app.shared.enums import StationId
from app.shared.exceptions import StationActionForbiddenError
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import WorkOrderCreate
from app.work_orders.service import WorkOrderService


MANAGER = StationContext(station_id=StationId.MANAGER)


def _services(db_session: Session):
    return (
        WorkOrderService(WorkOrderRepository(db_session)),
        ManagerService(ManagerRepository(db_session)),
    )


def _create(work_order_service: WorkOrderService, title: str, coating_type: CoatingType = CoatingType.RAL):
    return work_order_service.create_work_order(
        WorkOrderCreate(
            title=title,
            coating_type=coating_type,
            total_quantity=100,
            customer_name="ACME",
            ral_code="RAL 7016",
            paint_code="P-7016",
            paint_producer="AkzoNobel",
            received_date=date(2026, 5, 27),
            planned_pickup_date=date(2026, 6, 3),
            total_area_m2=24.0,
            profiles_quantity=100,
            accessories_quantity=0,
        )
    )


def _set_stage_in_progress(db_session: Session, work_order_id: int, stage: ProcessStage) -> None:
    state = db_session.execute(
        select(WorkOrderStageState).where(
            WorkOrderStageState.work_order_id == work_order_id,
            WorkOrderStageState.stage == stage,
        )
    ).scalar_one()
    state.status = StageStatus.IN_PROGRESS
    db_session.flush()


def _log_in_progress(db_session: Session, work_order_id: int, stage: ProcessStage, occurred_at: datetime) -> None:
    db_session.add(
        StageTransitionEvent(
            work_order_id=work_order_id,
            batch_id=None,
            stage=stage,
            status=StageStatus.IN_PROGRESS,
            station_id=StationId.SYSTEM,
            occurred_at=occurred_at,
        )
    )
    db_session.flush()


def test_wip_aging_lists_in_progress_orders_sorted_by_age(db_session: Session) -> None:
    work_order_service, manager_service = _services(db_session)

    older = _create(work_order_service, "Stuck older")
    newer = _create(work_order_service, "Stuck newer")
    manager_service.assign_plan(
        older.id, WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1), station_context=MANAGER
    )
    manager_service.assign_plan(
        newer.id, WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=2), station_context=MANAGER
    )

    _set_stage_in_progress(db_session, older.id, ProcessStage.PRODUCTION)
    _set_stage_in_progress(db_session, newer.id, ProcessStage.PRODUCTION)

    now = datetime(2026, 6, 12, 12, 0, tzinfo=UTC)
    _log_in_progress(db_session, older.id, ProcessStage.PRODUCTION, now - timedelta(hours=8))
    _log_in_progress(db_session, newer.id, ProcessStage.PRODUCTION, now - timedelta(hours=1))

    stats = manager_service.get_work_in_progress_aging(station_context=MANAGER, now=now)

    assert [item.order_number for item in stats.items] == [older.order_number, newer.order_number]
    assert stats.items[0].stage == ProcessStage.PRODUCTION
    assert stats.items[0].stage_label == "Produkcja"
    assert stats.items[0].age_seconds == 8 * 3600
    assert stats.items[1].age_seconds == 3600
    assert stats.items[0].production_type == ProductionType.MANUAL
    assert stats.items[0].queue_position == 1


def test_wip_aging_picks_furthest_advanced_in_progress_stage(db_session: Session) -> None:
    # NA42: an automatic order at the line has HANGING and PACKING both IN_PROGRESS (no PRODUCTION
    # stage); the report should surface the furthest-advanced stage (PACKING).
    work_order_service, manager_service = _services(db_session)
    order = _create(work_order_service, "Automatic at line")
    manager_service.assign_plan(
        order.id, WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=1), station_context=MANAGER
    )
    _set_stage_in_progress(db_session, order.id, ProcessStage.HANGING)
    _set_stage_in_progress(db_session, order.id, ProcessStage.PACKING)

    stats = manager_service.get_work_in_progress_aging(station_context=MANAGER)

    matching = [item for item in stats.items if item.order_number == order.order_number]
    assert len(matching) == 1
    assert matching[0].stage == ProcessStage.PACKING


def test_wip_aging_excludes_not_started_orders(db_session: Session) -> None:
    work_order_service, manager_service = _services(db_session)

    in_progress = _create(work_order_service, "Working")
    planned_idle = _create(work_order_service, "Planned but not started")
    manager_service.assign_plan(
        in_progress.id, WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1), station_context=MANAGER
    )
    manager_service.assign_plan(
        planned_idle.id, WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=2), station_context=MANAGER
    )

    _set_stage_in_progress(db_session, in_progress.id, ProcessStage.PRODUCTION)
    # planned_idle has no stage IN_PROGRESS yet.

    stats = manager_service.get_work_in_progress_aging(station_context=MANAGER)

    order_numbers = [item.order_number for item in stats.items]
    assert in_progress.order_number in order_numbers
    assert planned_idle.order_number not in order_numbers


def test_wip_aging_breakdown_counts_by_method_and_coating(db_session: Session) -> None:
    # NA23: the live cohort is also cut two independent ways; each partition's counts sum to len(items).
    work_order_service, manager_service = _services(db_session)
    manual_ral = _create(work_order_service, "Manual RAL", coating_type=CoatingType.RAL)
    auto_decoral = _create(work_order_service, "Automatic decoral", coating_type=CoatingType.DECORAL)
    manager_service.assign_plan(
        manual_ral.id, WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1), station_context=MANAGER
    )
    manager_service.assign_plan(
        auto_decoral.id, WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC, queue_position=2), station_context=MANAGER
    )
    _set_stage_in_progress(db_session, manual_ral.id, ProcessStage.PRODUCTION)
    _set_stage_in_progress(db_session, auto_decoral.id, ProcessStage.PACKING)  # NA42: automatic has no PRODUCTION

    stats = manager_service.get_work_in_progress_aging(station_context=MANAGER)

    method = {seg.key: seg.orders_count for seg in stats.breakdown.by_method}
    coating = {seg.key: seg.orders_count for seg in stats.breakdown.by_coating}
    assert method == {"manual": 1, "automatic": 1}
    assert coating == {"ral_only": 1, "decoral": 1}
    assert sum(method.values()) == len(stats.items)
    assert sum(coating.values()) == len(stats.items)
    by_number = {item.order_number: item for item in stats.items}
    assert by_number[auto_decoral.order_number].coating_type == CoatingType.DECORAL


def test_wip_aging_requires_manager(db_session: Session) -> None:
    _, manager_service = _services(db_session)
    with pytest.raises(StationActionForbiddenError):
        manager_service.get_work_in_progress_aging(station_context=StationContext(station_id=StationId.PACKING))
