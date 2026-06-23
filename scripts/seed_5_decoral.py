"""Seed 5 unplanned DECORAL work orders on well-stocked paint cards (bucket: Do zaplanowania)."""
from __future__ import annotations

from datetime import date, timedelta

from app.database.session import get_session_factory
from app.paints.models import Paint
from app.paints.repository import PaintRepository
from app.process.enums import CoatingType
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import WorkOrderCreate
from app.work_orders.service import WorkOrderService

MIN_STOCK_KG = 30.0

# (title, ral_code, paint_producer, paint_code, total_quantity, total_area_m2, profiles, accessories)
ORDERS = [
    dict(title="Panele elewacyjne Decoral drewno", ral_code="D-310", paint_producer="Decoral System",
         paint_code="DCR-310", total_quantity=24, total_area_m2=24.0, profiles_quantity=20, accessories_quantity=4),
    dict(title="Profile bramowe Decoral antracyt", ral_code="RAL 9005", paint_producer="AkzoNobel",
         paint_code="AKZ-9005-MA", total_quantity=16, total_area_m2=16.0, profiles_quantity=14, accessories_quantity=2),
    dict(title="Ramy okienne Decoral zloty dab", ral_code="RAL 7035", paint_producer="AkzoNobel",
         paint_code="AKZ-7035-GL", total_quantity=30, total_area_m2=30.0, profiles_quantity=26, accessories_quantity=4),
    dict(title="Listwy wykonczeniowe Decoral orzech", ral_code="RAL 3020", paint_producer="Sherwin-Williams",
         paint_code="SHW-3020-GL", total_quantity=12, total_area_m2=12.0, profiles_quantity=10, accessories_quantity=2),
    dict(title="Oslony Decoral szczotkowany", ral_code="RAL 5010", paint_producer="Tiger",
         paint_code="TIG-5010-MA", total_quantity=20, total_area_m2=20.0, profiles_quantity=18, accessories_quantity=2),
]


def main() -> None:
    today = date.today()
    pickup = today + timedelta(days=10)
    session_factory = get_session_factory()

    with session_factory() as session:
        paint_repo = PaintRepository(session)
        svc = WorkOrderService(WorkOrderRepository(session))

        for o in ORDERS:
            # Ensure the paint card exists and has comfortable stock for this DECORAL order.
            paint = paint_repo.get_by_identity(
                ral_code=o["ral_code"], paint_producer=o["paint_producer"], paint_code=o["paint_code"]
            )
            if paint is None:
                paint = paint_repo.add(
                    Paint(
                        ral_code=o["ral_code"], paint_producer=o["paint_producer"],
                        paint_code=o["paint_code"], current_quantity_kg=MIN_STOCK_KG,
                    )
                )
            elif paint.current_quantity_kg < MIN_STOCK_KG:
                paint.current_quantity_kg = MIN_STOCK_KG
            session.flush()

            payload = WorkOrderCreate(
                title=o["title"],
                total_quantity=o["total_quantity"],
                description=o["title"],
                customer_name="Fenco",
                ral_code=o["ral_code"],
                paint_code=o["paint_code"],
                paint_producer=o["paint_producer"],
                coating_type=CoatingType.DECORAL,
                received_date=today,
                planned_pickup_date=pickup,
                total_area_m2=o["total_area_m2"],
                profiles_quantity=o["profiles_quantity"],
                accessories_quantity=o["accessories_quantity"],
            )
            wo = svc.create_work_order(payload)
            print(f"Utworzono: {wo.order_number} - {o['title']} | farba {o['ral_code']} stan {paint.current_quantity_kg:.0f} kg")

    print("Gotowe. Dodano 5 zlecen DECORAL do zaplanowania, z zapewniona farba.")


if __name__ == "__main__":
    main()
