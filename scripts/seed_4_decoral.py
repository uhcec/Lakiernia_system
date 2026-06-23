"""Seed 4 unplanned DECORAL work orders (bucket: Do zaplanowania)."""
from __future__ import annotations

from datetime import date, timedelta

from app.database.session import get_session_factory
from app.process.enums import CoatingType
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import WorkOrderCreate
from app.work_orders.service import WorkOrderService

ORDERS = [
    dict(title="Panele elewacyjne Decoral drewno", total_quantity=24,
         customer_name="Fenco", ral_code="D-201", paint_code="DCR-201",
         paint_producer="Decoral System", profiles_quantity=20, accessories_quantity=4, total_area_m2=24.0),
    dict(title="Profile bramowe Decoral antracyt", total_quantity=16,
         customer_name="kris tech", ral_code="D-202", paint_code="DCR-202",
         paint_producer="Decoral System", profiles_quantity=14, accessories_quantity=2, total_area_m2=16.0),
    dict(title="Ramy okienne Decoral zloty dab", total_quantity=30,
         customer_name="Fenco", ral_code="D-203", paint_code="DCR-203",
         paint_producer="Decoral System", profiles_quantity=26, accessories_quantity=4, total_area_m2=30.0),
    dict(title="Listwy wykonczeniowe Decoral orzech", total_quantity=12,
         customer_name="kris tech", ral_code="D-204", paint_code="DCR-204",
         paint_producer="Decoral System", profiles_quantity=10, accessories_quantity=2, total_area_m2=12.0),
]


def main() -> None:
    today = date.today()
    pickup = today + timedelta(days=10)
    session_factory = get_session_factory()

    with session_factory() as session:
        repo = WorkOrderRepository(session)
        svc = WorkOrderService(repo)
        for o in ORDERS:
            payload = WorkOrderCreate(
                title=o["title"],
                total_quantity=o["total_quantity"],
                description=o["title"],
                customer_name=o["customer_name"],
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
            print(f"Utworzono: {wo.order_number} - {o['title']} ({o['customer_name']})")

    print("Gotowe. Dodano 4 zlecenia DECORAL do zaplanowania.")


if __name__ == "__main__":
    main()
