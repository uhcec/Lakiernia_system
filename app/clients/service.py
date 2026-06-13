import json
from datetime import date, datetime

from app.audit.context import StationContext, ensure_station_allowed
from app.audit.models import AuditEvent
from app.audit.repository import AuditRepository
from app.clients.models import Client
from app.clients.repository import ClientRepository
from app.clients.schemas import (
    ClientCreate,
    ClientDetailRead,
    ClientListResponse,
    ClientOrderHistoryItem,
    ClientRead,
    ClientUpdate,
)
from app.process.repository import ProcessRepository
from app.process.service import ProcessService
from app.shared.enums import StationId, get_work_order_status_label
from app.shared.exceptions import AppException, ResourceNotFoundError
from app.work_orders.models import WorkOrder
from app.work_orders.schemas import WorkOrderStatusView, build_process_status_view, build_production_type_view


class ClientAlreadyExistsError(AppException):
    def __init__(self, detail: str) -> None:
        super().__init__(detail=detail, status_code=409)


class ClientService:
    def __init__(self, repository: ClientRepository) -> None:
        self.repository = repository
        self.audit_repository = AuditRepository(repository.session)

    def list_clients(self, *, limit: int, offset: int, search: str | None = None) -> ClientListResponse:
        items = self.repository.list(limit=limit, offset=offset, search=search)
        total = self.repository.count(search=search)
        return ClientListResponse(
            items=[self._to_read_model(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    def get_client_detail(self, client_id: int) -> ClientDetailRead:
        client = self.repository.get_by_id(client_id)
        if client is None:
            raise ResourceNotFoundError(f"Client {client_id} not found.")

        process_service = ProcessService(ProcessRepository(self.repository.session))
        orders = self.repository.list_orders_for_company(client.company_name)
        return ClientDetailRead(
            id=client.id,
            company_name=client.company_name,
            contact_phone=client.contact_phone,
            nip=client.nip,
            created_at=client.created_at,
            updated_at=client.updated_at,
            orders=[self._to_order_history_item(order, process_service) for order in orders],
        )

    def create_client(self, payload: ClientCreate, *, station_context: StationContext | None = None) -> ClientRead:
        self._ensure_office_station_action(station_context)
        company_name = payload.company_name.strip()
        existing = self.repository.get_by_company_name(company_name)
        if existing is not None:
            raise ClientAlreadyExistsError(f"Klient o nazwie '{company_name}' już istnieje.")

        client = Client(
            company_name=company_name,
            contact_phone=self._normalize_optional_text(payload.contact_phone),
            nip=self._normalize_optional_text(payload.nip),
        )
        try:
            persisted = self.repository.add(client)
            self._record_audit_event(
                event_type="client.created",
                station_context=station_context,
                client=persisted,
                summary=f"Utworzono klienta {persisted.company_name}.",
                details={
                    "company_name": persisted.company_name,
                    "contact_phone": persisted.contact_phone,
                    "nip": persisted.nip,
                },
            )
            self.repository.commit()
        except Exception:
            self.repository.rollback()
            raise

        return self._to_read_model(persisted)

    def update_client(
        self,
        client_id: int,
        payload: ClientUpdate,
        *,
        station_context: StationContext | None = None,
    ) -> ClientRead:
        self._ensure_office_station_action(station_context)
        client = self.repository.get_by_id(client_id)
        if client is None:
            raise ResourceNotFoundError(f"Client {client_id} not found.")

        if payload.company_name is not None:
            new_name = payload.company_name.strip()
            existing = self.repository.get_by_company_name(new_name)
            if existing is not None and existing.id != client.id:
                raise ClientAlreadyExistsError(f"Klient o nazwie '{new_name}' już istnieje.")
            client.company_name = new_name

        if payload.contact_phone is not None:
            client.contact_phone = self._normalize_optional_text(payload.contact_phone)

        if payload.nip is not None:
            client.nip = self._normalize_optional_text(payload.nip)

        try:
            self.repository.session.flush()
            self._record_audit_event(
                event_type="client.updated",
                station_context=station_context,
                client=client,
                summary=f"Zaktualizowano klienta {client.company_name}.",
                details={
                    "company_name": client.company_name,
                    "contact_phone": client.contact_phone,
                    "nip": client.nip,
                },
            )
            self.repository.commit()
        except Exception:
            self.repository.rollback()
            raise

        return self._to_read_model(client)

    def delete_client(self, client_id: int, *, station_context: StationContext | None = None) -> None:
        self._ensure_office_station_action(station_context)
        client = self.repository.get_by_id(client_id)
        if client is None:
            raise ResourceNotFoundError(f"Client {client_id} not found.")

        company_name = client.company_name
        try:
            self.repository.delete(client)
            self._record_audit_event(
                event_type="client.deleted",
                station_context=station_context,
                client=client,
                summary=f"Usunięto klienta {company_name}.",
                details={"company_name": company_name},
            )
            self.repository.commit()
        except Exception:
            self.repository.rollback()
            raise

    @staticmethod
    def _ensure_office_station_action(station_context: StationContext | None) -> None:
        ensure_station_allowed(
            station_context,
            allowed_station_ids={StationId.OFFICE},
            action="office client registry actions",
        )

    def _to_read_model(self, client: Client) -> ClientRead:
        return ClientRead(
            id=client.id,
            company_name=client.company_name,
            contact_phone=client.contact_phone,
            nip=client.nip,
            order_count=self.repository.count_orders_for_company(client.company_name),
            created_at=client.created_at,
            updated_at=client.updated_at,
        )

    @staticmethod
    def _to_order_history_item(order: WorkOrder, process_service: ProcessService) -> ClientOrderHistoryItem:
        process_display_status = process_service.get_display_status(order)
        return ClientOrderHistoryItem(
            id=order.id,
            order_number=order.order_number,
            external_order_number=order.external_order_number,
            title=order.title,
            total_quantity=order.total_quantity,
            ral_code=order.ral_code,
            received_date=order.received_date,
            planned_pickup_date=order.planned_pickup_date,
            status=WorkOrderStatusView(value=order.status, label=get_work_order_status_label(order.status)),
            production_type=build_production_type_view(order.production_type) if order.production_type is not None else None,
            process_status=build_process_status_view(process_display_status),
        )

    def _record_audit_event(
        self,
        *,
        event_type: str,
        station_context: StationContext | None,
        client: Client,
        summary: str,
        details: dict[str, object],
    ) -> None:
        station_id = station_context.station_id if station_context is not None else StationId.SYSTEM
        self.audit_repository.add(
            AuditEvent(
                event_type=event_type,
                station_id=station_id,
                work_order_id=None,
                target_type="client",
                target_id=client.id,
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
