"""Reset the local dev DB and seed a curated demo of the N49 capacity planner + NA50 good-day stats.

Runs the full canonical baseline (`reset_and_seed_dev_db`: users, clients, foils, employees, the A–P
workflow scenarios, and a month of generic statistics) and then layers the data needed to *see* the
newest features:

- **Capacity board (N49-9) + multi-day plan (N49-4..N49-8):** a batch of active, planned AUTOMATIC orders
  with light→dark colours, mixed sizes (small/large vs the 100 m² band), and varied hard deadlines — so
  the board fills several days toward the floor/ceiling, groups colours light→dark, and flags a few
  orders that "won't make it" (infeasible banner).
- **Paint hard block + forward view (N49-7):** colours delivered into stock (OK), a colour delivered too
  thin so its run goes short partway (WARNING), a colour also used on the manual line then emptied
  (WARNING, never blocked), and a colour emptied *after* its orders were planned (BLOCKED on the board).
- **Good-day stats (NA50):** ~2 weeks of completed AUTOMATIC orders with realistic m², colour changes,
  and pickup deadlines — some days clear the 800 m² profit floor, some fall below; some ship on time,
  some late — so the "Dobry dzień" panel shows floor / on-time % / changeover loss / utilisation moving.

Run (development DB only — same guard as the base seed):
    APP_ENV=development python scripts/seed_n49_planner_walkthrough.py

Then log in (admin / adm1, or kierownik / ki1) and open the manager panel + Statystyki.
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

# Resolve `app` and the sibling `reset_and_seed_dev_db` when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select

import reset_and_seed_dev_db as base
from app.database.session import get_session_factory
from app.manager.repository import ManagerRepository
from app.manager.schemas import WorkOrderPlanAssignRequest
from app.manager.service import ManagerService
from app.paints.schemas import PaintDeliveryCreate, PaintManualAdjustmentCreate
from app.process.enums import CoatingType, ProcessStage, ProductionType, QuantityBatchType, StageStatus
from app.process.models import WorkOrderQuantityBatch
from app.process.service import ProcessService
from app.work_orders.models import WorkOrder
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.service import WorkOrderService

_CUSTOMERS = base._STATS_CUSTOMERS
SP, HG, PR, PK = base.SP, base.HG, base.PR, base.PK
IP, DONE = base.IP, base.DONE


def _paint_identity(ral: str) -> tuple[str, str, str]:
    code, producer = base._PAINT_BY_RAL[ral]
    return ral, producer, code


def _deliver(manager_service: ManagerService, ral: str, kg: float) -> None:
    ral_code, producer, code = _paint_identity(ral)
    manager_service.paint_service.record_delivery(
        PaintDeliveryCreate(ral_code=ral_code, paint_producer=producer, paint_code=code, quantity_kg=kg)
    )


def _empty_stock(manager_service: ManagerService, ral: str) -> None:
    """Bring a colour to a tracked 0 kg (a *known-depleted* balance the hard block can act on)."""
    ral_code, producer, code = _paint_identity(ral)
    look = manager_service.paint_service.lookup_current_stock(
        ral_code=ral_code, paint_producer=producer, paint_code=code
    )
    delta = -look.current_quantity_kg if look.current_quantity_kg > 0 else 0.0
    if delta == 0.0 and look.exists_in_inventory and manager_service.paint_service.has_stock_history(look.paint_id or 0):
        return
    # Ensure there is movement history even if it was never delivered, so it counts as *tracked*.
    if not look.exists_in_inventory or not (look.paint_id and manager_service.paint_service.has_stock_history(look.paint_id)):
        _deliver(manager_service, ral, 5.0)
        look = manager_service.paint_service.lookup_current_stock(ral_code=ral_code, paint_producer=producer, paint_code=code)
        delta = -look.current_quantity_kg
    manager_service.paint_service.record_manual_adjustment(
        PaintManualAdjustmentCreate(
            ral_code=ral_code, paint_producer=producer, paint_code=code,
            quantity_delta_kg=delta, note="Inwentaryzacja przy kabinie — wyzerowano",
        )
    )


def _plan_order(
    session,
    work_order_service: WorkOrderService,
    manager_service: ManagerService,
    *,
    title: str,
    ral: str,
    area: float,
    pickup_offset_days: int,
    production_type: ProductionType,
    customer: str,
    note: str,
) -> int:
    quantity = max(int(area / 8), 4)
    work_order = base.create_work_order(
        work_order_service,
        title=title,
        coating_type=CoatingType.RAL,
        total_quantity=quantity,
        customer_name=customer,
        ral_code=ral,
        profiles_quantity=quantity,
        accessories_quantity=0,
        notes=note,
    )
    persisted = session.get(WorkOrder, work_order.id)
    persisted.total_area_m2 = float(area)
    persisted.planned_pickup_date = date.today() + timedelta(days=pickup_offset_days)
    session.flush()
    manager_service.assign_plan(
        work_order.id, WorkOrderPlanAssignRequest(production_type=production_type)
    )
    return work_order.id


def seed_planner_demo(
    session, work_order_service: WorkOrderService, manager_service: ManagerService
) -> None:
    # 1) Stock the colours the board will use (generous, so most orders read OK with real remaining kg).
    for ral, kg in [
        ("RAL 9010", 500.0), ("RAL 7035", 320.0), ("RAL 7016", 300.0),
        ("RAL 9005", 220.0), ("RAL 7040", 200.0),
    ]:
        _deliver(manager_service, ral, kg)
    _deliver(manager_service, "RAL 5010", 40.0)   # thin → its run goes short (WARNING)
    _deliver(manager_service, "RAL 6021", 120.0)  # in stock now; emptied later → BLOCKED

    # 2) The main automatic plan — light→dark colours, mixed sizes, comfortable deadlines. Fills ~3 days.
    plan: list[tuple[str, float, int]] = [
        ("RAL 9010", 250, 9), ("RAL 9010", 200, 11),   # white, grouped
        ("RAL 7035", 180, 8), ("RAL 7035", 220, 12),   # light grey, grouped
        ("RAL 7016", 300, 7), ("RAL 7016", 150, 10),   # dark grey, grouped
        ("RAL 9005", 200, 13),                          # black
        ("RAL 7040", 120, 14),
        ("RAL 5010", 150, 9), ("RAL 5010", 150, 12),   # blue — second one runs short on paint
        ("RAL 6021", 180, 8), ("RAL 6021", 160, 11),   # green — emptied after planning → BLOCKED
    ]
    for index, (ral, area, pickup) in enumerate(plan, start=1):
        _plan_order(
            session, work_order_service, manager_service,
            title=f"Automat plan #{index} ({ral})",
            ral=ral, area=area, pickup_offset_days=pickup,
            production_type=ProductionType.AUTOMATIC,
            customer=_CUSTOMERS[index % len(_CUSTOMERS)],
            note="N49 — pozycja planu automatu (tablica wielodniowa).",
        )

    # 3) Two big orders already PAST their hard deadline → the "nie zdąży na termin" infeasible banner.
    for index, (ral, area) in enumerate([("RAL 7035", 280), ("RAL 7016", 260)], start=1):
        _plan_order(
            session, work_order_service, manager_service,
            title=f"Automat — po terminie #{index}",
            ral=ral, area=area, pickup_offset_days=-1,
            production_type=ProductionType.AUTOMATIC,
            customer=_CUSTOMERS[index % len(_CUSTOMERS)],
            note="N49 — termin już minął: pokazuje ostrzeżenie o niedotrzymaniu terminu.",
        )

    # 4) Manual-used WARNING: empty RAL 3020, plan it on MANUAL (so it's "manual-used"), then on AUTOMATIC
    #    — the automatic plan is allowed (low-confidence, not hard-blocked) and shows the paint warning.
    _empty_stock(manager_service, "RAL 3020")
    _plan_order(
        session, work_order_service, manager_service,
        title="Ręczna — kolor także na automacie (RAL 3020)",
        ral="RAL 3020", area=60, pickup_offset_days=10,
        production_type=ProductionType.MANUAL,
        customer=_CUSTOMERS[1], note="N49 — ten kolor jest też używany ręcznie (stan niepewny).",
    )
    _plan_order(
        session, work_order_service, manager_service,
        title="Automat — kolor używany ręcznie (RAL 3020)",
        ral="RAL 3020", area=90, pickup_offset_days=9,
        production_type=ProductionType.AUTOMATIC,
        customer=_CUSTOMERS[2], note="N49 — farba używana ręcznie: ostrzeżenie, nie twarda blokada.",
    )

    # 5) BLOCKED: empty an automatic-only colour *after* its order was planned → it flips to "brak farby"
    #    (a metered colour, out of stock) on the board. RAL 7040 is planned only on the automatic line,
    #    so it hard-blocks; RAL 6021 is also used on the manual line (baseline scenario K2), so emptying
    #    it only *warns* (low-confidence balance) — a deliberate contrast between the two cases.
    _empty_stock(manager_service, "RAL 7040")
    _empty_stock(manager_service, "RAL 6021")

    session.commit()
    print("Seeded N49 planner demo: 14 planned automatic orders + paint OK/WARNING/BLOCKED cases.")


def seed_good_day_history(session, work_order_service: WorkOrderService) -> None:
    """~2 weeks of completed AUTOMATIC orders with brackets, varied floor/on-time, for the NA50 panel."""
    today = date.today()
    # Light→dark-ish rotation with repeats so days have colour groups *and* changes.
    rals = ["RAL 9010", "RAL 9010", "RAL 7035", "RAL 7016", "RAL 5010", "RAL 9005", "RAL 7040"]
    # Per-stage (in_progress, done) minute offsets within the day; HANGING→PACKING brackets the pass.
    stage_times = {SP: (0, 8), HG: (12, 26), PR: (26, 70), PK: (70, 92)}
    queue_position = 5000
    made = 0

    for days_ago in range(1, 15):
        day = today - timedelta(days=days_ago)
        if day.weekday() >= 5:  # working days only (Mon–Fri), matching the planner calendar
            continue
        bucket = days_ago % 4
        if bucket == 0:
            areas = [70, 90, 60]                       # quiet day → below the 800 floor
        elif bucket == 1:
            areas = [220, 260, 200, 190]               # strong day → clears the floor
        elif bucket == 2:
            areas = [150, 120, 180, 140, 110, 130]     # busy day of mixed sizes → clears the floor
        else:
            areas = [300, 280, 260]                    # few big orders → clears the floor

        for k, area in enumerate(areas):
            ral = rals[(days_ago + k) % len(rals)]
            quantity = max(int(area / 8), 5)
            work_order = base.create_work_order(
                work_order_service,
                title=f"Automat {day.isoformat()} #{k + 1}",
                coating_type=CoatingType.RAL,
                total_quantity=quantity,
                customer_name=_CUSTOMERS[(days_ago + k) % len(_CUSTOMERS)],
                ral_code=ral,
                profiles_quantity=quantity,
                accessories_quantity=0,
                notes="N49 — historia do panelu „Dobry dzień”.",
            )
            persisted = session.get(WorkOrder, work_order.id)
            persisted.production_type = ProductionType.AUTOMATIC
            persisted.queue_position = queue_position
            persisted.total_area_m2 = float(area)
            persisted.completed_quantity = quantity
            queue_position += 1
            # Some orders ship late (packing day after the deadline); most on time — so on-time % visibly
            # dips on some days rather than sitting at a flat 100%.
            late = (k % 3 == 0)
            persisted.planned_pickup_date = (day - timedelta(days=1)) if late else (day + timedelta(days=4))

            base_dt = datetime(day.year, day.month, day.day, 7 + k, 0, tzinfo=UTC)
            sequence = ProcessService.get_stage_sequence_for_configuration(
                CoatingType.RAL, ProductionType.AUTOMATIC
            )
            for stage in sequence:
                ip_off, done_off = stage_times[stage]
                base._set_stage_state(
                    session, work_order.id, stage, DONE, base_dt + timedelta(minutes=done_off),
                    counted_quantity=quantity if stage in (SP, PK) else None,
                )
                base._add_stage_event(session, work_order.id, stage, IP, base_dt + timedelta(minutes=ip_off))
                base._add_stage_event(session, work_order.id, stage, DONE, base_dt + timedelta(minutes=done_off))

            main_batch = session.scalar(
                select(WorkOrderQuantityBatch).where(
                    WorkOrderQuantityBatch.work_order_id == work_order.id,
                    WorkOrderQuantityBatch.type == QuantityBatchType.MAIN,
                )
            )
            if main_batch is not None:
                main_batch.is_active = False
                main_batch.current_stage = sequence[-1]
                main_batch.current_stage_status = DONE
            session.flush()
            made += 1

    session.commit()
    print(f"Seeded good-day history: {made} completed automatic orders across recent working days.")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    repo_root = Path(__file__).resolve().parents[1]
    database_path = base.ensure_local_dev_sqlite(repo_root)
    print(f"Using local development database: {database_path}")
    base.run_alembic_upgrade(repo_root)

    session = get_session_factory()()
    try:
        base.reset_app_data(session)
        base.seed_all_use_cases(session)  # full baseline: A–P scenarios + a month of generic stats

        work_order_service = WorkOrderService(WorkOrderRepository(session))
        manager_service = ManagerService(ManagerRepository(session))
        seed_planner_demo(session, work_order_service, manager_service)
        seed_good_day_history(session, work_order_service)
    finally:
        session.close()

    print("\n=== N49 / NA50 walkthrough ready ===")
    print("Login: admin / adm1   (or kierownik / ki1)")
    print("- Panel kierownika → 'Plan wielodniowy' (capacity board): days vs floor/ceiling, light→dark")
    print("    colours, 'po terminie' + paint 'brak farby' / 'farba na wyczerpaniu' flags, infeasible banner.")
    print("- Stacje wspólne (Przygotowanie powierzchni / Pakowanie): line labels + 'NASTĘPNE' (N49-10).")
    print("- Statystyki → 'Dobry dzień': m² vs próg, terminowość %, strata na zmianach koloru, wykorzystanie.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
