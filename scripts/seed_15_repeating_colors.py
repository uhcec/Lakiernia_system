"""Wyczyść wszystkie zlecenia i utwórz 15 nowych zleceń na powtarzające się kolory.

Czyści TYLKO dane związane ze zleceniami (zlecenia, partie, etapy, załączniki, logi etapów,
zdarzenia audytu, blokady zasobów, licznik numerów). Zostawia użytkowników/loginy, klientów,
pracowników i ich obecność na stanowiskach, więc od razu można się zalogować i planować.

Zlecenia powstają jako niezaplanowane (do zaplanowania przez kierownika), RAL, po 4 kolory
w rotacji — każdy kolor powtarza się na kilku zleceniach.

Uruchom:  python scripts/seed_15_repeating_colors.py   (wymaga APP_ENV=development)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import date, timedelta

from sqlalchemy import delete

from app.audit.models import AuditEvent, AuditEventActor
from app.core.config import get_settings
from app.database import models as _models  # noqa: F401  (rejestr modeli)
from app.database.session import get_session_factory
from app.process.enums import CoatingType
from app.process.models import (
    ProcessResourceLock,
    StageTransitionEvent,
    WorkOrderQuantityBatch,
    WorkOrderStageState,
)
from app.work_orders.models import WorkOrder, WorkOrderAttachment, WorkOrderNumberCounter
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import WorkOrderCreate
from app.work_orders.service import WorkOrderService

# 4 powtarzające się kolory (kod RAL -> kod farby, producent).
PALETTE: list[tuple[str, str, str]] = [
    ("RAL 7016", "TIG-7016-MA", "Tiger"),          # antracyt
    ("RAL 9005", "AKZ-9005-MA", "AkzoNobel"),      # czarny
    ("RAL 9010", "AKZ-9010-GL", "AkzoNobel"),      # biały
    ("RAL 8017", "AKZ-8017-MA", "AkzoNobel"),      # brąz
]

CUSTOMERS = ["Profiltech Sp. z o.o.", "Aluminco", "Metal-Bud Zając"]

TITLES = [
    "Profile okienne", "Ramy drzwiowe", "Listwy elewacyjne", "Balustrady",
    "Kształtowniki", "Osłony techniczne", "Panele fasadowe", "Zestawy roletowe",
]


def reset_orders_only(session) -> None:
    """Usuń wszystkie dane zleceń, zostaw użytkowników/klientów/pracowników."""
    session.execute(delete(AuditEventActor))
    session.execute(delete(AuditEvent))
    session.execute(delete(StageTransitionEvent))
    session.execute(delete(ProcessResourceLock))
    session.execute(delete(WorkOrderAttachment))
    session.execute(delete(WorkOrderStageState))
    session.execute(delete(WorkOrderQuantityBatch))
    session.execute(delete(WorkOrder))
    session.execute(delete(WorkOrderNumberCounter))  # numeracja od nowa
    session.commit()


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    settings = get_settings()
    if settings.app_env.lower() != "development":
        raise SystemExit("Odmowa: APP_ENV musi być 'development'.")

    today = date.today()
    pickup = today + timedelta(days=10)
    session_factory = get_session_factory()

    with session_factory() as session:
        reset_orders_only(session)
        print("Wyczyszczono wszystkie zlecenia.")

        repo = WorkOrderRepository(session)
        svc = WorkOrderService(repo)

        count_per_color: dict[str, int] = {}
        for i in range(15):
            ral_code, paint_code, producer = PALETTE[i % len(PALETTE)]
            customer = CUSTOMERS[i % len(CUSTOMERS)]
            title = TITLES[i % len(TITLES)]
            qty = 10 + (i % 6) * 4  # 10..30
            profiles = max(qty - 2, 1)
            accessories = qty - profiles

            payload = WorkOrderCreate(
                title=title,
                total_quantity=qty,
                description=f"{title} — {ral_code}",
                customer_name=customer,
                ral_code=ral_code,
                paint_code=paint_code,
                paint_producer=producer,
                coating_type=CoatingType.RAL,
                received_date=today,
                planned_pickup_date=pickup,
                total_area_m2=float(qty),
                profiles_quantity=profiles,
                accessories_quantity=accessories,
            )
            wo = svc.create_work_order(payload)
            count_per_color[ral_code] = count_per_color.get(ral_code, 0) + 1
            print(f"  {wo.order_number}  {ral_code:9s}  {customer:22s}  {qty} szt.")

    print("\nGotowe — utworzono 15 zleceń do zaplanowania.")
    print("Rozkład kolorów:")
    for ral_code, n in count_per_color.items():
        print(f"  {ral_code}: {n} zleceń")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
