import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config


REPO_ROOT = Path(__file__).resolve().parents[1]
REVISION_BEFORE_PHASE2 = "20260529_0014"
REVISION_PHASE2 = "20260529_0015"


def test_clean_upgrade_applies_phase2_constraints(tmp_path: Path) -> None:
    db_path = tmp_path / "phase2_clean.db"

    _upgrade_database(db_path, REVISION_BEFORE_PHASE2)
    parent_id = _insert_work_order(db_path, order_number="WO-2026-9800")
    _insert_work_order(db_path, order_number="WO-2026-9801", is_correction=1, parent_order_id=parent_id)
    _insert_batch(db_path, work_order_id=parent_id, is_active=1, current_stage="PRODUCTION", current_stage_status="IN_PROGRESS")
    _insert_batch(db_path, work_order_id=parent_id, is_active=0, current_stage="PACKING", current_stage_status="DONE")

    _upgrade_database(db_path, REVISION_PHASE2)

    assert _read_revision(db_path) == REVISION_PHASE2


def test_orphan_correction_blocks_phase2_upgrade(tmp_path: Path) -> None:
    db_path = tmp_path / "phase2_orphan_correction.db"

    _upgrade_database(db_path, REVISION_BEFORE_PHASE2)
    _insert_work_order(db_path, order_number="WO-2026-9802", is_correction=1, parent_order_id=None)

    with pytest.raises(RuntimeError, match="correction work orders require"):
        _upgrade_database(db_path, REVISION_PHASE2)

    assert _read_revision(db_path) == REVISION_BEFORE_PHASE2


def test_multiple_active_batches_block_phase2_upgrade(tmp_path: Path) -> None:
    db_path = tmp_path / "phase2_multiple_active_batches.db"

    _upgrade_database(db_path, REVISION_BEFORE_PHASE2)
    work_order_id = _insert_work_order(db_path, order_number="WO-2026-9803")
    _insert_batch(db_path, work_order_id=work_order_id, is_active=1, current_stage="PRODUCTION", current_stage_status="IN_PROGRESS")
    _insert_batch(db_path, work_order_id=work_order_id, is_active=1, current_stage="PACKING", current_stage_status="NOT_STARTED")

    with pytest.raises(RuntimeError, match="one active quantity batch"):
        _upgrade_database(db_path, REVISION_PHASE2)

    assert _read_revision(db_path) == REVISION_BEFORE_PHASE2


def test_inactive_non_done_batch_blocks_phase2_upgrade(tmp_path: Path) -> None:
    db_path = tmp_path / "phase2_inactive_non_done_batch.db"

    _upgrade_database(db_path, REVISION_BEFORE_PHASE2)
    work_order_id = _insert_work_order(db_path, order_number="WO-2026-9804")
    _insert_batch(db_path, work_order_id=work_order_id, is_active=0, current_stage="PACKING", current_stage_status="IN_PROGRESS")

    with pytest.raises(RuntimeError, match="inactive quantity batches require DONE"):
        _upgrade_database(db_path, REVISION_PHASE2)

    assert _read_revision(db_path) == REVISION_BEFORE_PHASE2



def _insert_work_order(
    db_path: Path,
    *,
    order_number: str,
    is_correction: int = 0,
    parent_order_id: int | None = None,
) -> int:
    with sqlite3.connect(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO work_orders (
                order_number, title, total_quantity, completed_quantity, current_active_batch_id, parent_order_id,
                is_correction, description, customer_name, ral_code, paint_producer, status, coating_type,
                production_type, queue_namespace, queue_position, received_date, planned_pickup_date, total_area_m2,
                is_incomplete_on_arrival, profiles_quantity, profiles_to_count, accessories_quantity, accessories_to_count,
                notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_number,
                order_number,
                10,
                0,
                None,
                parent_order_id,
                is_correction,
                None,
                "Customer",
                "RAL 9005",
                "Producer",
                "ENTERED",
                "RAL",
                None,
                "CORRECTIONS" if is_correction else "MAIN",
                None,
                "2026-05-25",
                None,
                None,
                0,
                None,
                1,
                None,
                1,
                None,
                "2026-05-25T00:00:00+00:00",
                "2026-05-25T00:00:00+00:00",
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


def _insert_batch(
    db_path: Path,
    *,
    work_order_id: int,
    is_active: int,
    current_stage: str,
    current_stage_status: str,
) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO work_order_quantity_batches (
                work_order_id, quantity, type, parent_batch_id, is_active, current_stage, current_stage_status, is_partial, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (work_order_id, 10, "MAIN", None, is_active, current_stage, current_stage_status, 0, "2026-05-25T00:00:00+00:00"),
        )
        connection.commit()


def _read_revision(db_path: Path) -> str:
    with sqlite3.connect(db_path) as connection:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    return row[0]


def _upgrade_database(db_path: Path, revision: str) -> None:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    with _temporary_database_url(f"sqlite:///{db_path.resolve().as_posix()}"):
        command.upgrade(config, revision)


@contextmanager
def _temporary_database_url(database_url: str):
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        yield
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url