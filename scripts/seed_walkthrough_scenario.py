"""Prepare a CLEAN local dev DB with exactly one order for a single S01-S12 walkthrough scenario.

Unlike `reset_and_seed_dev_db.py` (which seeds ~23 demo orders), this wipes all work orders and
creates just one order at its starting point — created in Office, awaiting planning — so the
NA21 scenario walkthrough (`docs/SCENARIO_WALKTHROUGH.md`) is easy to follow one scenario at a time.

The coating type is set here (it is chosen at intake); the production type (manual/automatic) and
all later steps are driven live in the UI during the walkthrough.

Usage (APP_ENV=development only):
    python scripts/seed_walkthrough_scenario.py S01
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.session import get_session_factory
from app.process.enums import CoatingType
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.service import WorkOrderService

from reset_and_seed_dev_db import (  # reuse the vetted helpers
    create_work_order,
    ensure_local_dev_sqlite,
    reset_app_data,
    run_alembic_upgrade,
)

# code -> (coating, human label). Quantity 10 splits cleanly for corrections (7 OK / 3 corr).
_SCENARIOS: dict[str, tuple[CoatingType, str]] = {
    "S01": (CoatingType.RAL, "RAL - reczna - bez poprawki"),
    "S02": (CoatingType.RAL, "RAL - automat - bez poprawki"),
    "S03": (CoatingType.DECORAL, "Decoral - reczna - bez poprawki"),
    "S04": (CoatingType.DECORAL, "Decoral - automat - bez poprawki"),
    "S05": (CoatingType.RAL, "RAL - reczna - poprawka po pakowaniu"),
    "S06": (CoatingType.RAL, "RAL - automat - poprawka po pakowaniu"),
    "S07": (CoatingType.DECORAL, "Decoral - reczna - poprawka po pakowaniu"),
    "S08": (CoatingType.DECORAL, "Decoral - automat - poprawka po pakowaniu"),
    "S09": (CoatingType.RAL, "RAL - reczna - wiele rund poprawek"),
    "S10": (CoatingType.RAL, "RAL - automat - wiele rund poprawek"),
    "S11": (CoatingType.DECORAL, "Decoral - reczna - wiele rund poprawek"),
    "S12": (CoatingType.DECORAL, "Decoral - automat - wiele rund poprawek"),
}

_QUANTITY = 10
_RAL_CODE = {CoatingType.RAL: "RAL 7016", CoatingType.DECORAL: "D-200"}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    if len(sys.argv) != 2 or sys.argv[1].upper() not in _SCENARIOS:
        print(f"Usage: python scripts/seed_walkthrough_scenario.py <{'|'.join(_SCENARIOS)}>")
        return 2

    code = sys.argv[1].upper()
    coating, label = _SCENARIOS[code]

    repo_root = Path(__file__).resolve().parents[1]
    ensure_local_dev_sqlite(repo_root)
    run_alembic_upgrade(repo_root)

    session = get_session_factory()()
    try:
        reset_app_data(session)  # wipe all work orders; reseed users/clients/employees/presence
        work_order_service = WorkOrderService(WorkOrderRepository(session))
        order = create_work_order(
            work_order_service,
            title=f"{code} - {label}",
            coating_type=coating,
            total_quantity=_QUANTITY,
            customer_name="TEST WALIDACJA",
            ral_code=_RAL_CODE[coating],
            profiles_quantity=8,
            accessories_quantity=2,
            notes=f"Walidacja {code}. Jedyne zlecenie w bazie - prowadz wg docs/SCENARIO_WALKTHROUGH.md.",
        )
        session.commit()
    finally:
        session.close()

    print("=" * 70)
    print(f"Gotowe pod {code} ({coating.value}, ilosc {_QUANTITY}).")
    print(f"  Zlecenie: {order.order_number}  |  tytul: {order.title}")
    print(f"  Stan: utworzone w Biurze, czeka na zaplanowanie (Do zaplanowania).")
    print("  Baza poza tym pusta - tylko to jedno zlecenie.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
