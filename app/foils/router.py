from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.audit.context import StationContext, get_station_context
from app.database.session import get_db_session
from app.foils.repository import FoilRepository
from app.foils.schemas import (
    FoilCreate,
    FoilListResponse,
    FoilRead,
    FoilUpdate,
)
from app.foils.service import FoilService

router = APIRouter(prefix="/foils", tags=["foils"])


def get_foil_service(session: Annotated[Session, Depends(get_db_session)]) -> FoilService:
    return FoilService(FoilRepository(session))


@router.get("", response_model=FoilListResponse)
def list_foils(
    service: Annotated[FoilService, Depends(get_foil_service)],
    search: Annotated[str | None, Query(max_length=255)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FoilListResponse:
    return service.list_foils(limit=limit, offset=offset, search=search)


@router.get("/{foil_id}", response_model=FoilRead)
def get_foil(
    foil_id: int,
    service: Annotated[FoilService, Depends(get_foil_service)],
) -> FoilRead:
    return service.get_foil(foil_id)


@router.post("", response_model=FoilRead, status_code=status.HTTP_201_CREATED)
def create_foil(
    payload: FoilCreate,
    service: Annotated[FoilService, Depends(get_foil_service)],
    station_context: Annotated[StationContext, Depends(get_station_context)],
) -> FoilRead:
    return service.create_foil(payload, station_context=station_context)


@router.patch("/{foil_id}", response_model=FoilRead)
def update_foil(
    foil_id: int,
    payload: FoilUpdate,
    service: Annotated[FoilService, Depends(get_foil_service)],
    station_context: Annotated[StationContext, Depends(get_station_context)],
) -> FoilRead:
    return service.update_foil(foil_id, payload, station_context=station_context)


@router.delete("/{foil_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_foil(
    foil_id: int,
    service: Annotated[FoilService, Depends(get_foil_service)],
    station_context: Annotated[StationContext, Depends(get_station_context)],
) -> None:
    service.delete_foil(foil_id, station_context=station_context)
