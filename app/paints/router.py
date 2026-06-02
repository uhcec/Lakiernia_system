from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.audit.context import StationContext, get_station_context
from app.database.session import get_db_session
from app.paints.repository import PaintRepository
from app.paints.schemas import (
    PaintDeliveryCreate,
    PaintListResponse,
    PaintLookupRead,
    PaintManualAdjustmentCreate,
    PaintRead,
    PaintStockMovementListResponse,
)
from app.paints.service import PaintService

router = APIRouter(prefix="/paints", tags=["paints"])


def get_paint_service(session: Annotated[Session, Depends(get_db_session)]) -> PaintService:
    repository = PaintRepository(session)
    return PaintService(repository)


@router.get("", response_model=PaintListResponse)
def list_paints(
    service: Annotated[PaintService, Depends(get_paint_service)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaintListResponse:
    return service.list_paints(limit=limit, offset=offset)


@router.get("/lookup", response_model=PaintLookupRead)
def lookup_paint_stock(
    service: Annotated[PaintService, Depends(get_paint_service)],
    ral_code: Annotated[str, Query(min_length=1, max_length=64)],
    paint_producer: Annotated[str, Query(min_length=1, max_length=255)],
    paint_code: Annotated[str, Query(min_length=1, max_length=64)],
) -> PaintLookupRead:
    return service.lookup_current_stock(
        ral_code=ral_code,
        paint_producer=paint_producer,
        paint_code=paint_code,
    )


@router.get("/{paint_id}/movements", response_model=PaintStockMovementListResponse)
def list_paint_movements(
    paint_id: int,
    service: Annotated[PaintService, Depends(get_paint_service)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaintStockMovementListResponse:
    return service.list_movements(paint_id, limit=limit, offset=offset)


@router.post("/deliveries", response_model=PaintRead, status_code=status.HTTP_201_CREATED)
def record_paint_delivery(
    payload: PaintDeliveryCreate,
    service: Annotated[PaintService, Depends(get_paint_service)],
    station_context: Annotated[StationContext, Depends(get_station_context)],
) -> PaintRead:
    return service.record_delivery(payload, station_context=station_context)


@router.post("/adjustments", response_model=PaintRead, status_code=status.HTTP_201_CREATED)
def record_paint_adjustment(
    payload: PaintManualAdjustmentCreate,
    service: Annotated[PaintService, Depends(get_paint_service)],
    station_context: Annotated[StationContext, Depends(get_station_context)],
) -> PaintRead:
    return service.record_manual_adjustment(payload, station_context=station_context)