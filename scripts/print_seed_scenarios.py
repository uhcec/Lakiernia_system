from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app.database import models as _models  # noqa: F401
from app.database.session import get_session_factory
from app.work_orders.models import WorkOrder
from reset_and_seed_dev_db import ensure_local_dev_sqlite


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    database_path = ensure_local_dev_sqlite(repo_root)

    print(f"Using local development database: {database_path}")
    print("Current seeded-style scenarios in the existing database:")

    session = get_session_factory()()
    try:
        work_orders = session.scalars(
            select(WorkOrder)
            .where(WorkOrder.notes.is_not(None))
            .order_by(WorkOrder.id.asc())
        ).all()
    finally:
        session.close()

    if not work_orders:
        print("No work orders with scenario notes were found. Run python scripts/reset_and_seed_dev_db.py first.")
        return 0

    for work_order in work_orders:
        print(f"- {work_order.order_number} | {work_order.title}")
        print(f"  Notes: {work_order.notes}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())