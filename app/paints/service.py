import json
from datetime import UTC, date, datetime

from app.audit.context import StationContext, ensure_station_allowed
from app.audit.models import AuditEvent
from app.audit.repository import AuditRepository
from app.paints.models import Paint, PaintStockMovement
from app.paints.repository import PaintRepository
from app.paints.schemas import (
    PaintDeliveryCreate,
    PaintListResponse,
    PaintLookupRead,
    PaintManualAdjustmentCreate,
    PaintRead,
    PaintStockMovementListResponse,
    PaintStockMovementRead,
    build_paint_stock_movement_type_view,
)
from app.shared.enums import PaintStockMovementType, StationId
from app.shared.exceptions import InvalidPaintInventoryError, ResourceNotFoundError


class PaintService:
    def __init__(self, repository: PaintRepository) -> None:
        self.repository = repository
        self.audit_repository = AuditRepository(repository.session)

    def list_paints(self, *, limit: int, offset: int) -> PaintListResponse:
        items = self.repository.list(limit=limit, offset=offset)
        total = self.repository.count()
        return PaintListResponse(
            items=[self._to_read_model(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    def lookup_current_stock(self, *, ral_code: str, paint_producer: str, paint_code: str) -> PaintLookupRead:
        paint = self.repository.get_by_identity(
            ral_code=ral_code,
            paint_producer=paint_producer,
            paint_code=paint_code,
        )
        if paint is None:
            return PaintLookupRead(
                paint_id=None,
                ral_code=ral_code,
                paint_producer=paint_producer,
                paint_code=paint_code,
                current_quantity_kg=0,
                exists_in_inventory=False,
            )
        return PaintLookupRead(
            paint_id=paint.id,
            ral_code=paint.ral_code,
            paint_producer=paint.paint_producer,
            paint_code=paint.paint_code,
            current_quantity_kg=paint.current_quantity_kg,
            exists_in_inventory=True,
        )

    def capture_work_order_snapshot(self, *, ral_code: str, paint_producer: str, paint_code: str) -> tuple[Paint, float]:
        paint = self._get_or_create_paint(
            ral_code=ral_code,
            paint_producer=paint_producer,
            paint_code=paint_code,
        )
        return paint, paint.current_quantity_kg

    def record_delivery(
        self,
        payload: PaintDeliveryCreate,
        *,
        station_context: StationContext | None = None,
    ) -> PaintRead:
        self._ensure_office_station_action(station_context)
        paint = self._get_or_create_paint(
            ral_code=payload.ral_code,
            paint_producer=payload.paint_producer,
            paint_code=payload.paint_code,
        )
        movement_date = payload.movement_date or date.today()

        try:
            updated_paint = self._apply_movement(
                paint=paint,
                movement_type=PaintStockMovementType.DELIVERY,
                quantity_delta_kg=payload.quantity_kg,
                movement_date=movement_date,
                note=self._normalize_optional_text(payload.note),
                station_context=station_context,
            )
            self.repository.commit()
        except Exception:
            self.repository.rollback()
            raise

        return self._to_read_model(updated_paint)

    def record_manual_adjustment(
        self,
        payload: PaintManualAdjustmentCreate,
        *,
        station_context: StationContext | None = None,
    ) -> PaintRead:
        self._ensure_office_station_action(station_context)
        paint = self._get_or_create_paint(
            ral_code=payload.ral_code,
            paint_producer=payload.paint_producer,
            paint_code=payload.paint_code,
        )
        movement_date = payload.movement_date or date.today()

        try:
            updated_paint = self._apply_movement(
                paint=paint,
                movement_type=PaintStockMovementType.MANUAL_ADJUSTMENT,
                quantity_delta_kg=payload.quantity_delta_kg,
                movement_date=movement_date,
                note=payload.note,
                station_context=station_context,
            )
            self.repository.commit()
        except Exception:
            self.repository.rollback()
            raise

        return self._to_read_model(updated_paint)

    def record_automatic_consumption(
        self,
        *,
        ral_code: str,
        paint_producer: str,
        paint_code: str,
        quantity_kg: float,
        work_order_id: int,
        station_context: StationContext | None,
    ) -> Paint:
        paint = self._get_or_create_paint(
            ral_code=ral_code,
            paint_producer=paint_producer,
            paint_code=paint_code,
        )
        return self._apply_movement(
            paint=paint,
            movement_type=PaintStockMovementType.AUTOMATIC_CONSUMPTION,
            quantity_delta_kg=-quantity_kg,
            movement_date=date.today(),
            note=None,
            work_order_id=work_order_id,
            station_context=station_context,
        )

    def has_stock_history(self, paint_id: int) -> bool:
        # True when a paint has real stock movement history (delivered/adjusted/consumed), as opposed to
        # the 0-kg placeholder row auto-created when a work order snapshots its colour. The planner's
        # paint hard block (N49-7) treats only a colour with history + ≤ 0 balance as known-depleted.
        return self.repository.has_stock_movements(paint_id)

    def get_consumed_paint_kg_for_work_orders(self, work_order_ids) -> float:
        # Cumulative automatic paint consumption (kg) across the given work orders, computed from the
        # durable movement log (NA32). Used by read models so a corrected order reports the total kg of
        # all rounds/children rather than only the last round's per-round gate value.
        return self.repository.sum_automatic_consumption_kg(list(work_order_ids))

    def list_movements(self, paint_id: int, *, limit: int, offset: int) -> PaintStockMovementListResponse:
        paint = self.repository.get_by_id(paint_id)
        if paint is None:
            raise ResourceNotFoundError(f"Paint {paint_id} not found.")

        items = self.repository.list_movements(paint_id=paint_id, limit=limit, offset=offset)
        return PaintStockMovementListResponse(
            items=[self._to_movement_read_model(item) for item in items],
            total=len(self.repository.list_movements(paint_id=paint_id, limit=10_000, offset=0)),
            limit=limit,
            offset=offset,
        )

    def _get_or_create_paint(self, *, ral_code: str, paint_producer: str, paint_code: str) -> Paint:
        existing_paint = self.repository.get_by_identity(
            ral_code=ral_code,
            paint_producer=paint_producer,
            paint_code=paint_code,
        )
        if existing_paint is not None:
            return existing_paint

        paint = Paint(
            ral_code=ral_code,
            paint_producer=paint_producer,
            paint_code=paint_code,
            current_quantity_kg=0,
        )
        return self.repository.add(paint)

    def _apply_movement(
        self,
        *,
        paint: Paint,
        movement_type: PaintStockMovementType,
        quantity_delta_kg: float,
        movement_date: date,
        note: str | None,
        station_context: StationContext | None,
        work_order_id: int | None = None,
    ) -> Paint:
        updated_paint = self.repository.apply_quantity_delta(paint_id=paint.id, quantity_delta_kg=quantity_delta_kg)
        if updated_paint is None:
            raise InvalidPaintInventoryError(
                f"Insufficient paint stock for {paint.paint_producer} / {paint.ral_code} / {paint.paint_code}."
            )

        movement = PaintStockMovement(
            paint_id=paint.id,
            work_order_id=work_order_id,
            movement_type=movement_type,
            quantity_delta_kg=quantity_delta_kg,
            resulting_quantity_kg=updated_paint.current_quantity_kg,
            movement_date=movement_date,
            note=note,
        )
        persisted_movement = self.repository.add_movement(movement)
        self._record_audit_event(
            event_type=f"paint.{movement_type.value.lower()}.recorded",
            station_context=station_context,
            paint=updated_paint,
            movement=persisted_movement,
            summary=f"Recorded {movement_type.polish_label.lower()} for paint {updated_paint.paint_producer} / {updated_paint.ral_code} / {updated_paint.paint_code}.",
            details={
                "movement_type": movement_type.value,
                "quantity_delta_kg": quantity_delta_kg,
                "resulting_quantity_kg": updated_paint.current_quantity_kg,
                "movement_date": movement_date,
                "note": note,
                "work_order_id": work_order_id,
                "paint": {
                    "id": updated_paint.id,
                    "ral_code": updated_paint.ral_code,
                    "paint_producer": updated_paint.paint_producer,
                    "paint_code": updated_paint.paint_code,
                },
            },
        )
        return updated_paint

    @staticmethod
    def _ensure_office_station_action(station_context: StationContext | None) -> None:
        ensure_station_allowed(
            station_context,
            allowed_station_ids={StationId.OFFICE},
            action="office paint inventory actions",
        )

    def _record_audit_event(
        self,
        *,
        event_type: str,
        station_context: StationContext | None,
        paint: Paint,
        movement: PaintStockMovement,
        summary: str,
        details: dict[str, object],
    ) -> None:
        station_id = station_context.station_id if station_context is not None else StationId.SYSTEM
        self.audit_repository.add(
            AuditEvent(
                event_type=event_type,
                station_id=station_id,
                work_order_id=movement.work_order_id,
                target_type="paint",
                target_id=paint.id,
                summary=summary,
                details_json=json.dumps(self._json_ready(details), separators=(",", ":")),
            )
        )

    @classmethod
    def _json_ready(cls, value: object) -> object:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, dict):
            return {key: cls._json_ready(nested_value) for key, nested_value in value.items()}
        if isinstance(value, list):
            return [cls._json_ready(nested_value) for nested_value in value]
        return value

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _to_read_model(paint: Paint) -> PaintRead:
        return PaintRead(
            id=paint.id,
            ral_code=paint.ral_code,
            paint_producer=paint.paint_producer,
            paint_code=paint.paint_code,
            current_quantity_kg=paint.current_quantity_kg,
            created_at=paint.created_at,
            updated_at=paint.updated_at,
        )

    @staticmethod
    def _to_movement_read_model(movement: PaintStockMovement) -> PaintStockMovementRead:
        return PaintStockMovementRead(
            id=movement.id,
            paint_id=movement.paint_id,
            work_order_id=movement.work_order_id,
            movement_type=build_paint_stock_movement_type_view(movement.movement_type),
            quantity_delta_kg=movement.quantity_delta_kg,
            resulting_quantity_kg=movement.resulting_quantity_kg,
            movement_date=movement.movement_date,
            note=movement.note,
            created_at=movement.created_at,
        )
