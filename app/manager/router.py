from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.audit.context import StationContext, get_station_context
from app.database.session import get_db_session
from app.manager.repository import ManagerRepository
from app.manager.schemas import (
    WorkOrderPlanAssignRequest,
    WorkOrderQueuePositionUpdateRequest,
    WorkOrderQueueReorderBatchRequest,
)
from app.manager.service import ManagerService
from app.work_orders.schemas import WorkOrderRead

router = APIRouter(prefix="/manager", tags=["manager-work-orders"])


def get_manager_service(session: Annotated[Session, Depends(get_db_session)]) -> ManagerService:
    repository = ManagerRepository(session)
    return ManagerService(repository)


@router.get("/work-orders/unplanned", response_model=list[WorkOrderRead])
def list_unplanned_work_orders(
    service: Annotated[ManagerService, Depends(get_manager_service)],
) -> list[WorkOrderRead]:
    return service.list_unplanned_work_orders()


@router.get("/work-orders", response_model=list[WorkOrderRead])
def list_planned_work_orders(
    service: Annotated[ManagerService, Depends(get_manager_service)],
) -> list[WorkOrderRead]:
    return service.list_planned_work_orders()


@router.post("/work-orders/{work_order_id}/plan", response_model=WorkOrderRead)
def assign_plan(
    work_order_id: int,
    payload: WorkOrderPlanAssignRequest,
    service: Annotated[ManagerService, Depends(get_manager_service)],
    station_context: Annotated[StationContext, Depends(get_station_context)],
) -> WorkOrderRead:
    return service.assign_plan(work_order_id, payload, station_context=station_context)


@router.patch("/work-orders/{work_order_id}/queue-position", response_model=WorkOrderRead)
def update_queue_position(
    work_order_id: int,
    payload: WorkOrderQueuePositionUpdateRequest,
    service: Annotated[ManagerService, Depends(get_manager_service)],
    station_context: Annotated[StationContext, Depends(get_station_context)],
) -> WorkOrderRead:
    return service.update_queue_position(work_order_id, payload, station_context=station_context)


@router.post("/queue/reorder", response_model=list[WorkOrderRead])
def reorder_queue(
    payload: WorkOrderQueueReorderBatchRequest,
    service: Annotated[ManagerService, Depends(get_manager_service)],
    station_context: Annotated[StationContext, Depends(get_station_context)],
) -> list[WorkOrderRead]:
    return service.reorder_queue(payload, station_context=station_context)