"""Reset the local dev database to a CLEAN state with login accounts plus exactly three work orders
parked in the states needed to *click-verify* NA42 (AUTOMATIC has no PRODUCTION stage, MANUAL has no
HANGING) — no manual order creation, and no heavy demo data fighting the exclusive line resources.

    python scripts/seed_na42_walkthrough.py

Then log in (e.g. admin / adm1) and follow the printed click-path. This RESETS the database (same
guard as reset_and_seed_dev_db.py: development APP_ENV only).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Resolve `app`/`scripts` when run as `python scripts/seed_na42_walkthrough.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.audit.context import StationContext
from app.database.session import get_session_factory
from app.manager.repository import ManagerRepository
from app.manager.service import ManagerService
from app.paints.schemas import PaintDeliveryCreate
from app.process.enums import CoatingType, ProcessStage, ProductionType
from app.process.repository import ProcessRepository
from app.process.service import ProcessService
from app.shared.enums import StationId
from app.work_orders.models import WorkOrder
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.service import WorkOrderService
from scripts.reset_and_seed_dev_db import (
    advance_to_packing,
    assign_plan,
    create_work_order,
    ensure_local_dev_sqlite,
    finish_surface_preparation,
    reset_app_data,
    run_alembic_upgrade,
    start_surface_preparation,
)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    repo_root = Path(__file__).resolve().parents[1]
    database_path = ensure_local_dev_sqlite(repo_root)
    print(f"Using local development database: {database_path}")
    run_alembic_upgrade(repo_root)

    session = get_session_factory()()
    try:
        # Clean slate + login accounts / clients / employees / presence (no demo orders).
        reset_app_data(session)
        session.commit()

        work_order_service = WorkOrderService(WorkOrderRepository(session))
        process_service = ProcessService(ProcessRepository(session))
        manager_service = ManagerService(ManagerRepository(session))

        def stock_paint(order: WorkOrder, kg: float = 80.0) -> None:
            process_service.paint_service.record_delivery(
                PaintDeliveryCreate(
                    ral_code=order.ral_code,
                    paint_producer=order.paint_producer,
                    paint_code=order.paint_code,
                    quantity_kg=kg,
                ),
                station_context=None,
            )

        # --- WALK-A: AUTOMATIC, on the line, paint NOT recorded yet --------------------------------
        walk_a = create_work_order(
            work_order_service,
            title="NA42-A automat na linii",
            coating_type=CoatingType.RAL,
            total_quantity=100,
            customer_name="WALK Sp. z o.o.",
            ral_code="RAL 9005",
            profiles_quantity=80,
            accessories_quantity=20,
        )
        stock_paint(walk_a)  # so you can enter paint consumption from the automatic panel
        assign_plan(manager_service, walk_a.id, ProductionType.AUTOMATIC, 1)
        start_surface_preparation(process_service, walk_a.id, counted_quantity=100)
        finish_surface_preparation(process_service, walk_a.id)
        # HANGING start is deferred to the end (it claims the exclusive line; WALK-C uses it first).

        # --- WALK-B: MANUAL, planned + surface-prep done -------------------------------------------
        walk_b = create_work_order(
            work_order_service,
            title="NA42-B reczna bez zawieszania",
            coating_type=CoatingType.RAL,
            total_quantity=40,
            customer_name="WALK Sp. z o.o.",
            ral_code="RAL 7016",
            profiles_quantity=30,
            accessories_quantity=10,
        )
        assign_plan(manager_service, walk_b.id, ProductionType.MANUAL, 2)
        start_surface_preparation(process_service, walk_b.id, counted_quantity=40)
        finish_surface_preparation(process_service, walk_b.id)

        # --- WALK-C: AUTOMATIC returned to planning after a packing correction ---------------------
        walk_c = create_work_order(
            work_order_service,
            title="NA42-C poprawka + zmiana metody",
            coating_type=CoatingType.RAL,
            total_quantity=100,
            customer_name="WALK Sp. z o.o.",
            ral_code="RAL 5010",
            profiles_quantity=80,
            accessories_quantity=20,
        )
        assign_plan(manager_service, walk_c.id, ProductionType.AUTOMATIC, 3)
        advance_to_packing(process_service, walk_c.id, counted_quantity=100)  # runs through hanging, frees it
        process_service.complete_packing(
            walk_c.id,
            counted_quantity=100,
            ok_quantity=95,
            correction_quantity=5,
            correction_profiles_quantity=5,
            correction_accessories_quantity=0,
            correction_reason_category="niedomalowanie",
            station_context=StationContext(station_id=StationId.PACKING),
        )

        # Now claim the line for WALK-A (HANGING is free — WALK-C finished hanging above).
        process_service.start_stage(walk_a.id, ProcessStage.HANGING)

        session.commit()

        print("\nDatabase reset; NA42 walkthrough ready. Log in as admin / adm1.\n")
        print(f"  WALK-A  {walk_a.order_number}  AUTOMATIC, hanging in progress, paint NOT yet recorded")
        print("          /produkcja-automat: card visible + paint (carton) form -> enter paint")
        print("          /pakowanie: active count row, 'Zakończ pakowanie' BLOCKED (hanging not done)")
        print("          /zawieszanie: finish hanging -> /pakowanie: complete -> READY")
        print(f"  WALK-B  {walk_b.order_number}  MANUAL, surface-prep done")
        print("          /zawieszanie: NOT present (manual has no hanging); /produkcja-reczna: present")
        print(f"  WALK-C  {walk_c.order_number}  AUTOMATIC, back in planning after a packing correction")
        print("          /kierownik: re-plan as RĘCZNA at position 1 -> must succeed (no 409)")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
