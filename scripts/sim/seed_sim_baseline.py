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
from app.database.session import get_session_factory  # noqa: E402


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
    finally:
        session.close()

    print("Simulation baseline ready: station users, clients, foils, employees seeded; zero work orders.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
