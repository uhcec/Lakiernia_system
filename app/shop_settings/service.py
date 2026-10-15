import json

from sqlalchemy.orm import Session

from app.audit.context import StationContext, ensure_station_allowed
from app.audit.models import AuditEvent
from app.audit.repository import AuditRepository
from app.shared.enums import StationId
from app.shop_settings.models import ShopSettings
from app.shop_settings.schemas import ShopSettingsRead, ShopSettingsUpdate

DEFAULT_HANGING_MAX_ACTIVE_ORDERS = 1


def get_hanging_max_active_orders(session: Session) -> int:
    """How many orders may hang at once; 1 (the old fixed rule) until the manager changes it."""
    row = session.get(ShopSettings, 1)
    return row.hanging_max_active_orders if row is not None else DEFAULT_HANGING_MAX_ACTIVE_ORDERS


class ShopSettingsService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit_repository = AuditRepository(session)

    def get_settings(self) -> ShopSettingsRead:
        # Readable by every logged-in station: the hanging screen needs the limit to grey its buttons.
        return ShopSettingsRead(hanging_max_active_orders=get_hanging_max_active_orders(self.session))

    def update_settings(self, payload: ShopSettingsUpdate, station_context: StationContext | None) -> ShopSettingsRead:
        # Owner 2026-10-15: the manager (and admin, who bypasses station checks) changes settings.
        ensure_station_allowed(
            station_context,
            allowed_station_ids={StationId.MANAGER},
            action="zmiana ustawień",
        )
        row = self.session.get(ShopSettings, 1)
        previous = row.hanging_max_active_orders if row is not None else DEFAULT_HANGING_MAX_ACTIVE_ORDERS
        if row is None:
            row = ShopSettings(id=1, hanging_max_active_orders=payload.hanging_max_active_orders)
            self.session.add(row)
        else:
            row.hanging_max_active_orders = payload.hanging_max_active_orders
        self.session.flush()

        station_id = station_context.station_id if station_context is not None else StationId.SYSTEM
        self.audit_repository.add(
            AuditEvent(
                event_type="settings.updated",
                station_id=station_id,
                work_order_id=None,
                target_type="shop_settings",
                target_id=row.id,
                summary=(
                    "Hanging max active orders changed from "
                    f"{previous} to {payload.hanging_max_active_orders}."
                ),
                details_json=json.dumps(
                    {"hanging_max_active_orders": {"from": previous, "to": payload.hanging_max_active_orders}},
                    separators=(",", ":"),
                ),
            )
        )
        self.session.commit()
        return ShopSettingsRead(hanging_max_active_orders=row.hanging_max_active_orders)
