import json
from datetime import date, datetime

from app.audit.context import StationContext, ensure_station_allowed
from app.audit.models import AuditEvent
from app.audit.repository import AuditRepository
from app.foils.models import Foil
from app.foils.repository import FoilRepository
from app.foils.schemas import (
    FoilCreate,
    FoilListResponse,
    FoilRead,
    FoilUpdate,
)
from app.shared.enums import StationId
from app.shared.exceptions import AppException, ResourceNotFoundError


class FoilAlreadyExistsError(AppException):
    def __init__(self, detail: str) -> None:
        super().__init__(detail=detail, status_code=409)


class FoilService:
    def __init__(self, repository: FoilRepository) -> None:
        self.repository = repository
        self.audit_repository = AuditRepository(repository.session)

    def list_foils(self, *, limit: int, offset: int, search: str | None = None) -> FoilListResponse:
        items = self.repository.list(limit=limit, offset=offset, search=search)
        total = self.repository.count(search=search)
        return FoilListResponse(
            items=[self._to_read_model(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    def get_foil(self, foil_id: int) -> FoilRead:
        return self._to_read_model(self._get_existing_foil(foil_id))

    def create_foil(self, payload: FoilCreate, *, station_context: StationContext | None = None) -> FoilRead:
        self._ensure_office_station_action(station_context)
        code = payload.code.strip()
        existing = self.repository.get_by_code(code)
        if existing is not None:
            raise FoilAlreadyExistsError(f"Folia o kodzie '{code}' już istnieje.")

        foil = Foil(
            name=payload.name.strip(),
            code=code,
            supplier=self._normalize_optional_text(payload.supplier),
            notes=self._normalize_optional_text(payload.notes),
        )
        try:
            persisted = self.repository.add(foil)
            self._record_audit_event(
                event_type="foil.created",
                station_context=station_context,
                foil=persisted,
                summary=f"Utworzono folię {persisted.name} ({persisted.code}).",
                details={"name": persisted.name, "code": persisted.code, "supplier": persisted.supplier},
            )
            self.repository.commit()
        except Exception:
            self.repository.rollback()
            raise

        return self._to_read_model(persisted)

    def update_foil(
        self,
        foil_id: int,
        payload: FoilUpdate,
        *,
        station_context: StationContext | None = None,
    ) -> FoilRead:
        self._ensure_office_station_action(station_context)
        foil = self._get_existing_foil(foil_id)

        if payload.code is not None:
            new_code = payload.code.strip()
            existing = self.repository.get_by_code(new_code)
            if existing is not None and existing.id != foil.id:
                raise FoilAlreadyExistsError(f"Folia o kodzie '{new_code}' już istnieje.")
            foil.code = new_code

        if payload.name is not None:
            foil.name = payload.name.strip()

        if payload.supplier is not None:
            foil.supplier = self._normalize_optional_text(payload.supplier)

        if payload.notes is not None:
            foil.notes = self._normalize_optional_text(payload.notes)

        try:
            self.repository.session.flush()
            self._record_audit_event(
                event_type="foil.updated",
                station_context=station_context,
                foil=foil,
                summary=f"Zaktualizowano folię {foil.name} ({foil.code}).",
                details={"name": foil.name, "code": foil.code, "supplier": foil.supplier},
            )
            self.repository.commit()
        except Exception:
            self.repository.rollback()
            raise

        return self._to_read_model(foil)

    def delete_foil(self, foil_id: int, *, station_context: StationContext | None = None) -> None:
        self._ensure_office_station_action(station_context)
        foil = self._get_existing_foil(foil_id)
        name = foil.name
        code = foil.code
        try:
            self.repository.delete(foil)
            self._record_audit_event(
                event_type="foil.deleted",
                station_context=station_context,
                foil=foil,
                summary=f"Usunięto folię {name} ({code}).",
                details={"name": name, "code": code},
            )
            self.repository.commit()
        except Exception:
            self.repository.rollback()
            raise

    def _get_existing_foil(self, foil_id: int) -> Foil:
        foil = self.repository.get_by_id(foil_id)
        if foil is None:
            raise ResourceNotFoundError(f"Foil {foil_id} not found.")
        return foil

    @staticmethod
    def _ensure_office_station_action(station_context: StationContext | None) -> None:
        ensure_station_allowed(
            station_context,
            allowed_station_ids={StationId.OFFICE},
            action="office foil registry actions",
        )

    def _to_read_model(self, foil: Foil) -> FoilRead:
        return FoilRead(
            id=foil.id,
            name=foil.name,
            code=foil.code,
            supplier=foil.supplier,
            notes=foil.notes,
            usage_count=self.repository.count_orders_for_foil(foil.id),
            created_at=foil.created_at,
            updated_at=foil.updated_at,
        )

    def _record_audit_event(
        self,
        *,
        event_type: str,
        station_context: StationContext | None,
        foil: Foil,
        summary: str,
        details: dict[str, object],
    ) -> None:
        station_id = station_context.station_id if station_context is not None else StationId.SYSTEM
        self.audit_repository.add(
            AuditEvent(
                event_type=event_type,
                station_id=station_id,
                work_order_id=None,
                target_type="foil",
                target_id=foil.id,
                summary=summary,
                details_json=json.dumps(self._json_ready(details), separators=(",", ":")),
            )
        )

    @classmethod
    def _json_ready(cls, value: object) -> object:
        if isinstance(value, (datetime, date)):
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
