"""Service/API-level tests for the painting auto-scheduler (NA33): config CRUD + proposal."""

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.context import StationContext
from app.audit.models import AuditEvent
from app.manager.enums import DEFAULT_RULE_ORDER, ScheduleRuleKey
from app.manager.repository import ManagerRepository
from app.manager.schemas import (
    ScheduleRuleConfigUpdate,
    ScheduleRuleConfigUpdateItem,
    WorkOrderPlanAssignRequest,
)
from app.manager.service import ManagerService
from app.process.enums import CoatingType, ProductionType
from app.shared.enums import StationId
from app.shared.exceptions import StationActionForbiddenError
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import WorkOrderCreate
from app.work_orders.service import WorkOrderService

MANAGER = StationContext(station_id=StationId.MANAGER)


def _payload(title: str, ral_code: str, pickup: date | None = None) -> WorkOrderCreate:
    return WorkOrderCreate(
        title=title,
        coating_type=CoatingType.RAL,
        total_quantity=10,
        customer_name="ACME",
        ral_code=ral_code,
        paint_code="P-1",
        paint_producer="AkzoNobel",
        received_date=date(2026, 5, 27),
        planned_pickup_date=pickup or date(2026, 6, 3),
        total_area_m2=24.0,
        profiles_quantity=10,
        accessories_quantity=0,
    )


def _build(db_session: Session) -> tuple[WorkOrderService, ManagerService]:
    return (
        WorkOrderService(WorkOrderRepository(db_session)),
        ManagerService(ManagerRepository(db_session)),
    )


def _plan_automatic(work_order_service: WorkOrderService, manager_service: ManagerService, payload: WorkOrderCreate) -> int:
    created = work_order_service.create_work_order(payload)
    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.AUTOMATIC),
        station_context=MANAGER,
    )
    return created.id


def test_get_schedule_config_defaults_to_all_enabled_catalog_order(db_session: Session) -> None:
    _, manager_service = _build(db_session)
    config = manager_service.get_schedule_config(ProductionType.AUTOMATIC, station_context=MANAGER)
    assert [item.key for item in config.rules] == list(DEFAULT_RULE_ORDER)
    assert all(item.enabled for item in config.rules)
    assert all(item.label and item.description for item in config.rules)


def test_update_schedule_config_persists_and_audits(db_session: Session) -> None:
    _, manager_service = _build(db_session)
    payload = ScheduleRuleConfigUpdate(
        rules=[
            ScheduleRuleConfigUpdateItem(key=ScheduleRuleKey.DEADLINE, enabled=True),
            ScheduleRuleConfigUpdateItem(key=ScheduleRuleKey.COLOUR, enabled=True),
            ScheduleRuleConfigUpdateItem(key=ScheduleRuleKey.CHANGEOVER, enabled=False),
        ]
    )
    manager_service.update_schedule_config(ProductionType.AUTOMATIC, payload, station_context=MANAGER)

    reloaded = manager_service.get_schedule_config(ProductionType.AUTOMATIC, station_context=MANAGER)
    assert [(item.key, item.enabled) for item in reloaded.rules] == [
        (ScheduleRuleKey.DEADLINE, True),
        (ScheduleRuleKey.COLOUR, True),
        (ScheduleRuleKey.CHANGEOVER, False),
    ]
    event = db_session.scalar(
        select(AuditEvent).where(AuditEvent.event_type == "manager.schedule_config_updated")
    )
    assert event is not None and event.station_id == StationId.MANAGER


def test_update_schedule_config_rejects_incomplete_rule_set() -> None:
    with pytest.raises(ValueError):
        ScheduleRuleConfigUpdate(
            rules=[ScheduleRuleConfigUpdateItem(key=ScheduleRuleKey.COLOUR, enabled=True)]
        )


def test_proposal_groups_colours_and_reports_reduction(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    # Plan in interleaved colour order A,B,A,B → 3 colour changes in the current queue.
    a1 = _plan_automatic(work_order_service, manager_service, _payload("A1", "RAL 1000"))
    b1 = _plan_automatic(work_order_service, manager_service, _payload("B1", "RAL 2000"))
    a2 = _plan_automatic(work_order_service, manager_service, _payload("A2", "RAL 1000"))
    b2 = _plan_automatic(work_order_service, manager_service, _payload("B2", "RAL 2000"))

    proposal = manager_service.propose_auto_schedule(ProductionType.AUTOMATIC, station_context=MANAGER)

    proposed_ids = [order.id for order in proposal.proposed_order]
    assert proposed_ids == [a1, a2, b1, b2]  # colours clustered (default priority: colour first)
    assert proposal.current_colour_changeovers == 3
    assert proposal.proposed_colour_changeovers == 1
    assert proposal.colour_changeover_reduction == 2
    assert proposal.queue_revision is not None


def test_proposal_excludes_other_line_and_is_manager_gated(db_session: Session) -> None:
    work_order_service, manager_service = _build(db_session)
    _plan_automatic(work_order_service, manager_service, _payload("Auto", "RAL 1000"))
    # A manual order must not appear in the AUTOMATIC proposal.
    manual = work_order_service.create_work_order(_payload("Manual", "RAL 3000"))
    manager_service.assign_plan(
        manual.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL),
        station_context=MANAGER,
    )

    proposal = manager_service.propose_auto_schedule(ProductionType.AUTOMATIC, station_context=MANAGER)
    assert manual.id not in [order.id for order in proposal.proposed_order]

    with pytest.raises(StationActionForbiddenError):
        manager_service.propose_auto_schedule(
            ProductionType.AUTOMATIC, station_context=StationContext(station_id=StationId.OFFICE)
        )
