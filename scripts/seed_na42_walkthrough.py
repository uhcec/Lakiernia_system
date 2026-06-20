"""Park three work orders in the exact states needed to *click-verify* NA42 (AUTOMATIC has no
PRODUCTION stage, MANUAL has no HANGING) without creating any order by hand.

Run AFTER the normal seed (which creates the login accounts), then just open the app and click:

    python scripts/reset_and_seed_dev_db.py      # logins + base data
    python scripts/seed_na42_walkthrough.py      # parks the 3 walkthrough orders

It only APPENDS orders; it does not reset the database.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Resolve `app`/`scripts` when run as `python scripts/seed_na42_walkthrough.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select

from app.audit.context import StationContext
from app.database.session import get_session_factory
from app.manager.repository import ManagerRepository
from app.manager.service import ManagerService
from app.process.enums import CoatingType, ProcessStage, ProductionType
from app.paints.schemas import PaintDeliveryCreate
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
    finish_surface_preparation,
    start_surface_preparation,
)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Polish output on a cp1252 Windows console
    except Exception:
        pass
    session = get_session_factory()()
    try:
        work_order_service = WorkOrderService(WorkOrderRepository(session))
        process_service = ProcessService(ProcessRepository(session))
        manager_service = ManagerService(ManagerRepository(session))

        next_position = (session.scalar(select(func.max(WorkOrder.queue_position))) or 0) + 1

        def stock_paint(order: WorkOrder, kg: float = 80.0) -> None:
            # Ensure the order's paint card has enough stock for a real UI paint-consumption entry.
            process_service.paint_service.record_delivery(
                PaintDeliveryCreate(
                    ral_code=order.ral_code,
                    paint_producer=order.paint_producer,
                    paint_code=order.paint_code,
                    quantity_kg=kg,
                ),
                station_context=None,
            )

        # --- WALK-A: AUTOMATIC, on the line, paint NOT recorded yet -------------------------------
        # Plan automatic, surface-prep done, HANGING in progress. Paint not entered and hanging not
        # finished on purpose, so the automatic-production panel shows the paint form and packing is
        # still gated. This is the heart of the NA42 view check.
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
        assign_plan(manager_service, walk_a.id, ProductionType.AUTOMATIC, next_position)
        next_position += 1
        start_surface_preparation(process_service, walk_a.id, counted_quantity=100)
        finish_surface_preparation(process_service, walk_a.id)
        # NOTE: WALK-A's HANGING start is deferred to the very end — HANGING is an exclusive resource,
        # and WALK-C below also runs through hanging; A must claim the line last so it stays held.

        # --- WALK-B: MANUAL, planned + surface-prep done ------------------------------------------
        # Should NOT appear on /zawieszanie (manual has no hanging) and SHOULD appear on /produkcja-reczna.
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
        assign_plan(manager_service, walk_b.id, ProductionType.MANUAL, next_position)
        next_position += 1
        start_surface_preparation(process_service, walk_b.id, counted_quantity=40)
        finish_surface_preparation(process_service, walk_b.id)

        # --- WALK-C: AUTOMATIC returned to planning after a packing correction ---------------------
        # Re-planning it as MANUAL must succeed (this is the method-switch-on-replan case that used to
        # 409). It is left unplanned, waiting for the manager to re-plan as Ręczna.
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
        assign_plan(manager_service, walk_c.id, ProductionType.AUTOMATIC, next_position)
        next_position += 1
        advance_to_packing(process_service, walk_c.id, counted_quantity=100)
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

        # Now claim the line for WALK-A (HANGING is free again — WALK-C finished hanging above).
        process_service.start_stage(walk_a.id, ProcessStage.HANGING)

        session.commit()

        print("NA42 walkthrough orders parked:\n")
        print(f"  WALK-A  {walk_a.order_number}  AUTOMATIC, hanging in progress, paint NOT yet recorded")
        print("          -> /produkcja-automat: card visible + paint (carton) form")
        print("          -> /pakowanie: active count row, 'Zakończ pakowanie' BLOCKED (hanging not done)")
        print("          -> finish hanging on /zawieszanie, then complete packing -> READY")
        print(f"  WALK-B  {walk_b.order_number}  MANUAL, surface-prep done")
        print("          -> /zawieszanie: NOT present (manual has no hanging)")
        print("          -> /produkcja-reczna: present")
        print(f"  WALK-C  {walk_c.order_number}  AUTOMATIC, returned to planning after a packing correction")
        print("          -> /kierownik: re-plan it as RĘCZNA at position 1 -> must succeed (no 409)")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
