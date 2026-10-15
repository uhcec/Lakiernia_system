from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.audit.context import StationContext, get_station_context
from app.database.session import get_db_session
from app.shop_settings.schemas import ShopSettingsRead, ShopSettingsUpdate
from app.shop_settings.service import ShopSettingsService

router = APIRouter(prefix="/shop-settings", tags=["shop-settings"])


def get_shop_settings_service(session: Annotated[Session, Depends(get_db_session)]) -> ShopSettingsService:
    return ShopSettingsService(session)


@router.get("", response_model=ShopSettingsRead)
def get_shop_settings(
    service: Annotated[ShopSettingsService, Depends(get_shop_settings_service)],
) -> ShopSettingsRead:
    return service.get_settings()


@router.put("", response_model=ShopSettingsRead)
def update_shop_settings(
    payload: ShopSettingsUpdate,
    station_context: Annotated[StationContext, Depends(get_station_context)],
    service: Annotated[ShopSettingsService, Depends(get_shop_settings_service)],
) -> ShopSettingsRead:
    return service.update_settings(payload, station_context)
