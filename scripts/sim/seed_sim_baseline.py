"""Seed a *clean* development baseline for the workflow simulation.

Unlike ``scripts/reset_and_seed_dev_db.py`` (which seeds the full S01-S12 scenario matrix plus a month
of statistics), this leaves **zero work orders**: the office persona (``biuro``) invents the orders
during the run, so the captured flow is genuinely emergent. It reuses the reset script's own helpers
for the local.db guard, the Alembic upgrade, and the users/clients/foils/employees/presence baseline.

Development-only: ``ensure_local_dev_sqlite`` refuses anything that is not the local SQLite ``local.db``.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_SCRIPTS_DIR))

import reset_and_seed_dev_db as base  # noqa: E402  (path set up above)
from app.audit.context import StationContext  # noqa: E402
from app.database.session import get_session_factory  # noqa: E402
from app.paints.repository import PaintRepository  # noqa: E402
from app.paints.schemas import PaintDeliveryCreate  # noqa: E402
from app.paints.service import PaintService  # noqa: E402
from app.shared.enums import StationId  # noqa: E402

# Generous starting stock per colour so AUTOMATIC orders can record paint consumption and DECORAL orders
# can run without hitting the planner's paint hard-block during a light simulated run.
_STOCK_PER_COLOUR_KG = 300.0


def seed_paint_stock(session) -> None:
    """Deliver starting stock for every known colour (``reset_and_seed_dev_db._PAINT_BY_RAL``).

    Uses the real ``PaintService.record_delivery`` path (auto-creates the paint + a DELIVERY movement), so
    the inventory looks exactly as it would after a real delivery — not hand-poked rows."""
    service = PaintService(PaintRepository(session))
    office = StationContext(station_id=StationId.OFFICE)
    from datetime import date

    for ral_code, (paint_code, producer) in base._PAINT_BY_RAL.items():
        service.record_delivery(
            PaintDeliveryCreate(
                ral_code=ral_code,
                paint_producer=producer,
                paint_code=paint_code,
                quantity_kg=_STOCK_PER_COLOUR_KG,
                movement_date=date.today(),
                note="Symulacja — zapas startowy.",
            ),
            station_context=office,
        )
    print(f"Seeded {_STOCK_PER_COLOUR_KG:.0f} kg starting stock for {len(base._PAINT_BY_RAL)} colours.")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    database_path = base.ensure_local_dev_sqlite(_REPO_ROOT)
    print(f"Using local development database: {database_path}")
    base.run_alembic_upgrade(_REPO_ROOT)

    session = get_session_factory()()
    try:
        base.reset_app_data(session)  # users + clients + foils + employees + presence; clears all orders
        seed_paint_stock(session)
    finally:
        session.close()

    print("Simulation baseline ready: station users, clients, foils, employees + paint stock seeded; zero work orders.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
