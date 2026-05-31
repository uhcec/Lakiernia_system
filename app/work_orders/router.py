from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.audit.context import StationContext, get_station_context
from app.database.session import get_db_session
from app.process.enums import ProcessDisplayStatus
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import (
	WorkOrderCreate,
	WorkOrderAttachmentRead,
	WorkOrderListResponse,
	WorkOrderRead,
	WorkOrderReleaseUpdate,
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
	station_context: Annotated[StationContext, Depends(get_station_context)],
) -> WorkOrderRead:
	return service.create_work_order(payload, station_context=station_context)


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
	station_context: Annotated[StationContext, Depends(get_station_context)],
) -> WorkOrderRead:
	return service.update_work_order(work_order_id, payload, station_context=station_context)


@router.get("", response_model=WorkOrderListResponse)
def list_work_orders(
	service: Annotated[WorkOrderService, Depends(get_work_order_service)],
	limit: Annotated[int, Query(ge=1, le=100)] = 50,
	offset: Annotated[int, Query(ge=0)] = 0,
	process_status: Annotated[ProcessDisplayStatus | None, Query()] = None,
	external_order_number: Annotated[str | None, Query(max_length=128)] = None,
) -> WorkOrderListResponse:
	return service.list_work_orders(
		limit=limit,
		offset=offset,
		process_status=process_status,
		external_order_number=external_order_number,
	)


@router.post("/{work_order_id}/status-transitions", response_model=WorkOrderRead)
def transition_work_order_status(
	work_order_id: int,
	service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderRead:
	return service.reject_manual_status_transition(work_order_id)


@router.post("/{work_order_id}/mark-complete-arrival", response_model=WorkOrderRead)
def mark_work_order_complete_arrival(
	work_order_id: int,
	service: Annotated[WorkOrderService, Depends(get_work_order_service)],
	station_context: Annotated[StationContext, Depends(get_station_context)],
) -> WorkOrderRead:
	return service.mark_complete_arrival(work_order_id, station_context=station_context)


@router.patch("/{work_order_id}/release-status", response_model=WorkOrderRead)
def update_work_order_release_status(
	work_order_id: int,
	payload: WorkOrderReleaseUpdate,
	service: Annotated[WorkOrderService, Depends(get_work_order_service)],
	station_context: Annotated[StationContext, Depends(get_station_context)],
) -> WorkOrderRead:
	return service.update_release_status(work_order_id, payload, station_context=station_context)


@router.post("/{work_order_id}/attachments", response_model=WorkOrderAttachmentRead, status_code=status.HTTP_201_CREATED)
async def upload_work_order_attachment(
	work_order_id: int,
	service: Annotated[WorkOrderService, Depends(get_work_order_service)],
	station_context: Annotated[StationContext, Depends(get_station_context)],
	file: UploadFile = File(...),
	attachment_type: Annotated[str | None, Form()] = None,
	description: Annotated[str | None, Form()] = None,
) -> WorkOrderAttachmentRead:
	return await service.upload_attachment(
		work_order_id,
		file,
		attachment_type=attachment_type,
		description=description,
		station_context=station_context,
	)


@router.get("/{work_order_id}/attachments", response_model=list[WorkOrderAttachmentRead])
def list_work_order_attachments(
	work_order_id: int,
	service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> list[WorkOrderAttachmentRead]:
	return service.list_attachments(work_order_id)


@router.get("/{work_order_id}/attachments/{attachment_id}/download")
def download_work_order_attachment(
	work_order_id: int,
	attachment_id: int,
	service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> Response:
	attachment, file_path = service.get_attachment_download(work_order_id, attachment_id)
	return FileResponse(
		path=file_path,
		media_type=attachment.content_type,
		filename=attachment.original_filename,
	)


@router.delete("/{work_order_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_work_order_attachment(
	work_order_id: int,
	attachment_id: int,
	service: Annotated[WorkOrderService, Depends(get_work_order_service)],
	station_context: Annotated[StationContext, Depends(get_station_context)],
) -> Response:
	service.delete_attachment(work_order_id, attachment_id, station_context=station_context)
	return Response(status_code=status.HTTP_204_NO_CONTENT)