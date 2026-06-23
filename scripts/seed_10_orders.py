"""Seed 10 unplanned work orders for existing clients and paints."""
from __future__ import annotations

from datetime import date, timedelta

from app.database.session import get_session_factory
from app.process.enums import CoatingType
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import WorkOrderCreate
from app.work_orders.service import WorkOrderService

ORDERS = [
    dict(title="Profile tarasowe", coating_type=CoatingType.RAL, total_quantity=32,
         customer_name="Fenco", ral_code="RAL 7016", paint_code="TIG-7016-MA",
         paint_producer="Tiger", profiles_quantity=28, accessories_quantity=4, total_area_m2=32.0),
    dict(title="Okna fasadowe duze", coating_type=CoatingType.RAL, total_quantity=18,
         customer_name="kris tech", ral_code="RAL 9005", paint_code="AKZ-9005-MA",
         paint_producer="AkzoNobel", profiles_quantity=14, accessories_quantity=4, total_area_m2=18.0),
    dict(title="Elementy balkonowe", coating_type=CoatingType.RAL, total_quantity=45,
         customer_name="Fenco", ral_code="RAL 7035", paint_code="AKZ-7035-GL",
         paint_producer="AkzoNobel", profiles_quantity=40, accessories_quantity=5, total_area_m2=45.0),
    dict(title="Skrzydla drzwiowe", coating_type=CoatingType.RAL, total_quantity=12,
         customer_name="kris tech", ral_code="RAL 3020", paint_code="SHW-3020-GL",
         paint_producer="Sherwin-Williams", profiles_quantity=10, accessories_quantity=2, total_area_m2=12.0),
    dict(title="Ramy okien aluminiowych", coating_type=CoatingType.RAL, total_quantity=60,
         customer_name="Fenco", ral_code="RAL 9010", paint_code="AKZ-9010-GL",
         paint_producer="AkzoNobel", profiles_quantity=55, accessories_quantity=5, total_area_m2=60.0),
    dict(title="Listwy elewacyjne", coating_type=CoatingType.RAL, total_quantity=25,
         customer_name="kris tech", ral_code="RAL 5010", paint_code="TIG-5010-MA",
         paint_producer="Tiger", profiles_quantity=22, accessories_quantity=3, total_area_m2=25.0),
    dict(title="Oslony techniczne", coating_type=CoatingType.RAL, total_quantity=8,
         customer_name="Fenco", ral_code="RAL 8017", paint_code="AKZ-8017-MA",
         paint_producer="AkzoNobel", profiles_quantity=8, accessories_quantity=0, total_area_m2=8.0),
    dict(title="Ksztaltowniki aluminiowe", coating_type=CoatingType.RAL, total_quantity=38,
         customer_name="kris tech", ral_code="RAL 7040", paint_code="TIG-7040-MA",
         paint_producer="Tiger", profiles_quantity=30, accessories_quantity=8, total_area_m2=38.0),
    dict(title="Panel elewacyjny Decoral", coating_type=CoatingType.DECORAL, total_quantity=15,
         customer_name="Fenco", ral_code="D-200", paint_code="DCR-200",
         paint_producer="Decoral System", profiles_quantity=12, accessories_quantity=3, total_area_m2=15.0),
    dict(title="Zestawy roletowe", coating_type=CoatingType.RAL, total_quantity=20,
         customer_name="kris tech", ral_code="RAL 6021", paint_code="IGP-6021-GL",
         paint_producer="IGP", profiles_quantity=16, accessories_quantity=4, total_area_m2=20.0),
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
                coating_type=o["coating_type"],
                received_date=today,
                planned_pickup_date=pickup,
                total_area_m2=o["total_area_m2"],
                profiles_quantity=o["profiles_quantity"],
                accessories_quantity=o["accessories_quantity"],
            )
            wo = svc.create_work_order(payload)
            print(f"Utworzono: {wo.order_number} - {o['title']} ({o['customer_name']})")

    print("Gotowe. Dodano 10 zlecen do zaplanowania.")


if __name__ == "__main__":
    main()
