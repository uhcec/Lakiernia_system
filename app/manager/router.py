from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db_session
from app.manager.repository import ManagerRepository
from app.manager.schemas import WorkOrderPlanAssignRequest, WorkOrderQueuePositionUpdateRequest
from app.manager.service import ManagerService
from app.work_orders.schemas import WorkOrderRead

router = APIRouter(prefix="/manager/work-orders", tags=["manager-work-orders"])


def get_manager_service(session: Annotated[Session, Depends(get_db_session)]) -> ManagerService:
    repository = ManagerRepository(session)
    return ManagerService(repository)


@router.get("/unplanned", response_model=list[WorkOrderRead])
def list_unplanned_work_orders(
    service: Annotated[ManagerService, Depends(get_manager_service)],
) -> list[WorkOrderRead]:
    return service.list_unplanned_work_orders()


@router.get("", response_model=list[WorkOrderRead])
def list_planned_work_orders(
    service: Annotated[ManagerService, Depends(get_manager_service)],
) -> list[WorkOrderRead]:
    return service.list_planned_work_orders()


@router.post("/{work_order_id}/plan", response_model=WorkOrderRead)
def assign_plan(
    work_order_id: int,
    payload: WorkOrderPlanAssignRequest,
    service: Annotated[ManagerService, Depends(get_manager_service)],
) -> WorkOrderRead:
    return service.assign_plan(work_order_id, payload)


@router.patch("/{work_order_id}/queue-position", response_model=WorkOrderRead)
def update_queue_position(
    work_order_id: int,
    payload: WorkOrderQueuePositionUpdateRequest,
    service: Annotated[ManagerService, Depends(get_manager_service)],
) -> WorkOrderRead:
    return service.update_queue_position(work_order_id, payload)