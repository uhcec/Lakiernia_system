import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_clean_upgrade_applies_phase1_constraints(tmp_path: Path) -> None:
    db_path = tmp_path / "phase1_clean.db"

    _upgrade_database(db_path, "20260527_0011")
    _insert_valid_work_order(db_path, order_number="WO-2026-9500")

    _upgrade_database(db_path, "20260527_0012")

    assert _read_revision(db_path) == "20260527_0012"


def test_dirty_work_order_blocks_phase1_upgrade(tmp_path: Path) -> None:
    db_path = tmp_path / "phase1_dirty_work_order.db"

    _upgrade_database(db_path, "20260527_0011")
    _insert_valid_work_order(db_path, order_number="WO-2026-9501", queue_position=0)

    with pytest.raises(RuntimeError, match="queue_position"):
        _upgrade_database(db_path, "20260527_0012")

    assert _read_revision(db_path) == "20260527_0011"


def test_dirty_batch_blocks_phase1_upgrade(tmp_path: Path) -> None:
    db_path = tmp_path / "phase1_dirty_batch.db"

    _upgrade_database(db_path, "20260527_0011")
    work_order_id = _insert_valid_work_order(db_path, order_number="WO-2026-9502")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO work_order_quantity_batches (
                work_order_id, quantity, type, parent_batch_id, is_active, current_stage, current_stage_status, is_partial, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (work_order_id, 0, "MAIN", None, 1, None, None, 0, "2026-05-25T00:00:00+00:00"),
        )
        connection.commit()

    with pytest.raises(RuntimeError, match="quantity > 0"):
        _upgrade_database(db_path, "20260527_0012")

    assert _read_revision(db_path) == "20260527_0011"


def test_dirty_stage_state_blocks_phase1_upgrade(tmp_path: Path) -> None:
    db_path = tmp_path / "phase1_dirty_stage.db"

    _upgrade_database(db_path, "20260527_0011")
    work_order_id = _insert_valid_work_order(db_path, order_number="WO-2026-9503")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO work_order_stage_states (
                work_order_id, stage, status, counted_quantity, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (work_order_id, "SURFACE_PREPARATION", "NOT_STARTED", 0, "2026-05-25T00:00:00+00:00", "2026-05-25T00:00:00+00:00"),
        )
        connection.commit()

    with pytest.raises(RuntimeError, match="counted_quantity"):
        _upgrade_database(db_path, "20260527_0012")

    assert _read_revision(db_path) == "20260527_0011"


def _insert_valid_work_order(db_path: Path, *, order_number: str, queue_position: int | None = None) -> int:
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
                None,
                0,
                None,
                "Customer",
                "RAL 9005",
                "Producer",
                "ENTERED",
                "RAL",
                None,
                "MAIN",
                queue_position,
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