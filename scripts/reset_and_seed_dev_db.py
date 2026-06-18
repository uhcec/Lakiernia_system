from __future__ import annotations

import sys
from pathlib import Path

# Ensure THIS repo resolves `app` even when run as `python scripts/reset_and_seed_dev_db.py` (where the
# script dir, not the repo root, is on sys.path). Otherwise an editable install in a system Python could
# shadow `app` with a copy at another path. Must run before importing `app`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import shutil

from alembic import command
from alembic.config import Config
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.audit.models import AuditEvent, AuditEventActor
from app.auth.models import User
from app.auth.service import hash_password
from app.clients.models import Client
from app.core.config import get_settings, get_work_order_attachments_path
from app.employees.models import Employee, StationPresence
from app.database import models as _models  # noqa: F401
from app.database.session import get_session_factory
from app.manager.repository import ManagerRepository
from app.manager.schemas import WorkOrderPlanAssignRequest
from app.manager.service import ManagerService
from app.process.enums import CoatingType, ProcessStage, ProductionType, QuantityBatchType, StageStatus
from app.process.models import (
    ProcessResourceLock,
    StageTransitionEvent,
    WorkOrderQuantityBatch,
    WorkOrderStageState,
)
from app.process.repository import ProcessRepository
from app.process.service import ProcessService
from app.shared.enums import StationId, WorkOrderKind, WorkOrderStatus
from app.work_orders.models import WorkOrder, WorkOrderAttachment, WorkOrderNumberCounter
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import WorkOrderCreate
from app.work_orders.service import WorkOrderService


PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<<>>\n%%EOF\n"

_PAINT_BY_RAL: dict[str, tuple[str, str]] = {
    "RAL 7016": ("TIG-7016-MA", "Tiger"),
    "RAL 9005": ("AKZ-9005-MA", "AkzoNobel"),
    "RAL 7035": ("AKZ-7035-GL", "AkzoNobel"),
    "RAL 3020": ("SHW-3020-GL", "Sherwin-Williams"),
    "RAL 5010": ("TIG-5010-MA", "Tiger"),
    "D-200":    ("DCR-200",     "Decoral System"),
    "D-310":    ("DCR-310",     "Decoral System"),
    "RAL 8017": ("AKZ-8017-MA", "AkzoNobel"),
    "RAL 9010": ("AKZ-9010-GL", "AkzoNobel"),
    "RAL 7040": ("TIG-7040-MA", "Tiger"),
    "RAL 5005": ("SHW-5005-MA", "Sherwin-Williams"),
    "RAL 6021": ("IGP-6021-GL", "IGP"),
    "RAL 3003": ("TIG-3003-MA", "Tiger"),
    "RAL 7010": ("AKZ-7010-MA", "AkzoNobel"),
    "RAL 7020": ("TIG-7020-GL", "Tiger"),
    "RAL 7030": ("SHW-7030-MA", "Sherwin-Williams"),
    "RAL 1013": ("AKZ-1013-GL", "AkzoNobel"),
    "RAL 6029": ("TIG-6029-MA", "Tiger"),
    "RAL 6018": ("IGP-6018-GL", "IGP"),
    "RAL 7031": ("AKZ-7031-MA", "AkzoNobel"),
    "RAL 7032": ("AKZ-7032-GL", "AkzoNobel"),
    "RAL 7033": ("TIG-7033-MA", "Tiger"),
    "RAL 9018": ("SHW-9018-GL", "Sherwin-Williams"),
}


@dataclass(slots=True)
class SeededScenario:
    code: str
    order_number: str
    purpose: str
    page: str
    details: str


def main() -> int:
    # The seed report contains Polish characters; avoid a UnicodeEncodeError on legacy Windows consoles.
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
        reset_app_data(session)
        scenarios = seed_all_use_cases(session)
    finally:
        session.close()

    print_seed_report(scenarios)
    return 0


def ensure_local_dev_sqlite(repo_root: Path) -> Path:
    settings = get_settings()
    if settings.app_env.lower() != "development":
        raise SystemExit("Refusing to run: APP_ENV must be development.")

    url = make_url(settings.database_url)
    if not url.drivername.startswith("sqlite"):
        raise SystemExit("Refusing to run: DATABASE_URL must point to local SQLite.")

    database_name = url.database
    if not database_name or database_name == ":memory:":
        raise SystemExit("Refusing to run: DATABASE_URL must point to a file-backed local SQLite database.")

    database_path = Path(database_name)
    if not database_path.is_absolute():
        database_path = (repo_root / database_path).resolve()

    if database_path.name != "local.db":
        raise SystemExit("Refusing to run: script is restricted to the local development local.db file.")

    return database_path


def run_alembic_upgrade(repo_root: Path) -> None:
    alembic_config = Config(str(repo_root / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(repo_root / "alembic"))
    command.upgrade(alembic_config, "head")


_STATION_USERS = [
    ("biuro", "bi1", "OFFICE", False),
    ("kierownik", "ki1", "MANAGER", False),
    ("przygotowanie", "prz1", "SURFACE_PREPARATION", False),
    ("zawieszanie", "zaw1", "HANGING", False),
    ("produkcja-reczna", "rec1", "MANUAL_PRODUCTION", False),
    ("produkcja-automat", "aut1", "AUTOMATIC_PRODUCTION", False),
    ("pakowanie", "pak1", "PACKING", False),
    ("decoral", "dec1", "DECORAL_PRODUCTION", False),
    ("admin", "adm1", "OFFICE", True),
]


def reset_app_data(session: Session) -> None:
    attachments_root = get_work_order_attachments_path()
    if attachments_root.exists():
        shutil.rmtree(attachments_root)
    attachments_root.mkdir(parents=True, exist_ok=True)

    # Child/log tables first. Crucially, clear stage_transition_events and audit rows: SQLite reuses
    # primary keys after the work orders are deleted, so leftover events/audits from a previous seed
    # would otherwise re-attach to freshly created orders and corrupt the statistics.
    session.execute(delete(AuditEventActor))
    session.execute(delete(AuditEvent))
    session.execute(delete(StageTransitionEvent))
    session.execute(delete(ProcessResourceLock))
    session.execute(delete(WorkOrderAttachment))
    session.execute(delete(WorkOrderStageState))
    session.execute(delete(WorkOrderQuantityBatch))
    session.execute(delete(WorkOrder))
    session.execute(delete(WorkOrderNumberCounter))
    session.execute(delete(Client))
    session.execute(delete(User))
    session.execute(delete(StationPresence))
    session.execute(delete(Employee))
    session.commit()

    for login, password, station_id, is_admin in _STATION_USERS:
        session.add(User(
            login=login,
            hashed_password=hash_password(password),
            station_id=station_id,
            is_admin=is_admin,
        ))
    session.commit()
    print(f"Seeded {len(_STATION_USERS)} users.")

    for company_name, contact_phone, nip in _SEED_CLIENTS:
        session.add(Client(company_name=company_name, contact_phone=contact_phone, nip=nip))
    session.commit()
    print(f"Seeded {len(_SEED_CLIENTS)} clients.")

    for full_name in _SEED_EMPLOYEES:
        session.add(Employee(full_name=full_name))
    session.commit()
    print(f"Seeded {len(_SEED_EMPLOYEES)} employees.")


_SEED_EMPLOYEES = [
    "Jan Kowalski",
    "Anna Nowak",
    "Piotr Wiśniewski",
    "Katarzyna Wójcik",
    "Marek Kamiński",
]


_SEED_CLIENTS = [
    ("Profiltech Sp. z o.o.", "+48 22 123 45 67", "5261040828"),
    ("Aluminco", "+48 71 345 67 89", "8991234567"),
    ("Metal-Bud Zając", "+48 12 456 78 90", "6761234567"),
]


def seed_all_use_cases(session: Session) -> list[SeededScenario]:
    work_order_repository = WorkOrderRepository(session)
    process_repository = ProcessRepository(session)
    manager_repository = ManagerRepository(session)

    work_order_service = WorkOrderService(work_order_repository)
    process_service = ProcessService(process_repository)
    manager_service = ManagerService(manager_repository)

    scenarios: list[SeededScenario] = []
    queue_position = 10

    office_order = create_work_order(
        work_order_service,
        title="Biuro - kompletne zlecenie",
        coating_type=CoatingType.RAL,
        total_quantity=24,
        customer_name="Profiltech Sp. z o.o.",
        ral_code="RAL 7016",
        profiles_quantity=18,
        accessories_quantity=6,
        notes="A. Kompletne zlecenie biurowe gotowe do planowania.",
    )
    scenarios.append(
        scenario(
            "A",
            office_order.order_number,
            "Normal office order, complete, status Do zaplanowania",
            "Office intake / Manager panel",
            office_order.notes or "",
        )
    )

    incomplete_hidden = create_work_order(
        work_order_service,
        title="Biuro - brakujace elementy",
        coating_type=CoatingType.RAL,
        total_quantity=12,
        customer_name="Metal-Bud Zając",
        ral_code="RAL 9005",
        is_incomplete_on_arrival=True,
        profiles_quantity=12,
        accessories_to_count=True,
        notes="B. Niekompletne na przyjeciu, ukryte z planowania.",
    )
    scenarios.append(
        scenario(
            "B",
            incomplete_hidden.order_number,
            "Incomplete order, status Nie kompletne, hidden from planning",
            "Office intake / Manager panel",
            incomplete_hidden.notes or "",
        )
    )

    incomplete_ready = create_work_order(
        work_order_service,
        title="Biuro - do oznaczenia jako kompletne",
        coating_type=CoatingType.RAL,
        total_quantity=15,
        customer_name="Okno-System",
        ral_code="RAL 7035",
        is_incomplete_on_arrival=True,
        profiles_to_count=True,
        accessories_quantity=4,
        notes="C. Uzyj akcji 'Oznacz jako kompletne'.",
    )
    scenarios.append(
        scenario(
            "C",
            incomplete_ready.order_number,
            "Incomplete order ready for 'Oznacz jako kompletne'",
            "Office intake / Work order details",
            incomplete_ready.notes or "",
        )
    )

    manual_ral_surface = create_work_order(
        work_order_service,
        title="RAL manual - przygotowanie",
        coating_type=CoatingType.RAL,
        total_quantity=20,
        customer_name="Aluminco",
        ral_code="RAL 3020",
        profiles_quantity=18,
        accessories_quantity=2,
        notes="D. Plan manualny, gotowe do przygotowania powierzchni.",
    )
    assign_plan(manager_service, manual_ral_surface.id, ProductionType.MANUAL, queue_position)
    queue_position += 10
    scenarios.append(
        scenario(
            "D",
            manual_ral_surface.order_number,
            "Manual RAL planned and ready for surface preparation",
            "Surface preparation",
            manual_ral_surface.notes or "",
        )
    )

    auto_ral_surface = create_work_order(
        work_order_service,
        title="RAL automat - przygotowanie",
        coating_type=CoatingType.RAL,
        total_quantity=18,
        customer_name="Balkon-Tech Sp. z o.o.",
        ral_code="RAL 5010",
        profiles_quantity=15,
        accessories_quantity=3,
        notes="E1. Plan automat, gotowe do przygotowania powierzchni.",
    )
    assign_plan(manager_service, auto_ral_surface.id, ProductionType.AUTOMATIC, queue_position)
    queue_position += 10
    scenarios.append(
        scenario(
            "E",
            auto_ral_surface.order_number,
            "Automatic RAL ready for surface preparation",
            "Surface preparation",
            auto_ral_surface.notes or "",
        )
    )

    decoral_manual = create_work_order(
        work_order_service,
        title="Decoral manual - gotowe do decoral",
        coating_type=CoatingType.DECORAL,
        total_quantity=9,
        customer_name="Fasada Polska",
        ral_code="D-200",
        profiles_quantity=8,
        accessories_quantity=1,
        notes="F. Manualny Decoral po pakowaniu, gotowy do etapu Decoral.",
    )
    assign_plan(manager_service, decoral_manual.id, ProductionType.MANUAL, queue_position)
    queue_position += 10
    advance_to_packing(process_service, decoral_manual.id, counted_quantity=9)
    process_service.complete_packing(decoral_manual.id, counted_quantity=9, ok_quantity=9, correction_quantity=0)
    scenarios.append(
        scenario(
            "F",
            decoral_manual.order_number,
            "Decoral manual flow ready for decoral stage",
            "Decoral production",
            decoral_manual.notes or "",
        )
    )

    decoral_automatic = create_work_order(
        work_order_service,
        title="Decoral automat - gotowe do decoral",
        coating_type=CoatingType.DECORAL,
        total_quantity=11,
        customer_name="Fasada Polska",
        ral_code="D-310",
        profiles_quantity=9,
        accessories_quantity=2,
        notes="G. Automat + Decoral po pakowaniu, gotowe do etapu Decoral.",
    )
    assign_plan(manager_service, decoral_automatic.id, ProductionType.AUTOMATIC, queue_position)
    queue_position += 10
    start_surface_preparation(process_service, decoral_automatic.id, counted_quantity=11)
    finish_surface_preparation(process_service, decoral_automatic.id)
    process_service.start_stage(decoral_automatic.id, ProcessStage.HANGING)
    process_service.finish_stage(decoral_automatic.id, ProcessStage.HANGING)
    _set_consumed_paint(process_service, decoral_automatic.id, kg=1.0)
    process_service.complete_packing(decoral_automatic.id, counted_quantity=11, ok_quantity=11, correction_quantity=0)
    scenarios.append(
        scenario(
            "G",
            decoral_automatic.order_number,
            "Decoral automatic flow ready for automatic plus decoral behavior",
            "Automatic production / Packing / Decoral production",
            decoral_automatic.notes or "",
        )
    )

    packing_split = create_work_order(
        work_order_service,
        title="Pakowanie - podzial 7 i 3",
        coating_type=CoatingType.RAL,
        total_quantity=10,
        customer_name="Profiltech Sp. z o.o.",
        ral_code="RAL 8017",
        profiles_quantity=9,
        accessories_quantity=1,
        notes="H. W pakowaniu, wpisz counted 10, OK 7, corrections 3.",
    )
    assign_plan(manager_service, packing_split.id, ProductionType.MANUAL, queue_position)
    queue_position += 10
    advance_to_packing(process_service, packing_split.id, counted_quantity=10)
    scenarios.append(
        scenario(
            "H",
            packing_split.order_number,
            "Packing split example ready for counted 10, OK 7, corrections 3",
            "Packing",
            packing_split.notes or "",
        )
    )

    correction_parent = create_work_order(
        work_order_service,
        title="Poprawka - zlecenie w trakcie korekty",
        coating_type=CoatingType.RAL,
        total_quantity=10,
        customer_name="Alumar",
        ral_code="RAL 9010",
        profiles_quantity=8,
        accessories_quantity=2,
        notes="I. Poprawka 3 szt. — zlecenie wróciło do planowania.",
    )
    assign_plan(manager_service, correction_parent.id, ProductionType.MANUAL, queue_position)
    queue_position += 10
    advance_to_packing(process_service, correction_parent.id, counted_quantity=10)
    process_service.complete_packing(
        correction_parent.id,
        counted_quantity=10,
        ok_quantity=7,
        correction_quantity=3,
        correction_profiles_quantity=2,
        correction_accessories_quantity=1,
        correction_reason_category="niedomalowanie",
    )
    assign_plan(manager_service, correction_parent.id, ProductionType.MANUAL, queue_position)
    queue_position += 10
    scenarios.append(
        scenario(
            "I",
            correction_parent.order_number,
            "Order returned to planning after correction — 7 OK, 3 correction",
            "Manager panel / Production",
            correction_parent.notes or "",
        )
    )

    attachment_order = create_work_order(
        work_order_service,
        title="Zalacznik PDF",
        coating_type=CoatingType.RAL,
        total_quantity=6,
        customer_name="Konstruktor Sp. z o.o.",
        ral_code="RAL 7040",
        profiles_quantity=5,
        accessories_quantity=1,
        notes="J. Przykladowy zalacznik PDF zapisany lokalnie.",
    )
    create_attachment(work_order_repository, attachment_order.id)
    scenarios.append(
        scenario(
            "J",
            attachment_order.order_number,
            "Order with example PDF attachment metadata and file",
            "Work order attachments",
            attachment_order.notes or "",
        )
    )

    checkpoint_surface_equal = create_work_order(
        work_order_service,
        title="Checkpoint - rowne przygotowanie",
        coating_type=CoatingType.RAL,
        total_quantity=8,
        customer_name="Metal-Bud Zając",
        ral_code="RAL 5005",
        profiles_quantity=7,
        accessories_quantity=1,
        notes="K1. Counted quantity w przygotowaniu rowne planowi.",
    )
    assign_plan(manager_service, checkpoint_surface_equal.id, ProductionType.MANUAL, queue_position)
    queue_position += 10
    start_surface_preparation(process_service, checkpoint_surface_equal.id, counted_quantity=8)
    scenarios.append(
        scenario(
            "K",
            checkpoint_surface_equal.order_number,
            "Surface preparation counted_quantity equal to plan",
            "Surface preparation",
            checkpoint_surface_equal.notes or "",
        )
    )

    checkpoint_surface_diff = create_work_order(
        work_order_service,
        title="Checkpoint - rozne przygotowanie",
        coating_type=CoatingType.RAL,
        total_quantity=8,
        customer_name="Aluminco",
        ral_code="RAL 6021",
        profiles_quantity=7,
        accessories_quantity=1,
        notes="K2. Counted quantity w przygotowaniu rozne od planu.",
    )
    assign_plan(manager_service, checkpoint_surface_diff.id, ProductionType.MANUAL, queue_position)
    queue_position += 10
    start_surface_preparation(process_service, checkpoint_surface_diff.id, counted_quantity=6)
    scenarios.append(
        scenario(
            "K",
            checkpoint_surface_diff.order_number,
            "Surface preparation counted_quantity different from plan",
            "Surface preparation",
            checkpoint_surface_diff.notes or "",
        )
    )

    checkpoint_packing_diff = create_work_order(
        work_order_service,
        title="Checkpoint - roznica w pakowaniu",
        coating_type=CoatingType.RAL,
        total_quantity=10,
        customer_name="Balkon-Tech Sp. z o.o.",
        ral_code="RAL 3003",
        profiles_quantity=9,
        accessories_quantity=1,
        notes="K3. Pakowanie z zapisanym counted_quantity roznym od planu.",
    )
    assign_plan(manager_service, checkpoint_packing_diff.id, ProductionType.MANUAL, queue_position)
    queue_position += 10
    advance_to_packing(process_service, checkpoint_packing_diff.id, counted_quantity=10)
    set_stage_counted_quantity(session, checkpoint_packing_diff.id, ProcessStage.PACKING, counted_quantity=12)
    scenarios.append(
        scenario(
            "K",
            checkpoint_packing_diff.order_number,
            "Packing counted_quantity different from planned quantity",
            "Packing",
            checkpoint_packing_diff.notes or "",
        )
    )

    _queue_demo_customers = ["Technoalum", "Stalmet", "Okno-System"]
    for index in range(1, 4):
        queue_demo = create_work_order(
            work_order_service,
            title=f"Kolejka managera {index}",
            coating_type=CoatingType.RAL,
            total_quantity=5 + index,
            customer_name=_queue_demo_customers[index - 1],
            ral_code=f"RAL 70{index}0",
            profiles_quantity=4 + index,
            accessories_quantity=1,
            notes=f"L{index}. Dedykowane testy drag and drop dla kolejki managera.",
        )
        assign_plan(manager_service, queue_demo.id, ProductionType.MANUAL, queue_position)
        queue_position += 10
        scenarios.append(
            scenario(
                "L",
                queue_demo.order_number,
                f"Manager queue example #{index} for drag and drop",
                "Manager panel queue",
                queue_demo.notes or "",
            )
        )

    multi_round_parent = create_work_order(
        work_order_service,
        title="Wieloetapowa poprawka - dwie rundy",
        coating_type=CoatingType.RAL,
        total_quantity=10,
        customer_name="Alumar",
        ral_code="RAL 1013",
        profiles_quantity=9,
        accessories_quantity=1,
        notes=(
            "M1. Screen: Panel managera — niezaplanowane. Click: zaplanuj ostatnia runde poprawki (1 szt.) i wykonaj pelna sciezke manualna. "
            "Expect: 9 OK wczesniej, ostatnia runda 1 szt. — po zakonczeniu rodzic przejdzie na Gotowe 10/10."
        ),
    )
    assign_plan(manager_service, multi_round_parent.id, ProductionType.MANUAL, queue_position)
    queue_position += 10
    advance_to_packing(process_service, multi_round_parent.id, counted_quantity=10)
    process_service.complete_packing(
        multi_round_parent.id,
        counted_quantity=10,
        ok_quantity=7,
        correction_quantity=3,
        correction_profiles_quantity=2,
        correction_accessories_quantity=1,
        correction_reason_category="niedomalowanie",
    )
    assign_plan(manager_service, multi_round_parent.id, ProductionType.MANUAL, queue_position)
    queue_position += 10
    advance_to_packing(process_service, multi_round_parent.id, counted_quantity=3)
    process_service.complete_packing(
        multi_round_parent.id,
        counted_quantity=3,
        ok_quantity=2,
        correction_quantity=1,
        correction_profiles_quantity=1,
        correction_accessories_quantity=0,
        correction_reason_category="inne",
        correction_reason_note="Druga runda poprawki w danych testowych.",
    )
    scenarios.append(
        scenario(
            "M",
            multi_round_parent.order_number,
            "Manual multi-round order waiting for final correction round — 9 OK, 1 szt. pending",
            "Manager panel / Production",
            multi_round_parent.notes or "",
        )
    )

    automatic_parent = create_work_order(
        work_order_service,
        title="Automat + poprawka - runda korekcyjna",
        coating_type=CoatingType.RAL,
        total_quantity=10,
        customer_name="Profiltech Sp. z o.o.",
        ral_code="RAL 6029",
        profiles_quantity=9,
        accessories_quantity=1,
        notes=(
            "N1. Screen: Pakowanie. Click: zakoncz pakowanie poprawki automatycznej counted 2, OK 2, correction 0. "
            "Expect: zlecenie przejdzie na Gotowe 10/10."
        ),
    )
    assign_plan(manager_service, automatic_parent.id, ProductionType.AUTOMATIC, queue_position)
    queue_position += 10
    advance_to_packing(process_service, automatic_parent.id, counted_quantity=10)
    process_service.complete_packing(
        automatic_parent.id,
        counted_quantity=10,
        ok_quantity=8,
        correction_quantity=2,
        correction_profiles_quantity=1,
        correction_accessories_quantity=1,
        correction_reason_category="wtrącenia",
    )
    assign_plan(manager_service, automatic_parent.id, ProductionType.AUTOMATIC, queue_position)
    queue_position += 10
    advance_to_packing(process_service, automatic_parent.id, counted_quantity=2)
    scenarios.append(
        scenario(
            "N",
            automatic_parent.order_number,
            "Automatic correction round in packing — 8 OK so far, 2 correction ready for completion",
            "Packing",
            automatic_parent.notes or "",
        )
    )

    occupied_queue_first = create_work_order(
        work_order_service,
        title="Konflikt kolejki - zajeta pozycja",
        coating_type=CoatingType.RAL,
        total_quantity=7,
        customer_name="Balkon-Tech Sp. z o.o.",
        ral_code="RAL 7031",
        profiles_quantity=6,
        accessories_quantity=1,
        notes=(
            f"O1. Screen: Panel managera / API docs. Click: uzyj tej pozycji {queue_position} przy planowaniu innego zlecenia "
            f"albo przy zmianie pozycji drugiego zlecenia. Expect: backend zwroci 409 Queue position {queue_position} is already taken."
        ),
    )
    assign_plan(manager_service, occupied_queue_first.id, ProductionType.MANUAL, queue_position)
    queue_conflict_taken = queue_position
    queue_position += 10
    occupied_queue_second = create_work_order(
        work_order_service,
        title="Konflikt kolejki - ruch na zajeta pozycje",
        coating_type=CoatingType.RAL,
        total_quantity=8,
        customer_name="Metal-Bud Zając",
        ral_code="RAL 7032",
        profiles_quantity=7,
        accessories_quantity=1,
        notes=(
            f"O2. Screen: Panel managera / API docs. Click: sprobuj zmienic queue_position tego zlecenia na zajeta pozycje {queue_conflict_taken}. "
            f"Expect: backend zwroci 409 Queue position {queue_conflict_taken} is already taken."
        ),
    )
    assign_plan(manager_service, occupied_queue_second.id, ProductionType.MANUAL, queue_position)
    queue_position += 10
    queue_conflict_candidate = create_work_order(
        work_order_service,
        title="Konflikt kolejki - kandydat do bledu",
        coating_type=CoatingType.RAL,
        total_quantity=9,
        customer_name="Stalmet",
        ral_code="RAL 7033",
        profiles_quantity=8,
        accessories_quantity=1,
        notes=(
            f"O3. Screen: Panel managera / API docs. Click: zaplanuj to zlecenie na zajeta pozycje {queue_conflict_taken}. "
            f"Expect: backend zwroci 409 Queue position {queue_conflict_taken} is already taken."
        ),
    )
    scenarios.append(
        scenario(
            "O",
            occupied_queue_first.order_number,
            "Occupied queue position anchor for conflict testing",
            "Manager panel / API docs",
            occupied_queue_first.notes or "",
        )
    )
    scenarios.append(
        scenario(
            "O",
            occupied_queue_second.order_number,
            "Planned order that should fail when moved into an occupied slot",
            "Manager panel / API docs",
            occupied_queue_second.notes or "",
        )
    )
    scenarios.append(
        scenario(
            "O",
            queue_conflict_candidate.order_number,
            "Unplanned order that should fail when planned into an occupied slot",
            "Manager panel / API docs",
            queue_conflict_candidate.notes or "",
        )
    )

    history_parent = create_work_order(
        work_order_service,
        title="Historia poprawek - zakonczony lancuch rund",
        coating_type=CoatingType.RAL,
        total_quantity=10,
        customer_name="Konstruktor Sp. z o.o.",
        ral_code="RAL 9018",
        profiles_quantity=9,
        accessories_quantity=1,
        notes=(
            "P1. Screen: Szczegoly zlecenia. Click: sprawdz wycofana ilosc i status Gotowe. "
            "Expect: zlecenie jest Gotowe 10/10, przeszlo przez dwie rundy korekcyjne."
        ),
    )
    assign_plan(manager_service, history_parent.id, ProductionType.MANUAL, queue_position)
    queue_position += 10
    advance_to_packing(process_service, history_parent.id, counted_quantity=10)
    process_service.complete_packing(
        history_parent.id,
        counted_quantity=10,
        ok_quantity=7,
        correction_quantity=3,
        correction_profiles_quantity=2,
        correction_accessories_quantity=1,
        correction_reason_category="niedomalowanie",
    )
    assign_plan(manager_service, history_parent.id, ProductionType.MANUAL, queue_position)
    queue_position += 10
    advance_to_packing(process_service, history_parent.id, counted_quantity=3)
    process_service.complete_packing(
        history_parent.id,
        counted_quantity=3,
        ok_quantity=2,
        correction_quantity=1,
        correction_profiles_quantity=1,
        correction_accessories_quantity=0,
        correction_reason_category="inne",
        correction_reason_note="Powtorna poprawka w historii testowej.",
    )
    assign_plan(manager_service, history_parent.id, ProductionType.MANUAL, queue_position)
    queue_position += 10
    advance_to_packing(process_service, history_parent.id, counted_quantity=1)
    process_service.complete_packing(history_parent.id, counted_quantity=1, ok_quantity=1, correction_quantity=0)
    scenarios.append(
        scenario(
            "P",
            history_parent.order_number,
            "Completed order after two correction rounds — history preserved in quantity batches",
            "Work order details / Gotowe",
            history_parent.notes or "",
        )
    )

    # Seeded last on purpose: an automatic order parked at HANGING reserves a packing slot (NA22a),
    # so it must come after the manual packing scenarios above to avoid filling the packing slots.
    auto_ral_hanging_packing = create_work_order(
        work_order_service,
        title="RAL automat - zawieszanie i pakowanie",
        coating_type=CoatingType.RAL,
        total_quantity=14,
        customer_name="Technoalum",
        ral_code="RAL 6018",
        profiles_quantity=12,
        accessories_quantity=2,
        notes="E2. Automat w zawieszaniu; widoczne tez podglady produkcji i pakowania.",
    )
    assign_plan(manager_service, auto_ral_hanging_packing.id, ProductionType.AUTOMATIC, queue_position)
    queue_position += 10
    start_surface_preparation(process_service, auto_ral_hanging_packing.id, counted_quantity=14)
    finish_surface_preparation(process_service, auto_ral_hanging_packing.id)
    process_service.start_stage(auto_ral_hanging_packing.id, ProcessStage.HANGING)
    scenarios.append(
        scenario(
            "E",
            auto_ral_hanging_packing.order_number,
            "Automatic RAL visible for hanging, automatic production preview, and packing",
            "Hanging / Automatic production / Packing",
            auto_ral_hanging_packing.notes or "",
        )
    )

    # Statistics demo last: it sets production_type/queue_position directly (never calls assign_plan),
    # so it does not trigger the manager's completed-order queue compaction over the scenario orders.
    seed_statistics_demo(session, work_order_service, process_service, manager_service)

    return scenarios


# --- Statistics demo data ------------------------------------------------------------------------
# Drives a month of work orders through the real service flow (so state + stage-transition events are
# valid), then rewrites the event timestamps so the Statystyki charts spread across days with a real
# method × coating mix — making throughput, the cycle-time Suma/Średnia breakdown, the Decoral-pass
# series, corrections, and live WIP-aging all visibly populated.

# (method, coating, base_area_m2, quantity) archetypes, rotated to get a realistic mix.
_STATS_ARCHETYPES: list[tuple[ProductionType, CoatingType, float, int]] = [
    (ProductionType.MANUAL, CoatingType.RAL, 22.0, 20),
    (ProductionType.AUTOMATIC, CoatingType.RAL, 35.0, 30),
    (ProductionType.MANUAL, CoatingType.DECORAL, 14.0, 10),
    (ProductionType.MANUAL, CoatingType.RAL, 48.0, 40),
    (ProductionType.AUTOMATIC, CoatingType.RAL, 28.0, 24),
    (ProductionType.AUTOMATIC, CoatingType.DECORAL, 18.0, 12),
    (ProductionType.MANUAL, CoatingType.RAL, 30.0, 26),
]

_STATS_CUSTOMERS = [
    "Profiltech Sp. z o.o.", "Aluminco", "Metal-Bud Zając", "Technoalum", "Stalmet",
    "Okno-System", "Fasada Polska", "Balkon-Tech Sp. z o.o.",
]
_STATS_RAL_CODES = ["RAL 7016", "RAL 9005", "RAL 7035", "RAL 3020", "RAL 5010", "RAL 6018"]
_STATS_DECORAL_CODES = ["D-200", "D-310"]
_STATS_CORRECTION_REASONS = ["niedomalowanie", "wtrącenia", "zarysowania", "inne"]

SP, HG, PR, PK, DC = (
    ProcessStage.SURFACE_PREPARATION,
    ProcessStage.HANGING,
    ProcessStage.PRODUCTION,
    ProcessStage.PACKING,
    ProcessStage.DECORAL_PRODUCTION,
)
IP, DONE = StageStatus.IN_PROGRESS, StageStatus.DONE


def _stage_offsets(method: ProductionType, coating: CoatingType) -> dict[tuple[ProcessStage, StageStatus], int]:
    """Minutes-from-start for each (stage, status) event, so stages have realistic, differing durations.

    Manual production runs longer than the automatic line; decoral adds a separate pass after packing.
    The gaps between one stage's DONE and the next stage's IN_PROGRESS show up as queue-wait time.
    """
    extra = 8 if coating == CoatingType.DECORAL else 0
    if method == ProductionType.MANUAL:
        offsets = {
            (SP, IP): 0, (SP, DONE): 12,
            (PR, IP): 20, (PR, DONE): 64 + extra,
            (PK, IP): 72 + extra, (PK, DONE): 86 + extra,
        }
    else:
        # Automatic: hanging, then PRODUCTION + PACKING start implicitly at hanging finish.
        offsets = {
            (SP, IP): 0, (SP, DONE): 10,
            (HG, IP): 16, (HG, DONE): 30,
            (PR, IP): 30, (PR, DONE): 70 + extra,
            (PK, IP): 30, (PK, DONE): 80 + extra,
        }
    if coating == CoatingType.DECORAL:
        pack_done = offsets[(PK, DONE)]
        offsets[(DC, IP)] = pack_done + 12
        offsets[(DC, DONE)] = pack_done + 12 + 30
    return offsets


def _add_stage_event(
    session: Session,
    work_order_id: int,
    stage: ProcessStage,
    status: StageStatus,
    occurred_at: datetime,
) -> None:
    session.add(
        StageTransitionEvent(
            work_order_id=work_order_id,
            batch_id=None,
            stage=stage,
            status=status,
            station_id=StationId.SYSTEM,
            occurred_at=occurred_at,
        )
    )


def _set_stage_state(
    session: Session,
    work_order_id: int,
    stage: ProcessStage,
    status: StageStatus,
    updated_at: datetime,
    counted_quantity: int | None = None,
) -> None:
    stage_state = session.scalar(
        select(WorkOrderStageState).where(
            WorkOrderStageState.work_order_id == work_order_id,
            WorkOrderStageState.stage == stage,
        )
    )
    if stage_state is not None:
        stage_state.status = status
        stage_state.updated_at = updated_at
        if counted_quantity is not None:
            stage_state.counted_quantity = counted_quantity


def seed_statistics_demo(
    session: Session,
    work_order_service: WorkOrderService,
    process_service: ProcessService,
    manager_service: ManagerService,
) -> None:
    """Build a month of demo statistics by constructing state + stage-transition events directly.

    Runs after the workflow scenarios. It deliberately does NOT use ManagerService.assign_plan (whose
    completed-order queue compaction collides at this scale) nor the process-service stage transitions
    (which hold the single HANGING lock / packing slots the scenarios leave occupied). Writing the
    completed/in-progress state and the timestamped events by hand gives full control of the dates so
    the Statystyki charts spread across the month with a real method × coating mix.
    """
    today = date.today()
    month_start = today.replace(day=1)
    queue_position = 1000  # high/trailing positions so demo history sits past the live queue
    made: list[tuple[int, datetime, ProductionType, CoatingType]] = []

    archetype_index = 0
    day = month_start
    while day <= today:
        orders_today = 2 + (day.day % 3)  # 2..4 completed orders per day
        for k in range(orders_today):
            method, coating, base_area, quantity = _STATS_ARCHETYPES[archetype_index % len(_STATS_ARCHETYPES)]
            archetype_index += 1
            # Vary the area a little per day so the daily bars are uneven (more lifelike).
            area = round(base_area * (0.8 + ((day.day * 7 + k) % 5) * 0.1), 1)
            base_dt = datetime(day.year, day.month, day.day, 6 + k * 3, 0, tzinfo=UTC)
            ral_code = (
                _STATS_DECORAL_CODES[archetype_index % len(_STATS_DECORAL_CODES)]
                if coating == CoatingType.DECORAL
                else _STATS_RAL_CODES[archetype_index % len(_STATS_RAL_CODES)]
            )

            work_order = create_work_order(
                work_order_service,
                title=f"Statystyki {day.isoformat()} #{k + 1}",
                coating_type=coating,
                total_quantity=quantity,
                customer_name=_STATS_CUSTOMERS[archetype_index % len(_STATS_CUSTOMERS)],
                ral_code=ral_code,
                profiles_quantity=quantity,
                accessories_quantity=0,
                notes="Dane demonstracyjne do statystyk.",
            )

            offsets = _stage_offsets(method, coating)
            stage_sequence = ProcessService.get_stage_sequence_for_configuration(coating, method)
            persisted = session.get(WorkOrder, work_order.id)
            persisted.production_type = method
            persisted.queue_position = queue_position
            persisted.total_area_m2 = area
            persisted.completed_quantity = quantity
            queue_position += 1

            # Mark every stage in this order's path DONE and emit the IN_PROGRESS/DONE events that the
            # stats read, all dated within the order's day.
            for stage in stage_sequence:
                done_at = base_dt + timedelta(minutes=offsets[(stage, DONE)])
                _set_stage_state(
                    session, work_order.id, stage, StageStatus.DONE, done_at,
                    counted_quantity=quantity if stage in (SP, PK) else None,
                )
                _add_stage_event(session, work_order.id, stage, IP, base_dt + timedelta(minutes=offsets[(stage, IP)]))
                _add_stage_event(session, work_order.id, stage, DONE, done_at)

            # The MAIN batch finishes on the last stage; no active batch remains (a completed order).
            main_batch = session.scalar(
                select(WorkOrderQuantityBatch).where(
                    WorkOrderQuantityBatch.work_order_id == work_order.id,
                    WorkOrderQuantityBatch.type == QuantityBatchType.MAIN,
                )
            )
            if main_batch is not None:
                main_batch.is_active = False
                main_batch.current_stage = stage_sequence[-1]
                main_batch.current_stage_status = StageStatus.DONE
            persisted.current_active_batch_id = None
            session.flush()

            made.append((work_order.id, base_dt, method, coating))
        day += timedelta(days=1)

    # Spread a handful of corrections across the month (counted in the Poprawki chart + reason report)
    # as historical, inactive CORRECTION batches — does not disturb the completed orders' state.
    corrections = 0
    for position, (order_id, base_dt, _method, coating) in enumerate(made):
        if coating != CoatingType.RAL or position % 5 != 2:
            continue
        main_batch = session.scalar(
            select(WorkOrderQuantityBatch).where(
                WorkOrderQuantityBatch.work_order_id == order_id,
                WorkOrderQuantityBatch.type == QuantityBatchType.MAIN,
            )
        )
        session.add(
            WorkOrderQuantityBatch(
                work_order_id=order_id,
                quantity=2 + position % 3,
                type=QuantityBatchType.CORRECTION,
                parent_batch_id=main_batch.id if main_batch else None,
                is_active=False,
                current_stage=None,
                current_stage_status=None,
                is_partial=True,
                correction_reason_category=_STATS_CORRECTION_REASONS[position % len(_STATS_CORRECTION_REASONS)],
                created_at=base_dt,
            )
        )
        corrections += 1
    session.commit()

    # Live WIP-aging: a few orders left genuinely in progress at varied ages (some >24h => red),
    # with a method × coating mix.
    now = datetime.now(UTC)
    wip_specs = [
        (ProductionType.MANUAL, CoatingType.RAL, ProcessStage.PRODUCTION, 30),
        (ProductionType.MANUAL, CoatingType.DECORAL, ProcessStage.PRODUCTION, 8),
        (ProductionType.AUTOMATIC, CoatingType.RAL, ProcessStage.HANGING, 52),
        (ProductionType.AUTOMATIC, CoatingType.DECORAL, ProcessStage.SURFACE_PREPARATION, 4),
        (ProductionType.MANUAL, CoatingType.RAL, ProcessStage.SURFACE_PREPARATION, 2),
        (ProductionType.MANUAL, CoatingType.RAL, ProcessStage.PRODUCTION, 26),
    ]
    for index, (method, coating, target_stage, hours_ago) in enumerate(wip_specs):
        quantity = 16 + index * 2
        ral_code = _STATS_DECORAL_CODES[index % 2] if coating == CoatingType.DECORAL else _STATS_RAL_CODES[index % len(_STATS_RAL_CODES)]
        work_order = create_work_order(
            work_order_service,
            title=f"W toku #{index + 1}",
            coating_type=coating,
            total_quantity=quantity,
            customer_name=_STATS_CUSTOMERS[index % len(_STATS_CUSTOMERS)],
            ral_code=ral_code,
            profiles_quantity=quantity,
            accessories_quantity=0,
            notes="W toku — demonstracja widoku „Zlecenia w toku”.",
        )
        persisted = session.get(WorkOrder, work_order.id)
        persisted.production_type = method
        persisted.queue_position = queue_position
        persisted.total_area_m2 = float(quantity)
        queue_position += 1

        started_at = now - timedelta(hours=hours_ago)
        stage_sequence = ProcessService.get_stage_sequence_for_configuration(coating, method)
        # Stages before the target are done; the target is in progress; later stages untouched.
        for stage in stage_sequence:
            if stage == target_stage:
                _set_stage_state(
                    session, work_order.id, stage, StageStatus.IN_PROGRESS, started_at,
                    counted_quantity=quantity if stage in (SP, PK) else None,
                )
                _add_stage_event(session, work_order.id, stage, IP, started_at)
                break
            _set_stage_state(
                session, work_order.id, stage, StageStatus.DONE, started_at - timedelta(minutes=20),
                counted_quantity=quantity if stage in (SP, PK) else None,
            )

        main_batch = session.scalar(
            select(WorkOrderQuantityBatch).where(
                WorkOrderQuantityBatch.work_order_id == work_order.id,
                WorkOrderQuantityBatch.type == QuantityBatchType.MAIN,
            )
        )
        if main_batch is not None:
            main_batch.current_stage = target_stage
            main_batch.current_stage_status = StageStatus.IN_PROGRESS
        session.flush()
    session.commit()

    print(f"Seeded statistics demo: {len(made)} completed orders, {corrections} corrections, {len(wip_specs)} in-progress.")


def create_work_order(
    work_order_service: WorkOrderService,
    *,
    title: str,
    coating_type: CoatingType,
    total_quantity: int,
    customer_name: str,
    ral_code: str,
    is_incomplete_on_arrival: bool = False,
    profiles_quantity: int | None = None,
    profiles_to_count: bool = False,
    accessories_quantity: int | None = None,
    accessories_to_count: bool = False,
    notes: str | None = None,
):
    paint_code, paint_producer = _PAINT_BY_RAL.get(ral_code, ("FARBA-SEED", "AkzoNobel"))
    payload = WorkOrderCreate(
        title=title,
        total_quantity=total_quantity,
        description=title,
        customer_name=customer_name,
        ral_code=ral_code,
        paint_code=paint_code,
        paint_producer=paint_producer,
        coating_type=coating_type,
        received_date=date.today(),
        planned_pickup_date=date.today() + timedelta(days=7),
        total_area_m2=float(total_quantity),
        is_incomplete_on_arrival=is_incomplete_on_arrival,
        profiles_quantity=profiles_quantity,
        profiles_to_count=profiles_to_count,
        accessories_quantity=accessories_quantity,
        accessories_to_count=accessories_to_count,
        notes=notes,
    )
    return work_order_service.create_work_order(payload)


def assign_plan(
    manager_service: ManagerService,
    work_order_id: int,
    production_type: ProductionType,
    queue_position: int,
) -> None:
    manager_service.assign_plan(
        work_order_id,
        WorkOrderPlanAssignRequest(production_type=production_type, queue_position=queue_position),
    )


def start_surface_preparation(process_service: ProcessService, work_order_id: int, *, counted_quantity: int) -> None:
    process_service.start_stage(
        work_order_id,
        ProcessStage.SURFACE_PREPARATION,
        counted_quantity=counted_quantity,
    )


def finish_surface_preparation(process_service: ProcessService, work_order_id: int) -> None:
    process_service.finish_stage(work_order_id, ProcessStage.SURFACE_PREPARATION)


def advance_to_packing(process_service: ProcessService, work_order_id: int, *, counted_quantity: int) -> None:
    work_order = process_service.get_work_order_process(work_order_id)
    is_correction_round = (
        work_order.active_batch is not None
        and work_order.active_batch.parent_batch_id is not None
    )
    skips_surface_preparation = work_order.is_correction or work_order.work_order_kind == WorkOrderKind.PRZEMALOWANKA or is_correction_round
    if not skips_surface_preparation:
        start_surface_preparation(process_service, work_order_id, counted_quantity=counted_quantity)
        finish_surface_preparation(process_service, work_order_id)

    if work_order.production_type == ProductionType.AUTOMATIC:
        process_service.start_stage(work_order_id, ProcessStage.HANGING)
        process_service.finish_stage(work_order_id, ProcessStage.HANGING)
        _set_consumed_paint(process_service, work_order_id, kg=1.0)
        return

    process_service.start_stage(work_order_id, ProcessStage.PRODUCTION)
    process_service.finish_stage(work_order_id, ProcessStage.PRODUCTION)
    process_service.start_stage(work_order_id, ProcessStage.PACKING)


def get_latest_correction_child(repository: WorkOrderRepository, parent_order_id: int) -> WorkOrder:
    parent = repository.get_by_id(parent_order_id)
    if parent is None or not parent.correction_orders:
        raise RuntimeError(f"Expected correction order for parent {parent_order_id}.")
    return sorted(parent.correction_orders, key=lambda order: (order.created_at, order.id))[-1]


def create_attachment(repository: WorkOrderRepository, work_order_id: int) -> None:
    root_path = get_work_order_attachments_path()
    attachment_directory = root_path / str(work_order_id)
    attachment_directory.mkdir(parents=True, exist_ok=True)

    stored_filename = "seeded-attachment.pdf"
    absolute_path = attachment_directory / stored_filename
    absolute_path.write_bytes(PDF_BYTES)

    attachment = WorkOrderAttachment(
        work_order_id=work_order_id,
        original_filename="instrukcja-testowa.pdf",
        stored_filename=stored_filename,
        storage_path=absolute_path.relative_to(root_path).as_posix(),
        content_type="application/pdf",
        file_size=len(PDF_BYTES),
        attachment_type="SPEC",
        description="Przykladowy plik PDF do testow lokalnych.",
    )
    repository.add_attachment(attachment)
    repository.commit()


def set_stage_counted_quantity(
    session: Session,
    work_order_id: int,
    stage: ProcessStage,
    *,
    counted_quantity: int,
) -> None:
    stage_state = session.scalar(
        select(WorkOrderStageState).where(
            WorkOrderStageState.work_order_id == work_order_id,
            WorkOrderStageState.stage == stage,
        )
    )
    if stage_state is None:
        raise RuntimeError(f"Stage {stage.value} not found for work order {work_order_id}.")
    stage_state.counted_quantity = counted_quantity
    stage_state.updated_at = datetime.now(UTC)
    session.commit()


def _set_consumed_paint(process_service: ProcessService, work_order_id: int, *, kg: float) -> None:
    """Bypass paint stock check for seed data — set consumed quantity directly."""
    from app.work_orders.models import WorkOrder as _WO
    wo = process_service.repository.session.get(_WO, work_order_id)
    if wo is not None:
        wo.consumed_paint_quantity_kg = kg
        process_service.repository.session.flush()


def scenario(code: str, order_number: str, purpose: str, page: str, details: str) -> SeededScenario:
    return SeededScenario(code=code, order_number=order_number, purpose=purpose, page=page, details=details)


def print_seed_report(scenarios: list[SeededScenario]) -> None:
    print("Seeded local dev database.")
    print("Created order numbers and use cases:")
    for item in scenarios:
        print(f"- [{item.code}] {item.order_number}: {item.purpose}")
        print(f"  Screen: {item.page}")
        print(f"  Action / Expectation: {item.details}")


if __name__ == "__main__":
    raise SystemExit(main())
