"""Seed completed work orders for testing the /statystyki throughput page.

Generates READY orders across the days of the CURRENT month (1st .. today) with
realistic per-line areas: AUTOMATIC production runs large daily totals (hundreds
of m², up to ~1100), MANUAL production runs small ones (a few up to ~65 m²/day).
This matches the chart axes (automat → 1200 m², ręczna → 70 m²).
Directly inserts stage states to bypass resource lock checks.
Run with: python scripts/seed_throughput_test.py
"""
from __future__ import annotations

import random
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database import models as _models  # noqa: F401
from app.database.session import get_session_factory
from app.process.enums import CoatingType, ProcessStage, ProductionType, StageStatus
from app.process.models import WorkOrderStageState
from app.process.repository import ProcessRepository
from app.work_orders.models import WorkOrder
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import WorkOrderCreate
from app.work_orders.service import WorkOrderService


_PAINT_BY_RAL: dict[str, tuple[str, str]] = {
    "RAL 7016": ("TIG-7016-MA", "Tiger"),
    "RAL 9005": ("AKZ-9005-MA", "AkzoNobel"),
    "RAL 7035": ("AKZ-7035-GL", "AkzoNobel"),
    "RAL 3020": ("SHW-3020-GL", "Sherwin-Williams"),
    "RAL 5010": ("TIG-5010-MA", "Tiger"),
    "D-200":    ("DCR-200",     "Decoral System"),
    "D-310":    ("DCR-310",     "Decoral System"),
    "RAL 9010": ("AKZ-9010-GL", "AkzoNobel"),
    "RAL 7040": ("TIG-7040-MA", "Tiger"),
}

TODAY = date.today()

_CUSTOMERS = [
    "Profiltech Sp. z o.o.", "Stalmet", "Aluminco", "Fasada Polska", "Okno-System",
    "Balkon-Tech Sp. z o.o.", "Technoalum", "Metal-Bud Zając", "Konstruktor Sp. z o.o.",
]
_RAL_KEYS = ["RAL 7016", "RAL 9005", "RAL 7035", "RAL 3020", "RAL 5010", "RAL 9010", "RAL 7040"]
_DECORAL_KEYS = ["D-200", "D-310"]
_REASONS = ["niedomalowanie", "za grubo", "wtrącenia", "inne"]


def _day_dt(day: int, order_idx: int) -> datetime:
    base = date(TODAY.year, TODAY.month, day)
    return datetime(base.year, base.month, base.day, 8, 0, 0, tzinfo=UTC) + timedelta(minutes=order_idx * 9)


def build_orders() -> list[dict]:
    """Generate orders for each day of the current month up to today.

    AUTOMATIC lines carry the bulk of the area (daily total up to ~1100 m²); MANUAL
    lines stay small (daily total up to ~65 m²). Some lines are Decoral (their base
    coat still counts toward automat/ręczna), and a few orders spin off a correction.
    """
    rng = random.Random(42)
    orders: list[dict] = []

    for day in range(1, TODAY.day + 1):
        order_idx = 0

        # AUTOMATIC — large daily total split across a few lines (cap < 1180).
        auto_remaining = rng.choice([320, 480, 650, 820, 980, 1120])
        for _ in range(rng.randint(2, 4)):
            if auto_remaining < 120:
                break
            m2_int = rng.randint(120, min(420, auto_remaining))
            auto_remaining -= m2_int
            m2 = float(m2_int)
            is_decoral = rng.random() < 0.20
            ral = rng.choice(_DECORAL_KEYS) if is_decoral else rng.choice(_RAL_KEYS)
            customer = rng.choice(_CUSTOMERS)
            qty = max(6, round(m2 / 6))
            order = dict(
                title=f"{customer} - {ral} (automat)", customer=customer, ral=ral,
                coating=CoatingType.DECORAL if is_decoral else CoatingType.RAL,
                production=ProductionType.AUTOMATIC, qty=qty, m2=m2,
                packing_done_at=_day_dt(day, order_idx),
            )
            if rng.random() < 0.10:
                cq = rng.randint(1, min(5, qty - 1))
                order["correction"] = dict(qty=cq, profiles=cq, accessories=0, reason=rng.choice(_REASONS))
            orders.append(order)
            order_idx += 1

        # MANUAL — small daily total split across a line or two (cap < 68).
        man_remaining = rng.choice([18, 30, 45, 62])
        for _ in range(rng.randint(1, 3)):
            if man_remaining < 8:
                break
            m2_int = rng.randint(8, min(28, man_remaining))
            man_remaining -= m2_int
            m2 = float(m2_int)
            is_decoral = rng.random() < 0.15
            ral = rng.choice(_DECORAL_KEYS) if is_decoral else rng.choice(_RAL_KEYS)
            customer = rng.choice(_CUSTOMERS)
            qty = max(3, round(m2 / 3))
            order = dict(
                title=f"{customer} - {ral} (ręczna)", customer=customer, ral=ral,
                coating=CoatingType.DECORAL if is_decoral else CoatingType.RAL,
                production=ProductionType.MANUAL, qty=qty, m2=m2,
                packing_done_at=_day_dt(day, order_idx),
            )
            if rng.random() < 0.12 and qty > 1:
                cq = rng.randint(1, min(4, qty - 1))
                order["correction"] = dict(qty=cq, profiles=cq, accessories=0, reason=rng.choice(_REASONS))
            orders.append(order)
            order_idx += 1

    return orders


_ORDERS: list[dict] = build_orders()


def get_next_queue_position(session: Session) -> int:
    result = session.execute(text("SELECT COALESCE(MAX(queue_position), 990) FROM work_orders")).scalar()
    return (result or 990) + 10


def _upsert_stage_state(
    session: Session,
    work_order_id: int,
    stage: ProcessStage,
    status: StageStatus,
    updated_at: datetime,
    counted_quantity: int | None = None,
) -> None:
    existing = session.scalar(
        select(WorkOrderStageState).where(
            WorkOrderStageState.work_order_id == work_order_id,
            WorkOrderStageState.stage == stage,
        )
    )
    if existing is None:
        session.add(WorkOrderStageState(
            work_order_id=work_order_id,
            stage=stage,
            status=status,
            counted_quantity=counted_quantity,
            created_at=updated_at,
            updated_at=updated_at,
        ))
    else:
        existing.status = status
        existing.updated_at = updated_at
        if counted_quantity is not None:
            existing.counted_quantity = counted_quantity


def _mark_order_ready(session: Session, wo: WorkOrder, packing_done_at: datetime) -> None:
    """Set completed_quantity = total_quantity and clear active quantity."""
    wo.completed_quantity = wo.total_quantity
    wo.current_active_quantity = 0
    session.flush()


def seed_order(
    session: Session,
    work_order_service: WorkOrderService,
    work_order_repository: WorkOrderRepository,
    order_def: dict,
    queue_position: int,
) -> None:
    paint_code, paint_producer = _PAINT_BY_RAL[order_def["ral"]]
    qty: int = order_def["qty"]
    m2: float = order_def["m2"]
    coating: CoatingType = order_def["coating"]
    production: ProductionType = order_def["production"]
    packing_done_at: datetime = order_def["packing_done_at"]
    is_auto = production == ProductionType.AUTOMATIC

    wo = work_order_service.create_work_order(WorkOrderCreate(
        title=order_def["title"],
        customer_name=order_def["customer"],
        ral_code=order_def["ral"],
        paint_code=paint_code,
        paint_producer=paint_producer,
        coating_type=coating,
        total_quantity=qty,
        profiles_quantity=qty - max(1, qty // 6),
        accessories_quantity=max(1, qty // 6),
        total_area_m2=m2,
        received_date=TODAY - timedelta(days=35),
        planned_pickup_date=TODAY - timedelta(days=2),
        description=order_def["title"],
    ))

    # Assign plan directly — bypasses queue-shift logic that conflicts with existing data
    wo_model = session.get(WorkOrder, wo.id)
    if wo_model is not None:
        wo_model.production_type = production
        wo_model.queue_position = queue_position
        session.flush()

    ts_early = packing_done_at - timedelta(hours=5)

    # Surface preparation
    _upsert_stage_state(session, wo.id, ProcessStage.SURFACE_PREPARATION, StageStatus.DONE, ts_early, qty)

    # Production path stages
    if is_auto:
        _upsert_stage_state(session, wo.id, ProcessStage.HANGING, StageStatus.DONE, ts_early + timedelta(hours=1))
        _upsert_stage_state(session, wo.id, ProcessStage.PRODUCTION, StageStatus.IN_PROGRESS, ts_early + timedelta(hours=1))
        wo.consumed_paint_quantity_kg = max(0.5, round(m2 / 6, 1))
    else:
        _upsert_stage_state(session, wo.id, ProcessStage.PRODUCTION, StageStatus.DONE, ts_early + timedelta(hours=1))

    correction = order_def.get("correction")

    # Packing stage — DONE at the desired date
    _upsert_stage_state(session, wo.id, ProcessStage.PACKING, StageStatus.DONE, packing_done_at, qty)

    if correction:
        # Create unplanned correction child — throughput counts its total_quantity as correction_pieces
        child_paint_code, child_paint_producer = _PAINT_BY_RAL[order_def["ral"]]
        child = work_order_service.create_work_order(WorkOrderCreate(
            title=f"[Poprawka] {order_def['title'][:45]}",
            customer_name=order_def["customer"],
            ral_code=order_def["ral"],
            paint_code=child_paint_code,
            paint_producer=child_paint_producer,
            coating_type=coating,
            total_quantity=correction["qty"],
            profiles_quantity=correction["profiles"],
            accessories_quantity=correction["accessories"],
            total_area_m2=round(m2 * correction["qty"] / qty, 1),
            received_date=TODAY - timedelta(days=35),
            planned_pickup_date=TODAY - timedelta(days=2),
            description=f"Poprawka: {correction['reason']}",
        ))
        child_wo = session.get(WorkOrder, child.id)
        if child_wo is not None:
            child_wo.is_correction = True
            child_wo.parent_order_id = wo.id
            child_wo.correction_reason_category = correction["reason"]
            child_wo.queue_namespace = "CORRECTIONS"
            # Backdate created_at so correction appears in the same period as packing
            child_wo.created_at = packing_done_at
        wo.completed_quantity = qty - correction["qty"]
        wo.current_active_quantity = correction["qty"]
    else:
        wo.completed_quantity = qty
        wo.current_active_quantity = 0

    # Decoral stage for decoral orders
    if coating == CoatingType.DECORAL:
        decoral_ts = packing_done_at + timedelta(hours=3)
        _upsert_stage_state(session, wo.id, ProcessStage.DECORAL_PRODUCTION, StageStatus.DONE, decoral_ts, qty)

    session.commit()
    print(f"  OK  {wo.order_number}  {order_def['title'][:50]:<50}  [{production.value}, {m2} m2]")


def main() -> int:
    settings = get_settings()
    if settings.app_env.lower() != "development":
        raise SystemExit("Refusing to run: APP_ENV must be development.")

    session = get_session_factory()()
    try:
        work_order_repository = WorkOrderRepository(session)
        work_order_service = WorkOrderService(work_order_repository)

        queue_position = get_next_queue_position(session)
        print(f"Starting from queue position {queue_position}")
        print(f"Creating {len(_ORDERS)} completed orders...\n")

        for order_def in _ORDERS:
            seed_order(
                session,
                work_order_service,
                work_order_repository,
                order_def,
                queue_position,
            )
            queue_position += 20

        print(f"\nDone. {len(_ORDERS)} orders seeded across {TODAY.strftime('%B %Y')} (days 1..{TODAY.day}).")
        print("Open /statystyki — the current month loads automatically.")
    finally:
        session.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
