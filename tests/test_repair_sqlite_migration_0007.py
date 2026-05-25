import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.config import get_settings
from scripts.repair_sqlite_migration_0007 import REVISION_0006, repair_local_sqlite_migration_0007


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_clean_0006_db_is_noop(tmp_path: Path):
    db_path = tmp_path / "local.db"
    _upgrade_database(db_path, REVISION_0006)
    initial_columns = _work_order_columns(db_path)

    result = repair_local_sqlite_migration_0007(database_url=_sqlite_url(db_path), repo_root=REPO_ROOT)

    assert result.action == "noop"
    assert list(tmp_path.glob("local.db.backup_*")) == []
    assert _work_order_columns(db_path) == initial_columns


def test_partial_0007_db_is_repaired_with_backup(tmp_path: Path):
    db_path = tmp_path / "local.db"
    _upgrade_database(db_path, REVISION_0006)
    _insert_work_order(db_path, order_number="WO-REPAIR-1")
    _apply_partial_0007_columns(db_path)

    result = repair_local_sqlite_migration_0007(database_url=_sqlite_url(db_path), repo_root=REPO_ROOT)

    assert result.action == "repaired"
    assert result.backup_path is not None
    assert result.backup_path.exists()
    assert _read_revision(db_path) == REVISION_0006
    assert "parent_order_id" not in _work_order_columns(db_path)
    assert "is_correction" not in _work_order_columns(db_path)
    assert _count_work_orders(db_path) == 1


def test_upgrade_head_succeeds_after_repair(tmp_path: Path):
    db_path = tmp_path / "local.db"
    _upgrade_database(db_path, REVISION_0006)
    _apply_partial_0007_columns(db_path)

    repair_result = repair_local_sqlite_migration_0007(database_url=_sqlite_url(db_path), repo_root=REPO_ROOT)
    assert repair_result.action == "repaired"

    _upgrade_database(db_path, "head")

    assert _read_revision(db_path) == "20260525_0008"
    columns = _work_order_columns(db_path)
    assert "parent_order_id" in columns
    assert "is_correction" in columns


def _apply_partial_0007_columns(db_path: Path) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute("ALTER TABLE work_orders ADD COLUMN parent_order_id INTEGER")
        connection.execute("ALTER TABLE work_orders ADD COLUMN is_correction BOOLEAN NOT NULL DEFAULT 0")
        connection.commit()


def _count_work_orders(db_path: Path) -> int:
    with sqlite3.connect(db_path) as connection:
        row = connection.execute("SELECT COUNT(*) FROM work_orders").fetchone()
    return row[0]


def _insert_work_order(db_path: Path, order_number: str) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO work_orders (
                order_number,
                title,
                description,
                customer_name,
                status,
                coating_type,
                production_type,
                queue_position,
                due_date,
                notes,
                created_at,
                updated_at,
                total_quantity,
                completed_quantity,
                current_active_batch_id,
                ral_code,
                paint_producer,
                received_date,
                planned_pickup_date,
                total_area_m2,
                profiles_quantity,
                profiles_to_count,
                accessories_quantity,
                accessories_to_count,
                is_incomplete_on_arrival
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_number,
                "Repair Test",
                None,
                "Customer",
                "ENTERED",
                "RAL",
                None,
                None,
                None,
                None,
                "2026-05-25T00:00:00+00:00",
                "2026-05-25T00:00:00+00:00",
                1,
                0,
                None,
                "RAL-9005",
                "Producer",
                "2026-05-25",
                None,
                None,
                None,
                1,
                None,
                1,
                0,
            ),
        )
        connection.commit()


def _read_revision(db_path: Path) -> str:
    with sqlite3.connect(db_path) as connection:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    return row[0]


def _upgrade_database(db_path: Path, revision: str) -> None:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    with _temporary_database_url(_sqlite_url(db_path)):
        command.upgrade(config, revision)


@contextmanager
def _temporary_database_url(database_url: str):
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    get_settings.cache_clear()
    try:
        yield
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url
        get_settings.cache_clear()


def _sqlite_url(db_path: Path) -> str:
    return f"sqlite:///{db_path.resolve().as_posix()}"


def _work_order_columns(db_path: Path) -> list[str]:
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute("PRAGMA table_info(work_orders)").fetchall()
    return [row[1] for row in rows]