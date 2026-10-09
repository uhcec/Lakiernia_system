"""Reset the local dev DB to a CLEAN, curated state for click-testing everything new since 2026-06-20
(NA36 drawings, NA38 foils, NA34 stat-only corrections, NA32 cumulative paint, NA44 labels/overdue,
NA35 wheel, NA31 manager position-1, NA30 completion invariant, NA42 regression).

    python scripts/seed_new_features_walkthrough.py

Each order is parked at the exact point where one feature is tested with one or two clicks — no repeated
setup. Also writes ready-to-upload sample files to ./walkthrough_files/. RESETS the database (same guard
as reset_and_seed_dev_db.py: development APP_ENV only). Then log in (admin / adm1) and follow the printed
map (or WALKTHROUGH_NOWOSCI.md).
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

# Resolve `app`/`scripts` when run as `python scripts/seed_new_features_walkthrough.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select

from app.database.session import get_session_factory
from app.foils.models import Foil
from app.paints.models import Paint, PaintStockMovement
from app.manager.repository import ManagerRepository
from app.manager.service import ManagerService
from app.paints.schemas import PaintDeliveryCreate
from app.process.enums import CoatingType, ProcessStage, ProductionType
from app.process.repository import ProcessRepository
from app.process.service import ProcessService
from app.work_orders.models import WorkOrder
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.service import WorkOrderService
from scripts.reset_and_seed_dev_db import (
    PDF_BYTES,
    PNG_BYTES,
    assign_plan,
    create_attachment,
    create_work_order,
    ensure_local_dev_sqlite,
    finish_surface_preparation,
    reset_app_data,
    run_alembic_upgrade,
    start_surface_preparation,
)


def _write_sample_upload_files(repo_root: Path) -> Path:
    folder = repo_root / "walkthrough_files"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "rysunek-techniczny.png").write_bytes(PNG_BYTES)
    (folder / "dokument.pdf").write_bytes(PDF_BYTES)
    (folder / "zly-plik.txt").write_bytes(b"to nie jest PDF ani obraz")
    return folder


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    repo_root = Path(__file__).resolve().parents[1]
    database_path = ensure_local_dev_sqlite(repo_root)
    print(f"Using local development database: {database_path}")
    run_alembic_upgrade(repo_root)
    sample_dir = _write_sample_upload_files(repo_root)

    session = get_session_factory()()
    try:
        # Clean slate + logins + clients + the 3 seed foils + employees (no demo orders).
        reset_app_data(session)
        # reset_app_data does NOT clear the paint tables; leftover stock movements from a previous seed
        # would (via SQLite id reuse) contaminate the NA32 cumulative-consumption rollup. Clear them so
        # paint starts empty and 0002 reports exactly 18 + 4 kg.
        session.execute(delete(PaintStockMovement))
        session.execute(delete(Paint))
        session.commit()

        wo_repo = WorkOrderRepository(session)
        work_order_service = WorkOrderService(wo_repo)
        process_service = ProcessService(ProcessRepository(session))
        manager_service = ManagerService(ManagerRepository(session))

        position = iter(range(1, 100))

        def plan(order: WorkOrder, method: ProductionType) -> None:
            assign_plan(manager_service, order.id, method, next(position))

        def stock(order: WorkOrder, kg: float) -> None:
            process_service.paint_service.record_delivery(
                PaintDeliveryCreate(
                    ral_code=order.ral_code,
                    paint_producer=order.paint_producer,
                    paint_code=order.paint_code,
                    quantity_kg=kg,
                ),
                station_context=None,
            )

        seeded_foil = session.scalars(select(Foil).order_by(Foil.id.asc())).first()
        foil_id = seeded_foil.id if seeded_foil is not None else None

        # === FOIL — Decoral order with a chosen foil, parked on the Decoral pass (NA38) =============
        # Released its packing slot at completion; shows on /decoral and on the detail page.
        foil_order = create_work_order(
            work_order_service,
            title="Decoral z folią",
            coating_type=CoatingType.DECORAL,
            total_quantity=9,
            customer_name="Fasada Polska",
            ral_code="D-200",
            decoral_foil_id=foil_id,
            profiles_quantity=8,
            accessories_quantity=1,
            notes="NA38: wybrana folia widoczna na karcie /decoral i w szczegółach.",
        )
        plan(foil_order, ProductionType.MANUAL)
        start_surface_preparation(process_service, foil_order.id, counted_quantity=9)
        finish_surface_preparation(process_service, foil_order.id)
        process_service.start_stage(foil_order.id, ProcessStage.PRODUCTION)
        process_service.finish_stage(foil_order.id, ProcessStage.PRODUCTION)
        process_service.start_packing(foil_order.id)
        process_service.complete_packing(foil_order.id, counted_quantity=9, ok_quantity=9, correction_quantity=0)

        # === PAINT — AUTOMATIC, two correction rounds with paint in BOTH; ends READY (NA32 + NA30) ==
        paint_order = create_work_order(
            work_order_service,
            title="Automat - farba sumarycznie",
            coating_type=CoatingType.RAL,
            total_quantity=100,
            customer_name="Konstrukcje Stalowe S.A.",
            ral_code="RAL 9006",
            profiles_quantity=80,
            accessories_quantity=20,
            notes="NA32: zużycie farby ma się sumować przez rundy korekty (18 + 4 = 22 kg).",
        )
        stock(paint_order, 200.0)
        # --- round 1: paint 18 kg, then a packing correction of 10 pcs (RAL → back to planning) ---
        plan(paint_order, ProductionType.AUTOMATIC)
        start_surface_preparation(process_service, paint_order.id, counted_quantity=100)
        finish_surface_preparation(process_service, paint_order.id)
        process_service.start_stage(paint_order.id, ProcessStage.HANGING)  # automatic: implicitly starts packing
        process_service.finish_stage(paint_order.id, ProcessStage.HANGING)
        # CHANGES #22: consumption is entered once per paint run, after its hanging finished.
        process_service.record_paint_run_consumption(
            process_service.list_open_paint_runs().runs[-1].id, consumed_kg=18.0
        )
        process_service.complete_packing(
            paint_order.id,
            counted_quantity=100,
            ok_quantity=90,
            correction_quantity=10,
            correction_profiles_quantity=10,
            correction_accessories_quantity=0,
            correction_reason_category="niedomalowanie",
        )
        # --- round 2: re-plan, paint 4 kg, finish to READY (correction skips surface prep) ---
        plan(paint_order, ProductionType.AUTOMATIC)
        process_service.start_stage(paint_order.id, ProcessStage.HANGING)
        process_service.finish_stage(paint_order.id, ProcessStage.HANGING)
        # CHANGES #22: consumption is entered once per paint run, after its hanging finished.
        process_service.record_paint_run_consumption(
            process_service.list_open_paint_runs().runs[-1].id, consumed_kg=4.0
        )
        process_service.complete_packing(paint_order.id, counted_quantity=10, ok_quantity=10, correction_quantity=0)

        # === DRAW — MANUAL at production, with a technical drawing + overdue pickup (NA36 + NA44) ===
        draw_order = create_work_order(
            work_order_service,
            title="Ręczna z rysunkiem",
            coating_type=CoatingType.RAL,
            total_quantity=30,
            customer_name="Meble Loft",
            ral_code="RAL 7016",
            profiles_quantity=24,
            accessories_quantity=6,
            notes="NA36: rysunek techniczny widoczny na karcie /produkcja-reczna. NA44: PO TERMINIE.",
        )
        plan(draw_order, ProductionType.MANUAL)
        start_surface_preparation(process_service, draw_order.id, counted_quantity=30)
        finish_surface_preparation(process_service, draw_order.id)
        process_service.start_stage(draw_order.id, ProcessStage.PRODUCTION)  # parked at manual production
        create_attachment(wo_repo, draw_order.id)  # seeds a DOCUMENT pdf + a TECHNICAL_DRAWING png
        # Make it overdue (planned pickup in the past, not READY).
        draw_db = session.get(WorkOrder, draw_order.id)
        draw_db.planned_pickup_date = date.today() - timedelta(days=3)
        session.flush()

        # === PACK-FIX — MANUAL at packing, started (NA34: "od razu poprawiona" / stat-only) ========
        pack_fix = create_work_order(
            work_order_service,
            title="Pakowanie - poprawka od razu",
            coating_type=CoatingType.RAL,
            total_quantity=20,
            customer_name="Hale Profil",
            ral_code="RAL 5010",
            profiles_quantity=16,
            accessories_quantity=4,
            notes='NA34: zaznacz "Od razu poprawiona" — zlecenie kończy się jako Gotowe, korekta w statystykach.',
        )
        plan(pack_fix, ProductionType.MANUAL)
        start_surface_preparation(process_service, pack_fix.id, counted_quantity=20)
        finish_surface_preparation(process_service, pack_fix.id)
        process_service.start_stage(pack_fix.id, ProcessStage.PRODUCTION)
        process_service.finish_stage(pack_fix.id, ProcessStage.PRODUCTION)
        process_service.start_packing(pack_fix.id)  # claims packing slot 1

        # === PACK-REPLAN — MANUAL at packing, started (NA34 "do zaplanowania" → NA31 manager) ======
        pack_replan = create_work_order(
            work_order_service,
            title="Pakowanie - do zaplanowania",
            coating_type=CoatingType.RAL,
            total_quantity=20,
            customer_name="Hale Profil",
            ral_code="RAL 6005",
            profiles_quantity=16,
            accessories_quantity=4,
            notes='NA34/NA31: zaznacz "Do zaplanowania" — wraca do /kierownik, planuj na pozycji 1 bez F5.',
        )
        plan(pack_replan, ProductionType.MANUAL)
        start_surface_preparation(process_service, pack_replan.id, counted_quantity=20)
        finish_surface_preparation(process_service, pack_replan.id)
        process_service.start_stage(pack_replan.id, ProcessStage.PRODUCTION)
        process_service.finish_stage(pack_replan.id, ProcessStage.PRODUCTION)
        process_service.start_packing(pack_replan.id, override=True)  # opens packing slot 2

        session.commit()

        # --- printed map -------------------------------------------------------------------------
        print("\n================  NOWOŚCI — gotowe do klikania  ================")
        print("Zaloguj się jako  admin / adm1  (pełny dostęp do wszystkich ekranów).")
        print(f"Pliki do wgrania (NA36) leżą w:  {sample_dir}")
        print("\nZlecenia (numer → co testujesz):")
        rows = [
            (foil_order.order_number, "NA38", "/folie + /decoral + szczegóły",
             "Rejestr folii; karta Decoral i szczegóły pokazują wybraną folię."),
            (draw_order.order_number, "NA36 + NA44", "/produkcja-reczna + /biuro",
             'Link "Rysunki techniczne" na karcie; w /biuro etykieta "Produkcja ręczna" i "PO TERMINIE".'),
            (pack_fix.order_number, "NA34", "/pakowanie",
             'Zakończ z korektą → "Od razu poprawiona": zlecenie = Gotowe, brak powrotu.'),
            (pack_replan.order_number, "NA34 + NA31", "/pakowanie → /kierownik",
             'Zakończ z korektą → "Do zaplanowania": wraca do planowania; w /kierownik pozycja 1 bez F5.'),
            (paint_order.order_number, "NA32 + NA30", "szczegóły zlecenia",
             "Zużyta farba = 22 kg (18+4) sumarycznie; stan farby -22 kg. (Gotowe — patrz NA30 opcjonalnie.)"),
        ]
        for number, tag, screen, what in rows:
            print(f"  - {number}  [{tag}]")
            print(f"      ekran: {screen}")
            print(f"      {what}")
        print("\nNA35 (scroll) + NA38 (picker): utwórz NOWE zlecenie Decoral w /biuro,")
        print("   wybierz folię (pole pojawia się tylko dla Decoral), a kółkiem myszy w polach")
        print("   liczbowych sprawdź, że zmienia o całe jednostki (bez 20.3).")
        print("=================================================================\n")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
