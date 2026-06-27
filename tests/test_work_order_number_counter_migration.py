import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_migration_backfills_work_order_number_counters(tmp_path: Path) -> None:
    db_path = tmp_path / "counter_backfill.db"

    _upgrade_database(db_path, "20260526_0010")
    _insert_work_order(db_path, order_number="WO-2025-0003")
    _insert_work_order(db_path, order_number="WO-2026-0007")
    _insert_work_order(db_path, order_number="WO-2026-0012")
    _insert_work_order(db_path, order_number="WO-LEGACY-XYZ")

    _upgrade_database(db_path, "20260527_0011")

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT year, last_value FROM work_order_number_counters ORDER BY year ASC"
        ).fetchall()

    assert rows == [(2025, 3), (2026, 12)]


def _insert_work_order(db_path: Path, *, order_number: str) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO work_orders (
                order_number,
                title,
                total_quantity,
                completed_quantity,
                current_active_batch_id,
                parent_order_id,
                is_correction,
                description,
                customer_name,
                ral_code,
                paint_producer,
                status,
                coating_type,
                production_type,
                queue_namespace,
                queue_position,
                received_date,
                planned_pickup_date,
                total_area_m2,
                is_incomplete_on_arrival,
                profiles_quantity,
                profiles_to_count,
                accessories_quantity,
                accessories_to_count,
                notes,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_number,
                order_number,
                1,
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
