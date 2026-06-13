from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.audit.context import StationContext, get_station_context
from app.clients.repository import ClientRepository
from app.clients.schemas import (
    ClientCreate,
    ClientDetailRead,
    ClientListResponse,
    ClientRead,
    ClientUpdate,
)
from app.clients.service import ClientService
from app.database.session import get_db_session

router = APIRouter(prefix="/clients", tags=["clients"])


def get_client_service(session: Annotated[Session, Depends(get_db_session)]) -> ClientService:
    repository = ClientRepository(session)
    return ClientService(repository)


@router.get("", response_model=ClientListResponse)
def list_clients(
    service: Annotated[ClientService, Depends(get_client_service)],
    search: Annotated[str | None, Query(max_length=255)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ClientListResponse:
    return service.list_clients(limit=limit, offset=offset, search=search)


@router.get("/{client_id}", response_model=ClientDetailRead)
def get_client(
    client_id: int,
    service: Annotated[ClientService, Depends(get_client_service)],
) -> ClientDetailRead:
    return service.get_client_detail(client_id)


@router.post("", response_model=ClientRead, status_code=status.HTTP_201_CREATED)
def create_client(
    payload: ClientCreate,
    service: Annotated[ClientService, Depends(get_client_service)],
    station_context: Annotated[StationContext, Depends(get_station_context)],
) -> ClientRead:
    return service.create_client(payload, station_context=station_context)


@router.patch("/{client_id}", response_model=ClientRead)
def update_client(
    client_id: int,
    payload: ClientUpdate,
    service: Annotated[ClientService, Depends(get_client_service)],
    station_context: Annotated[StationContext, Depends(get_station_context)],
) -> ClientRead:
    return service.update_client(client_id, payload, station_context=station_context)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(
    client_id: int,
    service: Annotated[ClientService, Depends(get_client_service)],
    station_context: Annotated[StationContext, Depends(get_station_context)],
) -> None:
    service.delete_client(client_id, station_context=station_context)
