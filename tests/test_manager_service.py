from datetime import date
import json

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.audit.context import StationContext
from app.audit.models import AuditEvent
from app.manager.repository import ManagerRepository
from app.manager.schemas import WorkOrderPlanAssignRequest, WorkOrderQueueReorderBatchRequest, WorkOrderQueueReorderRequest
from app.manager.service import ManagerService
from app.process.enums import CoatingType, ProductionType
from app.shared.enums import StationId
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import WorkOrderCreate
from app.work_orders.service import WorkOrderService


def build_work_order_payload(title: str) -> WorkOrderCreate:
    return WorkOrderCreate(
        title=title,
        coating_type=CoatingType.RAL,
        total_quantity=10,
        customer_name="ACME",
        ral_code="RAL 7016",
        paint_producer="AkzoNobel",
        received_date=date(2026, 5, 27),
        profiles_quantity=10,
        accessories_quantity=0,
    )


def build_services(db_session: Session) -> tuple[WorkOrderService, ManagerService, ManagerRepository]:
    work_order_repository = WorkOrderRepository(db_session)
    manager_repository = ManagerRepository(db_session)
    return WorkOrderService(work_order_repository), ManagerService(manager_repository), manager_repository


def test_assign_plan_records_manager_audit_event(db_session: Session) -> None:
    work_order_service, manager_service, _ = build_services(db_session)
    created = work_order_service.create_work_order(build_work_order_payload("Audit plan"))

    manager_service.assign_plan(
        created.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
        station_context=StationContext(station_id=StationId.MANAGER),
    )

    event = db_session.scalar(select(AuditEvent).where(AuditEvent.event_type == "manager.plan_assigned"))

    assert event is not None
    assert event.station_id == StationId.MANAGER
    assert event.work_order_id == created.id
    assert event.target_type == "work_order"
    assert event.target_id == created.id
    assert json.loads(event.details_json or "{}") == {
        "production_type": "MANUAL",
        "queue_position": 1,
    }


def test_reorder_queue_swaps_positions_under_sqlite_unique_index(db_session: Session) -> None:
    db_session.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_work_orders_queue_position ON work_orders(queue_position) WHERE queue_position IS NOT NULL"
        )
    )
    db_session.commit()

    work_order_service, manager_service, manager_repository = build_services(db_session)

    first = work_order_service.create_work_order(build_work_order_payload("Queue swap 1"))
    second = work_order_service.create_work_order(build_work_order_payload("Queue swap 2"))
    third = work_order_service.create_work_order(build_work_order_payload("Queue swap 3"))

    manager_service.assign_plan(
        first.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=1),
    )
    manager_service.assign_plan(
        second.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=2),
    )
    manager_service.assign_plan(
        third.id,
        WorkOrderPlanAssignRequest(production_type=ProductionType.MANUAL, queue_position=3),
    )

    queue_revision = manager_repository.get_planned_queue_revision()
    assert queue_revision is not None

    reordered = manager_service.reorder_queue(
        WorkOrderQueueReorderBatchRequest(
            queue_revision=queue_revision,
            items=[
                WorkOrderQueueReorderRequest(work_order_id=second.id, queue_position=1),
                WorkOrderQueueReorderRequest(work_order_id=first.id, queue_position=2),
                WorkOrderQueueReorderRequest(work_order_id=third.id, queue_position=3),
            ],
        )
    )

    assert [(item.id, item.queue_position) for item in reordered] == [
        (second.id, 1),
        (first.id, 2),
        (third.id, 3),
    ]