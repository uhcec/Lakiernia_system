from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
import shutil

from alembic import command
from alembic.config import Config
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import get_settings, get_work_order_attachments_path
from app.database import models as _models  # noqa: F401
from app.database.session import get_session_factory
from app.manager.repository import ManagerRepository
from app.manager.schemas import WorkOrderPlanAssignRequest
from app.manager.service import ManagerService
from app.process.enums import CoatingType, ProcessStage, ProductionType, StageStatus
from app.process.models import WorkOrderQuantityBatch, WorkOrderStageState
from app.process.repository import ProcessRepository
from app.process.service import ProcessService
from app.shared.enums import WorkOrderStatus
from app.work_orders.models import WorkOrder, WorkOrderAttachment
from app.work_orders.repository import WorkOrderRepository
from app.work_orders.schemas import WorkOrderCreate
from app.work_orders.service import WorkOrderService


PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<<>>\n%%EOF\n"


@dataclass(slots=True)
class SeededScenario:
    code: str
    order_number: str
    purpose: str
    page: str
    details: str


def main() -> int:
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


def reset_app_data(session: Session) -> None:
    attachments_root = get_work_order_attachments_path()
    if attachments_root.exists():
        shutil.rmtree(attachments_root)
    attachments_root.mkdir(parents=True, exist_ok=True)

    session.execute(delete(WorkOrderAttachment))
    session.execute(delete(WorkOrderStageState))
    session.execute(delete(WorkOrderQuantityBatch))
    session.execute(delete(WorkOrder))
    session.commit()


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
        customer_name="Office Client",
        ral_code="RAL 7016",
        profiles_quantity=24,
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
        customer_name="Incomplete Client",
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
        customer_name="Return Client",
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
        customer_name="Manual Flow",
        ral_code="RAL 3020",
        profiles_quantity=20,
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
        customer_name="Auto Surface",
        ral_code="RAL 5010",
        profiles_quantity=18,
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

    auto_ral_hanging_packing = create_work_order(
        work_order_service,
        title="RAL automat - zawieszanie i pakowanie",
        coating_type=CoatingType.RAL,
        total_quantity=14,
        customer_name="Auto Hanging",
        ral_code="RAL 6018",
        profiles_quantity=14,
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

    decoral_manual = create_work_order(
        work_order_service,
        title="Decoral manual - gotowe do decoral",
        coating_type=CoatingType.DECORAL,
        total_quantity=9,
        customer_name="Decoral Manual",
        ral_code="D-200",
        profiles_quantity=9,
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
        customer_name="Decoral Auto",
        ral_code="D-310",
        profiles_quantity=11,
        accessories_quantity=2,
        notes="G. Automat + Decoral po pakowaniu, gotowe do etapu Decoral.",
    )
    assign_plan(manager_service, decoral_automatic.id, ProductionType.AUTOMATIC, queue_position)
    queue_position += 10
    start_surface_preparation(process_service, decoral_automatic.id, counted_quantity=11)
    finish_surface_preparation(process_service, decoral_automatic.id)
    process_service.start_stage(decoral_automatic.id, ProcessStage.HANGING)
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
        customer_name="Packing Split",
        ral_code="RAL 8017",
        profiles_quantity=10,
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
        title="Poprawka - rodzic i dziecko",
        coating_type=CoatingType.RAL,
        total_quantity=10,
        customer_name="Correction Parent",
        ral_code="RAL 9010",
        profiles_quantity=10,
        accessories_quantity=2,
        notes="I. Rodzic po pakowaniu z poprawka 3 szt.",
    )
    assign_plan(manager_service, correction_parent.id, ProductionType.MANUAL, queue_position)
    queue_position += 10
    advance_to_packing(process_service, correction_parent.id, counted_quantity=10)
    process_service.complete_packing(correction_parent.id, counted_quantity=10, ok_quantity=7, correction_quantity=3)
    correction_child = get_latest_correction_child(work_order_repository, correction_parent.id)
    assign_plan(manager_service, correction_child.id, ProductionType.MANUAL, queue_position)
    queue_position += 10
    scenarios.append(
        scenario(
            "I",
            correction_parent.order_number,
            "Parent order that generated a child correction order",
            "Packing / Work order details",
            correction_parent.notes or "",
        )
    )
    scenarios.append(
        scenario(
            "I",
            correction_child.order_number,
            "Child correction order planned and visible in manager planning",
            "Manager panel",
            correction_child.notes or "",
        )
    )

    attachment_order = create_work_order(
        work_order_service,
        title="Zalacznik PDF",
        coating_type=CoatingType.RAL,
        total_quantity=6,
        customer_name="Attachment Client",
        ral_code="RAL 7040",
        profiles_quantity=6,
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
        customer_name="Checkpoint Equal",
        ral_code="RAL 5005",
        profiles_quantity=8,
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
        customer_name="Checkpoint Diff",
        ral_code="RAL 6021",
        profiles_quantity=8,
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
        customer_name="Packing Diff",
        ral_code="RAL 3003",
        profiles_quantity=10,
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

    for index in range(1, 4):
        queue_demo = create_work_order(
            work_order_service,
            title=f"Kolejka managera {index}",
            coating_type=CoatingType.RAL,
            total_quantity=5 + index,
            customer_name="Queue Demo",
            ral_code=f"RAL 70{index}0",
            profiles_quantity=5 + index,
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
        title="Wieloetapowa poprawka - rodzic",
        coating_type=CoatingType.RAL,
        total_quantity=10,
        customer_name="Multi Round",
        ral_code="RAL 1013",
        profiles_quantity=10,
        accessories_quantity=1,
        notes=(
            "M1. Screen: Szczegoly zlecenia / Pakowanie. Click: otworz rodzica i przejdz do historii poprawek. "
            "Expect: rodzic ma 7 OK, czeka na ostatnia poprawke 1 szt. przez lancuch poprawek."
        ),
    )
    assign_plan(manager_service, multi_round_parent.id, ProductionType.MANUAL, queue_position)
    queue_position += 10
    advance_to_packing(process_service, multi_round_parent.id, counted_quantity=10)
    process_service.complete_packing(multi_round_parent.id, counted_quantity=10, ok_quantity=7, correction_quantity=3)

    multi_round_first_child = get_latest_correction_child(work_order_repository, multi_round_parent.id)
    multi_round_first_child.notes = (
        "M2. Screen: Szczegoly zlecenia dziecka. Click: sprawdz, ze to dziecko ma juz wynik 2 OK / 1 poprawka. "
        "Expect: status dalej Czeka na poprawki, a ostatnie dziecko 1 szt. jest jeszcze nieplanowane."
    )
    work_order_repository.commit()
    assign_plan(manager_service, multi_round_first_child.id, ProductionType.MANUAL, queue_position)
    queue_position += 10
    advance_to_packing(process_service, multi_round_first_child.id, counted_quantity=3)
    process_service.complete_packing(multi_round_first_child.id, counted_quantity=3, ok_quantity=2, correction_quantity=1)

    multi_round_last_child = get_latest_correction_child(work_order_repository, multi_round_first_child.id)
    multi_round_last_child.notes = (
        "M3. Screen: Panel managera / niezaplanowane. Click: zaplanuj te ostatnia poprawke, wykonaj pelna sciezke manualna i zakoncz pakowanie 1/0. "
        "Expect: to zlecenie, jego rodzic i oryginalny rodzic przejda na Gotowe 10/10."
    )
    work_order_repository.commit()
    scenarios.append(
        scenario(
            "M",
            multi_round_parent.order_number,
            "Manual multi-round correction parent waiting for the last correction link",
            "Work order details / Packing",
            multi_round_parent.notes or "",
        )
    )
    scenarios.append(
        scenario(
            "M",
            multi_round_first_child.order_number,
            "Intermediate correction order already split into 2 OK and 1 more correction",
            "Work order details",
            multi_round_first_child.notes or "",
        )
    )
    scenarios.append(
        scenario(
            "M",
            multi_round_last_child.order_number,
            "Final unplanned correction order that closes the whole chain",
            "Manager panel",
            multi_round_last_child.notes or "",
        )
    )

    automatic_parent = create_work_order(
        work_order_service,
        title="Automat + poprawka - rodzic",
        coating_type=CoatingType.RAL,
        total_quantity=10,
        customer_name="Automatic Correction",
        ral_code="RAL 6029",
        profiles_quantity=10,
        accessories_quantity=1,
        notes=(
            "N1. Screen: Szczegoly zlecenia / Pakowanie. Click: sprawdz rodzica po rozdziale 8 OK / 2 poprawka. "
            "Expect: rodzic ma status Czeka na poprawki i czeka na dziecko automatyczne."
        ),
    )
    assign_plan(manager_service, automatic_parent.id, ProductionType.AUTOMATIC, queue_position)
    queue_position += 10
    advance_to_packing(process_service, automatic_parent.id, counted_quantity=10)
    process_service.complete_packing(automatic_parent.id, counted_quantity=10, ok_quantity=8, correction_quantity=2)

    automatic_child = get_latest_correction_child(work_order_repository, automatic_parent.id)
    automatic_child.notes = (
        "N2. Screen: Pakowanie. Click: zakoncz pakowanie automatycznej poprawki counted 2, OK 2, correction 0. "
        "Expect: dziecko i rodzic przejda na Gotowe 10/10 bez recznej zmiany statusu."
    )
    work_order_repository.commit()
    assign_plan(manager_service, automatic_child.id, ProductionType.AUTOMATIC, queue_position)
    queue_position += 10
    advance_to_packing(process_service, automatic_child.id, counted_quantity=2)
    scenarios.append(
        scenario(
            "N",
            automatic_parent.order_number,
            "Automatic parent waiting for a correction child to merge back",
            "Work order details / Packing",
            automatic_parent.notes or "",
        )
    )
    scenarios.append(
        scenario(
            "N",
            automatic_child.order_number,
            "Automatic correction child already positioned in packing for final completion",
            "Packing",
            automatic_child.notes or "",
        )
    )

    occupied_queue_first = create_work_order(
        work_order_service,
        title="Konflikt kolejki - zajeta pozycja",
        coating_type=CoatingType.RAL,
        total_quantity=7,
        customer_name="Queue Conflict",
        ral_code="RAL 7031",
        profiles_quantity=7,
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
        customer_name="Queue Conflict",
        ral_code="RAL 7032",
        profiles_quantity=8,
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
        customer_name="Queue Conflict",
        ral_code="RAL 7033",
        profiles_quantity=9,
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
        title="Historia poprawek - zakonczony lancuch",
        coating_type=CoatingType.RAL,
        total_quantity=10,
        customer_name="History Chain",
        ral_code="RAL 9018",
        profiles_quantity=10,
        accessories_quantity=1,
        notes=(
            "P1. Screen: Szczegoly zlecenia. Click: otworz rodzica i przejdz po relacjach rodzic-dziecko. "
            "Expect: caly lancuch poprawek jest zakonczony, a rodzic ma Gotowe 10/10."
        ),
    )
    assign_plan(manager_service, history_parent.id, ProductionType.MANUAL, queue_position)
    queue_position += 10
    advance_to_packing(process_service, history_parent.id, counted_quantity=10)
    process_service.complete_packing(history_parent.id, counted_quantity=10, ok_quantity=7, correction_quantity=3)

    history_first_child = get_latest_correction_child(work_order_repository, history_parent.id)
    history_first_child.notes = (
        "P2. Screen: Szczegoly pierwszej poprawki. Click: sprawdz relacje z rodzicem i kolejnym dzieckiem. "
        "Expect: pierwsza poprawka jest tez zakonczona i zachowuje historie laczenia."
    )
    work_order_repository.commit()
    assign_plan(manager_service, history_first_child.id, ProductionType.MANUAL, queue_position)
    queue_position += 10
    advance_to_packing(process_service, history_first_child.id, counted_quantity=3)
    process_service.complete_packing(history_first_child.id, counted_quantity=3, ok_quantity=2, correction_quantity=1)

    history_second_child = get_latest_correction_child(work_order_repository, history_first_child.id)
    history_second_child.notes = (
        "P3. Screen: Szczegoly drugiej poprawki. Click: sprawdz, ze to ostatnie ogniwo zostalo zakonczone 1/0. "
        "Expect: wszystkie trzy zlecenia sa Gotowe, a historia korekt zostaje zachowana."
    )
    work_order_repository.commit()
    assign_plan(manager_service, history_second_child.id, ProductionType.MANUAL, queue_position)
    queue_position += 10
    advance_to_packing(process_service, history_second_child.id, counted_quantity=1)
    process_service.complete_packing(history_second_child.id, counted_quantity=1, ok_quantity=1, correction_quantity=0)
    scenarios.append(
        scenario(
            "P",
            history_parent.order_number,
            "Completed parent with a preserved multi-step correction history chain",
            "Work order details",
            history_parent.notes or "",
        )
    )
    scenarios.append(
        scenario(
            "P",
            history_first_child.order_number,
            "Completed first correction with its own correction history",
            "Work order details",
            history_first_child.notes or "",
        )
    )
    scenarios.append(
        scenario(
            "P",
            history_second_child.order_number,
            "Completed final correction closing the history chain",
            "Work order details",
            history_second_child.notes or "",
        )
    )

    return scenarios


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
    payload = WorkOrderCreate(
        title=title,
        total_quantity=total_quantity,
        description=title,
        customer_name=customer_name,
        ral_code=ral_code,
        paint_producer="AkzoNobel",
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
    start_surface_preparation(process_service, work_order_id, counted_quantity=counted_quantity)
    finish_surface_preparation(process_service, work_order_id)

    if work_order.production_type == ProductionType.AUTOMATIC:
        process_service.start_stage(work_order_id, ProcessStage.HANGING)
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