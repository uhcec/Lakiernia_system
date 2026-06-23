"""Add 100 kg to every paint in the inventory (seed/admin operation)."""
from __future__ import annotations

from datetime import date

from app.audit.context import StationContext
from app.database.session import get_session_factory
from app.paints.models import Paint, PaintStockMovement
from app.paints.repository import PaintRepository
from app.paints.schemas import PaintDeliveryCreate
from app.paints.service import PaintService
from app.shared.enums import StationId


def main() -> None:
    session_factory = get_session_factory()
    office_ctx = StationContext(station_id=StationId.OFFICE)

    with session_factory() as session:
        repo = PaintRepository(session)
        svc = PaintService(repo)

        paints = repo.list(limit=1000, offset=0)
        for paint in paints:
            payload = PaintDeliveryCreate(
                ral_code=paint.ral_code,
                paint_producer=paint.paint_producer,
                paint_code=paint.paint_code,
                quantity_kg=100.0,
                movement_date=date.today(),
                note="Dostawa startowa — 100 kg na start systemu.",
            )
            result = svc.record_delivery(payload, station_context=office_ctx)
            print(f"  {paint.ral_code} / {paint.paint_producer} / {paint.paint_code}: {result.current_quantity_kg} kg")

    print(f"\nGotowe. Dodano 100 kg do {len(paints)} farb.")


if __name__ == "__main__":
    main()
