from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db_session
from app.shared.enums import WorkOrderStatus
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import (
	WorkOrderCreate,
	WorkOrderListResponse,
	WorkOrderRead,
	WorkOrderStatusTransitionRequest,
	WorkOrderUpdate,
)
from app.work_orders.service import WorkOrderService

router = APIRouter(prefix="/work-orders", tags=["work-orders"])


def get_work_order_service(session: Annotated[Session, Depends(get_db_session)]) -> WorkOrderService:
	repository = WorkOrderRepository(session)
	return WorkOrderService(repository)


@router.post("", response_model=WorkOrderRead, status_code=status.HTTP_201_CREATED)
def create_work_order(
	payload: WorkOrderCreate,
	service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderRead:
	return service.create_work_order(payload)


@router.get("/{work_order_id}", response_model=WorkOrderRead)
def get_work_order(
	work_order_id: int,
	service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderRead:
	return service.get_work_order(work_order_id)


@router.patch("/{work_order_id}", response_model=WorkOrderRead)
def update_work_order(
	work_order_id: int,
	payload: WorkOrderUpdate,
	service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderRead:
	return service.update_work_order(work_order_id, payload)


@router.get("", response_model=WorkOrderListResponse)
def list_work_orders(
	service: Annotated[WorkOrderService, Depends(get_work_order_service)],
	limit: Annotated[int, Query(ge=1, le=100)] = 50,
	offset: Annotated[int, Query(ge=0)] = 0,
	status: WorkOrderStatus | None = None,
) -> WorkOrderListResponse:
	return service.list_work_orders(limit=limit, offset=offset, status=status)


@router.post("/{work_order_id}/status-transitions", response_model=WorkOrderRead)
def transition_work_order_status(
	work_order_id: int,
	payload: WorkOrderStatusTransitionRequest,
	service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderRead:
	return service.transition_work_order_status_from_request(work_order_id, payload)


@router.post("/{work_order_id}/mark-complete-arrival", response_model=WorkOrderRead)
def mark_work_order_complete_arrival(
	work_order_id: int,
	service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderRead:
	return service.mark_complete_arrival(work_order_id)