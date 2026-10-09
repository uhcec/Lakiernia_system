"""Seed a realistic factory snapshot: ~30 clients and ~200 work orders spread across every stage of
the pipeline (intake, active production on both lines, waiting-for-corrections, ready-unreleased,
ready-released) instead of a single uniform bucket. Meant for exercising office-facing screens (client
list, WZ generation, manager board, stats) against something that looks like a real day at the shop.

Directly inserts stage states / production_type / queue_position, bypassing resource-lock checks —
same established pattern as scripts/seed_throughput_test.py. Idempotent-ish: re-running adds a fresh
batch on top (order numbers are always unique); it does not delete anything.

Run with: python scripts/seed_realistic_dataset.py
"""
from __future__ import annotations

import random
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.clients.models import Client
from app.core.config import get_settings
from app.database import models as _models  # noqa: F401
from app.database.session import get_session_factory
from app.process.enums import CoatingType, ProcessStage, ProductionType, StageStatus
from app.process.models import WorkOrderStageState
from app.process.service import ProcessService
from app.process.repository import ProcessRepository
from app.work_orders.models import WorkOrder
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import WorkOrderCreate
from app.work_orders.service import WorkOrderService

TODAY = date.today()
RNG = random.Random(2026)

_PAINT_BY_RAL: dict[str, tuple[str, str]] = {
    "RAL 7016": ("TIG-7016-MA", "Tiger"),
    "RAL 9005": ("AKZ-9005-MA", "AkzoNobel"),
    "RAL 7035": ("AKZ-7035-GL", "AkzoNobel"),
    "RAL 3020": ("SHW-3020-GL", "Sherwin-Williams"),
    "RAL 5010": ("TIG-5010-MA", "Tiger"),
    "RAL 9010": ("AKZ-9010-GL", "AkzoNobel"),
    "RAL 7040": ("TIG-7040-MA", "Tiger"),
    "RAL 8017": ("TIG-8017-MA", "Tiger"),
    "RAL 6005": ("AKZ-6005-MA", "AkzoNobel"),
    "RAL 1015": ("SHW-1015-GL", "Sherwin-Williams"),
    "D-200": ("DCR-200", "Decoral System"),
    "D-310": ("DCR-310", "Decoral System"),
}
_RAL_KEYS = [k for k in _PAINT_BY_RAL if not k.startswith("D-")]
_DECORAL_KEYS = [k for k in _PAINT_BY_RAL if k.startswith("D-")]
_REASONS = ["niedomalowanie", "za grubo", "wtrącenia", "porysowane", "inne"]

# 30 clients. A few (front of the list) are repeat/regular customers and get more orders via the
# Zipf-ish weighting below; the tail are one-off/occasional customers.
_CLIENTS = [
    "Profiltech Sp. z o.o.", "Stalmet Nowak", "Aluminco", "Fasada Polska", "Okno-System",
    "Balkon-Tech Sp. z o.o.", "Technoalum", "Metal-Bud Zając", "Konstruktor Sp. z o.o.",
    "Alu-Systemy Kowalski", "AluFasada Kraków", "Elmet Wrocław", "BudMet Sp. z o.o.",
    "Alubram Systemy", "Fenster-Pol", "Metaloplastyka Wiśniewski", "Grodmet",
    "Alumino Group", "Balustrady Wojciechowski", "PPHU Kowal-Stal",
    "Fasady Aluminiowe Zieliński", "AluTech Poznań", "StalGlass Sp. z o.o.",
    "Bramy i Ogrodzenia Lis", "Metalplast Śląsk", "Elewacje Nowoczesne Sp. z o.o.",
    "AluKonstrukcje Gdańsk", "Ślusarstwo Artystyczne Duda", "Systemy Przeszkleń Wójcik",
    "Profil-Bud Sp. z o.o.",
]


def seed_clients(session: Session) -> None:
    existing = {row[0] for row in session.execute(select(Client.company_name)).all()}
    created = 0
    for idx, name in enumerate(_CLIENTS):
        if name in existing:
            continue
        has_phone = RNG.random() < 0.7
        has_nip = RNG.random() < 0.6
        session.add(Client(
            company_name=name,
            contact_phone=f"6{RNG.randint(10000000, 99999999)}" if has_phone else None,
            nip=f"{RNG.randint(1000000000, 9999999999)}" if has_nip else None,
        ))
        created += 1
    session.commit()
    print(f"Clients: {created} created, {len(existing)} already present ({len(_CLIENTS)} total).")


def _weighted_customer() -> str:
    # Zipf-ish: customer[0] is ~10x more likely than customer[29].
    weights = [1.0 / (i + 1) for i in range(len(_CLIENTS))]
    return RNG.choices(_CLIENTS, weights=weights, k=1)[0]


def _split_quantities(qty: int) -> tuple[int, int]:
    accessories = max(0, min(qty, round(qty * RNG.uniform(0.15, 0.45))))
    return qty - accessories, accessories


def _new_order_def(bucket: str, idx: int) -> dict:
    customer = _weighted_customer()
    is_decoral = RNG.random() < 0.12
    ral = RNG.choice(_DECORAL_KEYS) if is_decoral else RNG.choice(_RAL_KEYS)
    paint_code, paint_producer = _PAINT_BY_RAL[ral]
    production_type = RNG.choice([ProductionType.AUTOMATIC] * 7 + [ProductionType.MANUAL] * 3)
    qty = RNG.randint(4, 260)
    area = round(qty * RNG.uniform(0.35, 0.55), 1)
    has_external = RNG.random() < 0.55
    profiles, accessories = _split_quantities(qty)

    return dict(
        bucket=bucket,
        title=f"{customer} — {ral} #{idx}",
        customer=customer,
        ral=ral,
        coating=CoatingType.DECORAL if is_decoral else CoatingType.RAL,
        paint_code=paint_code,
        paint_producer=paint_producer,
        production_type=production_type,
        qty=qty,
        area=area,
        profiles=profiles,
        accessories=accessories,
        external_order_number=f"ZK-{RNG.randint(1000, 9999)}" if has_external else None,
    )


def _upsert_stage_state(
    session: Session, work_order_id: int, stage: ProcessStage, status: StageStatus,
    updated_at: datetime, counted_quantity: int | None = None,
) -> None:
    existing = session.scalar(
        select(WorkOrderStageState).where(
            WorkOrderStageState.work_order_id == work_order_id,
            WorkOrderStageState.stage == stage,
        )
    )
    if existing is None:
        session.add(WorkOrderStageState(
            work_order_id=work_order_id, stage=stage, status=status,
            counted_quantity=counted_quantity, created_at=updated_at, updated_at=updated_at,
        ))
    else:
        existing.status = status
        existing.updated_at = updated_at
        if counted_quantity is not None:
            existing.counted_quantity = counted_quantity


def _days_ago(n: int, hour: int = 8) -> datetime:
    d = TODAY - timedelta(days=n)
    return datetime(d.year, d.month, d.day, hour, 0, 0, tzinfo=UTC)


def seed_order(
    session: Session, service: WorkOrderService, repository: WorkOrderRepository,
    process_service: ProcessService, order_def: dict, queue_position_holder: list[int],
) -> str:
    bucket = order_def["bucket"]
    qty = order_def["qty"]
    is_decoral = order_def["coating"] == CoatingType.DECORAL
    is_incomplete = bucket == "INTAKE_INCOMPLETE"

    days_since_intake = {
        "INTAKE_UNPLANNED": RNG.randint(0, 4),
        "INTAKE_INCOMPLETE": RNG.randint(0, 3),
        "ACTIVE_SURFACE_PREP": RNG.randint(1, 6),
        "ACTIVE_HANGING": RNG.randint(2, 7),
        "ACTIVE_PRODUCTION_MANUAL": RNG.randint(2, 7),
        "ACTIVE_DECORAL": RNG.randint(3, 9),
        "ACTIVE_PACKING": RNG.randint(3, 10),
        "WAITING_FOR_CORRECTIONS": RNG.randint(10, 25),
        "READY_UNRELEASED": RNG.randint(3, 15),
        "READY_RELEASED": RNG.randint(15, 75),
    }[bucket]
    received = TODAY - timedelta(days=days_since_intake)
    # A slice of active/intake orders are already overdue (planned pickup slipped) — realistic, not a bug.
    pickup_offset = RNG.randint(-6, 3) if bucket not in ("READY_UNRELEASED", "READY_RELEASED") else -RNG.randint(0, 3)
    planned_pickup = received + timedelta(days=max(1, 7 + pickup_offset))

    payload = dict(
        title=order_def["title"],
        external_order_number=order_def["external_order_number"],
        customer_name=order_def["customer"],
        ral_code=order_def["ral"],
        paint_code=order_def["paint_code"],
        paint_producer=order_def["paint_producer"],
        coating_type=order_def["coating"],
        total_quantity=qty,
        received_date=received,
        planned_pickup_date=planned_pickup,
        total_area_m2=order_def["area"],
    )
    if is_incomplete:
        payload.update(is_incomplete_on_arrival=True, profiles_to_count=True, accessories_to_count=True)
    else:
        payload.update(
            profiles_quantity=order_def["profiles"], profiles_to_count=False,
            accessories_quantity=order_def["accessories"], accessories_to_count=False,
        )

    wo = service.create_work_order(WorkOrderCreate(**payload))
    wo_model = session.get(WorkOrder, wo.id)
    assert wo_model is not None

    if bucket in ("INTAKE_UNPLANNED", "INTAKE_INCOMPLETE"):
        session.commit()
        return wo.order_number

    # Plan: assign line + queue position directly (bypasses queue-shift logic, matching
    # seed_throughput_test.py's established pattern). A single strictly-increasing counter shared
    # across both lines trivially satisfies the per-(production_type, queue_position) uniqueness.
    # A finished order (READY, whether released or not) has already left the active queue and
    # released its position per CHANGES #3 (app/process/service.py:_release_queue_slot) — keeping
    # its line but not a queue_position — so only the still-open buckets (active production and the
    # not-yet-finalized WAITING_FOR_CORRECTIONS parent) get one.
    production_type = order_def["production_type"]
    wo_model.production_type = production_type
    if bucket not in ("READY_UNRELEASED", "READY_RELEASED"):
        queue_position_holder[0] += 10
        wo_model.queue_position = queue_position_holder[0]
    session.flush()

    is_auto = production_type == ProductionType.AUTOMATIC
    ts_intake = _days_ago(days_since_intake)

    if bucket == "ACTIVE_SURFACE_PREP":
        status = RNG.choice([StageStatus.NOT_STARTED, StageStatus.IN_PROGRESS])
        _upsert_stage_state(session, wo.id, ProcessStage.SURFACE_PREPARATION, status, ts_intake)
        queue_position_holder[0] -= 10 if not is_auto else 0  # no-op, keep counter monotonic either way

    elif bucket == "ACTIVE_HANGING":
        # AUTOMATIC-only bucket (HANGING is not on the MANUAL route).
        wo_model.production_type = ProductionType.AUTOMATIC
        _upsert_stage_state(session, wo.id, ProcessStage.SURFACE_PREPARATION, StageStatus.DONE, ts_intake)
        _upsert_stage_state(session, wo.id, ProcessStage.HANGING,
                             RNG.choice([StageStatus.NOT_STARTED, StageStatus.IN_PROGRESS]),
                             ts_intake + timedelta(hours=2))

    elif bucket == "ACTIVE_PRODUCTION_MANUAL":
        wo_model.production_type = ProductionType.MANUAL
        _upsert_stage_state(session, wo.id, ProcessStage.SURFACE_PREPARATION, StageStatus.DONE, ts_intake)
        _upsert_stage_state(session, wo.id, ProcessStage.PRODUCTION, StageStatus.IN_PROGRESS,
                             ts_intake + timedelta(hours=2))

    elif bucket == "ACTIVE_DECORAL":
        _upsert_stage_state(session, wo.id, ProcessStage.SURFACE_PREPARATION, StageStatus.DONE, ts_intake)
        if is_auto:
            _upsert_stage_state(session, wo.id, ProcessStage.HANGING, StageStatus.DONE, ts_intake + timedelta(hours=1))
        else:
            _upsert_stage_state(session, wo.id, ProcessStage.PRODUCTION, StageStatus.DONE, ts_intake + timedelta(hours=1))
        _upsert_stage_state(session, wo.id, ProcessStage.PACKING, StageStatus.DONE, ts_intake + timedelta(hours=2), qty)
        _upsert_stage_state(session, wo.id, ProcessStage.DECORAL_PRODUCTION,
                             RNG.choice([StageStatus.NOT_STARTED, StageStatus.IN_PROGRESS]),
                             ts_intake + timedelta(hours=3))
        wo_model.completed_quantity = 0
        wo_model.current_active_quantity = qty

    elif bucket == "ACTIVE_PACKING":
        _upsert_stage_state(session, wo.id, ProcessStage.SURFACE_PREPARATION, StageStatus.DONE, ts_intake)
        if is_auto:
            _upsert_stage_state(session, wo.id, ProcessStage.HANGING, StageStatus.DONE, ts_intake + timedelta(hours=1))
            wo_model.consumed_paint_quantity_kg = max(0.5, round(order_def["area"] / 6, 1))
        else:
            _upsert_stage_state(session, wo.id, ProcessStage.PRODUCTION, StageStatus.DONE, ts_intake + timedelta(hours=1))
        _upsert_stage_state(session, wo.id, ProcessStage.PACKING,
                             RNG.choice([StageStatus.NOT_STARTED, StageStatus.IN_PROGRESS]),
                             ts_intake + timedelta(hours=2))
        wo_model.current_active_quantity = qty

    elif bucket in ("WAITING_FOR_CORRECTIONS", "READY_UNRELEASED", "READY_RELEASED"):
        packing_done_at = ts_intake + timedelta(hours=4)
        _upsert_stage_state(session, wo.id, ProcessStage.SURFACE_PREPARATION, StageStatus.DONE, ts_intake)
        if is_auto:
            _upsert_stage_state(session, wo.id, ProcessStage.HANGING, StageStatus.DONE, ts_intake + timedelta(hours=1))
            wo_model.consumed_paint_quantity_kg = max(0.5, round(order_def["area"] / 6, 1))
        else:
            _upsert_stage_state(session, wo.id, ProcessStage.PRODUCTION, StageStatus.DONE, ts_intake + timedelta(hours=1))
        _upsert_stage_state(session, wo.id, ProcessStage.PACKING, StageStatus.DONE, packing_done_at, qty)
        if is_decoral:
            _upsert_stage_state(session, wo.id, ProcessStage.DECORAL_PRODUCTION, StageStatus.DONE,
                                 packing_done_at + timedelta(hours=2), qty)

        if bucket == "WAITING_FOR_CORRECTIONS":
            correction_qty = max(1, min(qty - 1, round(qty * RNG.uniform(0.05, 0.2))))
            child = service.create_work_order(WorkOrderCreate(
                title=f"[Poprawka] {order_def['title'][:45]}",
                customer_name=order_def["customer"],
                ral_code=order_def["ral"],
                paint_code=order_def["paint_code"],
                paint_producer=order_def["paint_producer"],
                coating_type=order_def["coating"],
                total_quantity=correction_qty,
                profiles_quantity=correction_qty,
                accessories_quantity=0,
                total_area_m2=round(order_def["area"] * correction_qty / qty, 1),
                received_date=received,
                planned_pickup_date=planned_pickup,
                description=f"Poprawka: {RNG.choice(_REASONS)}",
            ))
            child_wo = session.get(WorkOrder, child.id)
            assert child_wo is not None
            child_wo.is_correction = True
            child_wo.parent_order_id = wo.id
            child_wo.correction_reason_category = RNG.choice(_REASONS)
            child_wo.queue_namespace = "CORRECTIONS"
            child_wo.created_at = packing_done_at + timedelta(days=RNG.randint(1, 5))
            wo_model.completed_quantity = qty - correction_qty
            wo_model.current_active_quantity = correction_qty
        else:
            wo_model.completed_quantity = qty
            wo_model.current_active_quantity = 0
            if bucket == "READY_RELEASED":
                wo_model.released_to_client_at = packing_done_at + timedelta(hours=RNG.randint(2, 48))

    session.commit()
    return wo.order_number


def build_order_defs() -> list[dict]:
    counts = {
        "INTAKE_UNPLANNED": 18,
        "INTAKE_INCOMPLETE": 8,
        "ACTIVE_SURFACE_PREP": 12,
        "ACTIVE_HANGING": 10,
        "ACTIVE_PRODUCTION_MANUAL": 8,
        "ACTIVE_DECORAL": 6,
        "ACTIVE_PACKING": 10,
        "WAITING_FOR_CORRECTIONS": 8,
        "READY_UNRELEASED": 40,
        "READY_RELEASED": 80,
    }
    defs: list[dict] = []
    idx = 1
    for bucket, count in counts.items():
        for _ in range(count):
            defs.append(_new_order_def(bucket, idx))
            idx += 1
    RNG.shuffle(defs)
    return defs


def ensure_paint_stock(session: Session) -> None:
    from app.paints.repository import PaintRepository
    from app.paints.schemas import PaintDeliveryCreate
    from app.paints.service import PaintService

    paint_service = PaintService(PaintRepository(session))
    for ral, (paint_code, producer) in _PAINT_BY_RAL.items():
        current = paint_service.lookup_current_stock(
            ral_code=ral, paint_producer=producer, paint_code=paint_code
        ).current_quantity_kg
        target = 400.0
        if current < target:
            paint_service.record_delivery(PaintDeliveryCreate(
                ral_code=ral, paint_producer=producer, paint_code=paint_code,
                quantity_kg=round(target - current, 1), movement_date=TODAY - timedelta(days=30),
            ))
    session.commit()
    print(f"Paint stock ensured for {len(_PAINT_BY_RAL)} colors (>= 400 kg each).")


def get_next_queue_position(session: Session) -> int:
    result = session.execute(text("SELECT COALESCE(MAX(queue_position), 990) FROM work_orders")).scalar()
    return (result or 990) + 10


def main() -> int:
    settings = get_settings()
    if settings.app_env.lower() != "development":
        raise SystemExit("Refusing to run: APP_ENV must be development.")

    session = get_session_factory()()
    try:
        seed_clients(session)
        ensure_paint_stock(session)

        repository = WorkOrderRepository(session)
        service = WorkOrderService(repository)
        process_service = ProcessService(ProcessRepository(session))

        order_defs = build_order_defs()
        queue_position_holder = [get_next_queue_position(session)]
        print(f"Creating {len(order_defs)} orders across {len(_CLIENTS)} clients...\n")

        bucket_counts: dict[str, int] = {}
        for order_def in order_defs:
            number = seed_order(session, service, repository, process_service, order_def, queue_position_holder)
            bucket_counts[order_def["bucket"]] = bucket_counts.get(order_def["bucket"], 0) + 1
            print(f"  {number}  [{order_def['bucket']:<24}] {order_def['customer']}")

        print("\nDone. Bucket summary:")
        for bucket, count in bucket_counts.items():
            print(f"  {bucket:<24} {count}")
        print(f"\nTotal orders created this run: {len(order_defs)}")
    finally:
        session.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
