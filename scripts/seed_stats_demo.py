"""Demo seed for the new analytics + packing features (NA16–NA18).

Resets and re-seeds the base dev database, then appends a focused scenario so the changes from this
session are *visually* obvious in the running app:

- **Packing exclusivity (NA16):** two manual orders parked at packing, unclaimed — claim one to see the
  other flip to "Zajęte: pakowanie …", and use "Zwolnij stanowisko" to release.
- **Cycle-time + queue-wait (NA17):** several completed orders whose stage-transition-log timestamps are
  backdated across the current month, so the Statystyki "Czasy etapów" charts show real per-stage work
  time and queue waits (and the throughput charts get daily bars).
- **Live WIP-aging (NA18):** a handful of orders left genuinely IN_PROGRESS at different stages with
  backdated start times, so "Zlecenia w toku" shows varied ages (one over 24h, highlighted red).

Run it with:  ``python scripts/seed_stats_demo.py``  (development DB only — same guard as the base seed).
Driving the real workflow keeps every invariant valid; only the log's ``occurred_at`` values are
rewritten afterwards to place the work in time.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure THIS repo root resolves `app` (an editable install may otherwise shadow it with a copy
# at another path). Must run before importing `app` or the base seed module.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

import reset_and_seed_dev_db as base

from app.database.session import get_session_factory
from app.manager.repository import ManagerRepository
from app.manager.service import ManagerService
from app.process.enums import CoatingType, ProcessStage, ProductionType, StageStatus
from app.process.models import ProcessResourceLock, StageTransitionEvent
from app.process.repository import ProcessRepository
from app.process.service import ProcessService
from app.work_orders.models import WorkOrder
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.service import WorkOrderService

MIN = timedelta(minutes=1)


def main() -> int:
    # Reset + base seed first (alembic upgrade, users, clients, baseline scenarios A-P). We call the
    # base steps directly rather than base.main() so the demo overlay runs in the same session and we
    # skip base's Polish-text report print (crashes on Windows cp1252 consoles).
    repo_root = Path(__file__).resolve().parents[1]
    base.ensure_local_dev_sqlite(repo_root)
    base.run_alembic_upgrade(repo_root)

    session = get_session_factory()()
    try:
        base.reset_app_data(session)
        base.seed_all_use_cases(session)

        # The base seed parks automatic orders that reserve packing slots (NA22a). Free those slots so
        # the demo's manual completed orders below are not blocked by "all packing slots full".
        for lock in session.scalars(
            select(ProcessResourceLock).where(ProcessResourceLock.resource_key.like("PACKING:%"))
        ).all():
            session.delete(lock)
        session.flush()

        work_order_service = WorkOrderService(WorkOrderRepository(session))
        process_service = ProcessService(ProcessRepository(session))
        manager_service = ManagerService(ManagerRepository(session))

        queue_position = 1000  # well above the base seed's positions to avoid collisions
        now_ref = datetime.now(UTC)
        today = date.today()
        month_days = [d for d in (2, 5, 8, 11, 14, 17) if d <= today.day] or [today.day]

        queue_position = _seed_completed_for_cycle_time(
            work_order_service, process_service, manager_service, session, today, month_days, queue_position
        )
        queue_position = _seed_work_in_progress(
            work_order_service, process_service, manager_service, session, now_ref, queue_position
        )
        queue_position = _seed_packing_exclusivity(
            work_order_service, process_service, manager_service, queue_position
        )

        session.commit()
    finally:
        session.close()

    print("\n=== Stats/packing demo overlay seeded ===")
    print("Statystyki (login kierownik/ki1 or admin/adm1):")
    print("  - 'Zlecenia w toku' (top): live WIP-aging — varied ages, one >24h highlighted red.")
    print("  - 'Przepustowość': daily m² bars across the current month.")
    print("  - 'Czasy etapów': per-stage work time + queue wait, plus the lead-time headline.")
    print("Pakowanie (login pakowanie/pak1):")
    print("  - Orders 'DEMO Pakowanie A/B': click 'Rozpocznij pakowanie' on one →")
    print("    the other shows 'Zajęte: pakowanie …'; use 'Zwolnij stanowisko' to release.")
    return 0


def _create(work_order_service: WorkOrderService, *, title: str, coating: CoatingType, qty: int, ral: str, customer: str):
    return base.create_work_order(
        work_order_service,
        title=title,
        coating_type=coating,
        total_quantity=qty,
        customer_name=customer,
        ral_code=ral,
        profiles_quantity=max(qty - 1, 0),
        accessories_quantity=1,
        notes=title,
    )


def _backdate(session: Session, work_order_id: int, schedule: dict[tuple[ProcessStage, StageStatus], datetime]) -> None:
    events = session.scalars(
        select(StageTransitionEvent).where(StageTransitionEvent.work_order_id == work_order_id)
    ).all()
    for event in events:
        moment = schedule.get((event.stage, event.status))
        if moment is not None:
            event.occurred_at = moment
    session.flush()


def _seed_completed_for_cycle_time(
    work_order_service, process_service, manager_service, session, today, month_days, queue_position
) -> int:
    # Manual completed orders with varied production durations → meaningful per-stage averages + waits.
    manual_specs = [
        ("RAL 7016", "Profiltech Sp. z o.o.", 24, 45),
        ("RAL 9005", "Aluminco", 18, 55),
        ("RAL 7035", "Metal-Bud Zając", 30, 38),
        ("RAL 3020", "Technoalum", 12, 62),
        ("RAL 5010", "Stalmet", 20, 50),
    ]
    for index, (ral, customer, qty, prod_min) in enumerate(manual_specs):
        order = _create(work_order_service, title=f"DEMO Ukończone manual {index + 1}", coating=CoatingType.RAL, qty=qty, ral=ral, customer=customer)
        base.assign_plan(manager_service, order.id, ProductionType.MANUAL, queue_position)
        queue_position += 10
        base.advance_to_packing(process_service, order.id, counted_quantity=qty)
        process_service.complete_packing(order.id, counted_quantity=qty, ok_quantity=qty, correction_quantity=0)

        day = month_days[index % len(month_days)]
        base_dt = datetime(today.year, today.month, day, 9, 0, tzinfo=UTC)
        _backdate(
            session,
            order.id,
            {
                (ProcessStage.SURFACE_PREPARATION, StageStatus.IN_PROGRESS): base_dt,
                (ProcessStage.SURFACE_PREPARATION, StageStatus.DONE): base_dt + 10 * MIN,
                (ProcessStage.PRODUCTION, StageStatus.IN_PROGRESS): base_dt + 40 * MIN,  # 30 min queue wait
                (ProcessStage.PRODUCTION, StageStatus.DONE): base_dt + (40 + prod_min) * MIN,
                (ProcessStage.PACKING, StageStatus.IN_PROGRESS): base_dt + (40 + prod_min + 25) * MIN,  # 25 min wait
                (ProcessStage.PACKING, StageStatus.DONE): base_dt + (40 + prod_min + 25 + 15) * MIN,
            },
        )

    # Note: an automatic completed order is intentionally omitted — the base seed (scenario E2) already
    # holds the single HANGING resource lock, so a fresh automatic order cannot start hanging. The
    # base seed's automatic orders still contribute automatic m² to the throughput chart.
    return queue_position


def _set_stage_event_age(session: Session, work_order_id: int, stage: ProcessStage, started_at: datetime) -> None:
    # Backdate the latest IN_PROGRESS event for the order's current stage so WIP-aging shows a real age.
    event = session.scalars(
        select(StageTransitionEvent)
        .where(
            StageTransitionEvent.work_order_id == work_order_id,
            StageTransitionEvent.stage == stage,
            StageTransitionEvent.status == StageStatus.IN_PROGRESS,
        )
        .order_by(StageTransitionEvent.occurred_at.desc())
    ).first()
    if event is not None:
        event.occurred_at = started_at
        session.flush()


def _seed_work_in_progress(
    work_order_service, process_service, manager_service, session, now_ref, queue_position
) -> int:
    # 1) Surface preparation, ~2h.
    s1 = _create(work_order_service, title="DEMO W toku — przygotowanie", coating=CoatingType.RAL, qty=10, ral="RAL 3003", customer="Okno-System")
    base.assign_plan(manager_service, s1.id, ProductionType.MANUAL, queue_position)
    queue_position += 10
    base.start_surface_preparation(process_service, s1.id, counted_quantity=10)
    _set_stage_event_age(session, s1.id, ProcessStage.SURFACE_PREPARATION, now_ref - timedelta(hours=2))

    # 2) Manual production, ~30h → over 24h, highlighted red.
    s2 = _create(work_order_service, title="DEMO W toku — produkcja (>24h)", coating=CoatingType.RAL, qty=14, ral="RAL 5005", customer="Alumar")
    base.assign_plan(manager_service, s2.id, ProductionType.MANUAL, queue_position)
    queue_position += 10
    base.start_surface_preparation(process_service, s2.id, counted_quantity=14)
    base.finish_surface_preparation(process_service, s2.id)
    process_service.start_stage(s2.id, ProcessStage.PRODUCTION)
    _set_stage_event_age(session, s2.id, ProcessStage.PRODUCTION, now_ref - timedelta(hours=30))

    # An automatic-at-hanging row already exists from the base seed (scenario E2). Backdate its
    # HANGING start so it shows a realistic age in the WIP-aging table instead of ~0.
    e2 = session.scalars(
        select(WorkOrder).where(WorkOrder.title == "RAL automat - zawieszanie i pakowanie")
    ).first()
    if e2 is not None:
        _set_stage_event_age(session, e2.id, ProcessStage.HANGING, now_ref - timedelta(hours=5))
    return queue_position


def _seed_packing_exclusivity(work_order_service, process_service, manager_service, queue_position) -> int:
    for letter, customer, ral in (("A", "Profiltech Sp. z o.o.", "RAL 8017"), ("B", "Konstruktor Sp. z o.o.", "RAL 9010")):
        order = _create(work_order_service, title=f"DEMO Pakowanie {letter}", coating=CoatingType.RAL, qty=10, ral=ral, customer=customer)
        base.assign_plan(manager_service, order.id, ProductionType.MANUAL, queue_position)
        queue_position += 10
        # Leaves PACKING IN_PROGRESS but unclaimed (no PACKING resource lock) — ready to "Rozpocznij".
        base.advance_to_packing(process_service, order.id, counted_quantity=10)
    return queue_position


if __name__ == "__main__":
    raise SystemExit(main())
