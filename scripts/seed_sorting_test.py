"""Seed 40 unplanned work orders with repeating RAL colors and companies for sorting tests."""
from __future__ import annotations

from datetime import date, timedelta

from app.database import models as _models  # noqa: F401
from app.database.session import get_session_factory
from app.manager.repository import ManagerRepository
from app.manager.service import ManagerService
from app.process.enums import CoatingType
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import WorkOrderCreate
from app.work_orders.service import WorkOrderService


_ORDERS: list[dict] = [
    # firma, ral_code, paint_code, paint_producer, total_quantity, total_area_m2, days_until_pickup
    {"customer": "Profiltech Sp. z o.o.",   "ral": "RAL 7016", "paint": "TIG-7016-MA", "producer": "Tiger",             "qty": 20, "area": 45.0,  "days": 3},
    {"customer": "Metal-Bud Zając",          "ral": "RAL 9005", "paint": "AKZ-9005-MA", "producer": "AkzoNobel",         "qty": 15, "area": 30.0,  "days": 7},
    {"customer": "Okno-System",              "ral": "RAL 7035", "paint": "AKZ-7035-GL", "producer": "AkzoNobel",         "qty": 30, "area": 60.0,  "days": 2},
    {"customer": "Aluprofil Kowalski",       "ral": "RAL 3020", "paint": "SHW-3020-GL", "producer": "Sherwin-Williams",  "qty": 10, "area": 20.0,  "days": 10},
    {"customer": "Fasada Group",             "ral": "RAL 9010", "paint": "AKZ-9010-GL", "producer": "AkzoNobel",         "qty": 25, "area": 55.0,  "days": 5},
    {"customer": "Profiltech Sp. z o.o.",   "ral": "RAL 9005", "paint": "AKZ-9005-MA", "producer": "AkzoNobel",         "qty": 18, "area": 38.0,  "days": 14},
    {"customer": "Metal-Bud Zając",          "ral": "RAL 7016", "paint": "TIG-7016-MA", "producer": "Tiger",             "qty": 12, "area": 25.0,  "days": 4},
    {"customer": "Okno-System",              "ral": "RAL 9010", "paint": "AKZ-9010-GL", "producer": "AkzoNobel",         "qty": 22, "area": 48.0,  "days": 6},
    {"customer": "Aluprofil Kowalski",       "ral": "RAL 7035", "paint": "AKZ-7035-GL", "producer": "AkzoNobel",         "qty": 8,  "area": 15.0,  "days": 9},
    {"customer": "Fasada Group",             "ral": "RAL 3020", "paint": "SHW-3020-GL", "producer": "Sherwin-Williams",  "qty": 35, "area": 70.0,  "days": 1},
    {"customer": "TechnoAlum",               "ral": "RAL 5010", "paint": "TIG-5010-MA", "producer": "Tiger",             "qty": 16, "area": 32.0,  "days": 12},
    {"customer": "Profiltech Sp. z o.o.",   "ral": "RAL 7035", "paint": "AKZ-7035-GL", "producer": "AkzoNobel",         "qty": 28, "area": 58.0,  "days": 8},
    {"customer": "Metal-Bud Zając",          "ral": "RAL 9010", "paint": "AKZ-9010-GL", "producer": "AkzoNobel",         "qty": 14, "area": 28.0,  "days": 15},
    {"customer": "Okno-System",              "ral": "RAL 7016", "paint": "TIG-7016-MA", "producer": "Tiger",             "qty": 40, "area": 85.0,  "days": 3},
    {"customer": "Aluprofil Kowalski",       "ral": "RAL 5010", "paint": "TIG-5010-MA", "producer": "Tiger",             "qty": 9,  "area": 18.0,  "days": 11},
    {"customer": "Fasada Group",             "ral": "RAL 7016", "paint": "TIG-7016-MA", "producer": "Tiger",             "qty": 20, "area": 42.0,  "days": 7},
    {"customer": "TechnoAlum",               "ral": "RAL 9005", "paint": "AKZ-9005-MA", "producer": "AkzoNobel",         "qty": 33, "area": 68.0,  "days": 2},
    {"customer": "Profiltech Sp. z o.o.",   "ral": "RAL 3020", "paint": "SHW-3020-GL", "producer": "Sherwin-Williams",  "qty": 11, "area": 22.0,  "days": 20},
    {"customer": "Metal-Bud Zając",          "ral": "RAL 5010", "paint": "TIG-5010-MA", "producer": "Tiger",             "qty": 19, "area": 40.0,  "days": 6},
    {"customer": "Okno-System",              "ral": "RAL 3020", "paint": "SHW-3020-GL", "producer": "Sherwin-Williams",  "qty": 27, "area": 54.0,  "days": 4},
    {"customer": "Aluprofil Kowalski",       "ral": "RAL 9005", "paint": "AKZ-9005-MA", "producer": "AkzoNobel",         "qty": 13, "area": 26.0,  "days": 13},
    {"customer": "Fasada Group",             "ral": "RAL 5010", "paint": "TIG-5010-MA", "producer": "Tiger",             "qty": 21, "area": 44.0,  "days": 9},
    {"customer": "TechnoAlum",               "ral": "RAL 7035", "paint": "AKZ-7035-GL", "producer": "AkzoNobel",         "qty": 17, "area": 35.0,  "days": 5},
    {"customer": "Profiltech Sp. z o.o.",   "ral": "RAL 9010", "paint": "AKZ-9010-GL", "producer": "AkzoNobel",         "qty": 32, "area": 65.0,  "days": 16},
    {"customer": "Metal-Bud Zając",          "ral": "RAL 3020", "paint": "SHW-3020-GL", "producer": "Sherwin-Williams",  "qty": 24, "area": 50.0,  "days": 10},
    {"customer": "Okno-System",              "ral": "RAL 5010", "paint": "TIG-5010-MA", "producer": "Tiger",             "qty": 7,  "area": 14.0,  "days": 18},
    {"customer": "Aluprofil Kowalski",       "ral": "RAL 7016", "paint": "TIG-7016-MA", "producer": "Tiger",             "qty": 36, "area": 75.0,  "days": 3},
    {"customer": "Fasada Group",             "ral": "RAL 9005", "paint": "AKZ-9005-MA", "producer": "AkzoNobel",         "qty": 15, "area": 30.0,  "days": 7},
    {"customer": "TechnoAlum",               "ral": "RAL 3020", "paint": "SHW-3020-GL", "producer": "Sherwin-Williams",  "qty": 29, "area": 60.0,  "days": None},
    {"customer": "Profiltech Sp. z o.o.",   "ral": "RAL 5010", "paint": "TIG-5010-MA", "producer": "Tiger",             "qty": 23, "area": 47.0,  "days": None},
    {"customer": "Metal-Bud Zając",          "ral": "RAL 7035", "paint": "AKZ-7035-GL", "producer": "AkzoNobel",         "qty": 10, "area": 20.0,  "days": 22},
    {"customer": "Okno-System",              "ral": "RAL 9005", "paint": "AKZ-9005-MA", "producer": "AkzoNobel",         "qty": 38, "area": 80.0,  "days": 1},
    {"customer": "Aluprofil Kowalski",       "ral": "RAL 3020", "paint": "SHW-3020-GL", "producer": "Sherwin-Williams",  "qty": 16, "area": 33.0,  "days": 8},
    {"customer": "Fasada Group",             "ral": "RAL 7035", "paint": "AKZ-7035-GL", "producer": "AkzoNobel",         "qty": 26, "area": 52.0,  "days": 19},
    {"customer": "TechnoAlum",               "ral": "RAL 9010", "paint": "AKZ-9010-GL", "producer": "AkzoNobel",         "qty": 12, "area": 24.0,  "days": None},
    {"customer": "Profiltech Sp. z o.o.",   "ral": "RAL 7016", "paint": "TIG-7016-MA", "producer": "Tiger",             "qty": 31, "area": 63.0,  "days": 17},
    {"customer": "Metal-Bud Zając",          "ral": "RAL 9010", "paint": "AKZ-9010-GL", "producer": "AkzoNobel",         "qty": 8,  "area": 16.0,  "days": 5},
    {"customer": "Okno-System",              "ral": "RAL 7016", "paint": "TIG-7016-MA", "producer": "Tiger",             "qty": 45, "area": 92.0,  "days": None},
    {"customer": "Aluprofil Kowalski",       "ral": "RAL 9010", "paint": "AKZ-9010-GL", "producer": "AkzoNobel",         "qty": 20, "area": 41.0,  "days": 25},
    {"customer": "Fasada Group",             "ral": "RAL 7016", "paint": "TIG-7016-MA", "producer": "Tiger",             "qty": 14, "area": 29.0,  "days": 12},
]

assert len(_ORDERS) == 40, f"Expected 40 orders, got {len(_ORDERS)}"


def main() -> None:
    session_factory = get_session_factory()
    session = session_factory()

    try:
        work_order_service = WorkOrderService(WorkOrderRepository(session))
        today = date.today()

        for i, o in enumerate(_ORDERS, start=1):
            pickup = today + timedelta(days=o["days"]) if o["days"] is not None else None
            payload = WorkOrderCreate(
                title=f"Zlecenie sortowania #{i}",
                total_quantity=o["qty"],
                description=f"{o['customer']} / {o['ral']}",
                customer_name=o["customer"],
                ral_code=o["ral"],
                paint_code=o["paint"],
                paint_producer=o["producer"],
                coating_type=CoatingType.RAL,
                received_date=today,
                planned_pickup_date=pickup,
                total_area_m2=o["area"],
                profiles_to_count=True,
                accessories_to_count=True,
            )
            work_order_service.create_work_order(payload)

        print(f"Utworzono {len(_ORDERS)} zleceń testowych.")
        print()

        from collections import Counter
        colors = Counter(o["ral"] for o in _ORDERS)
        firms = Counter(o["customer"] for o in _ORDERS)

        print("Kolory (powtórzenia):")
        for ral, count in sorted(colors.items()):
            print(f"  {ral}: {count}×")

        print()
        print("Firmy (powtórzenia):")
        for firm, count in sorted(firms.items()):
            print(f"  {firm}: {count}×")

        no_date = sum(1 for o in _ORDERS if o["days"] is None)
        print(f"\nZlecenia bez terminu (trafią na koniec przy sortowaniu): {no_date}")

    finally:
        session.close()


if __name__ == "__main__":
    main()
