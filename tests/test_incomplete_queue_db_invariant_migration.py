import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config


REPO_ROOT = Path(__file__).resolve().parents[1]
REVISION_BEFORE_INCOMPLETE_QUEUE_INVARIANT = "20260529_0017"
REVISION_INCOMPLETE_QUEUE_INVARIANT = "20260529_0018"


def test_clean_upgrade_applies_incomplete_queue_invariant(tmp_path: Path) -> None:
    db_path = tmp_path / "incomplete_queue_clean.db"

    _upgrade_database(db_path, REVISION_BEFORE_INCOMPLETE_QUEUE_INVARIANT)
    _insert_work_order(db_path, order_number="WO-2026-9900", status="ENTERED", is_incomplete_on_arrival=0)
    _insert_work_order(db_path, order_number="WO-2026-9901", status="INCOMPLETE", is_incomplete_on_arrival=1)

    _upgrade_database(db_path, REVISION_INCOMPLETE_QUEUE_INVARIANT)

    assert _read_revision(db_path) == REVISION_INCOMPLETE_QUEUE_INVARIANT


def test_incomplete_arrival_marker_blocks_upgrade_when_queued(tmp_path: Path) -> None:
    db_path = tmp_path / "incomplete_queue_flag_dirty.db"

    _upgrade_database(db_path, REVISION_BEFORE_INCOMPLETE_QUEUE_INVARIANT)
    _insert_work_order(
        db_path,
        order_number="WO-2026-9902",
        status="ENTERED",
        is_incomplete_on_arrival=1,
        production_type="MANUAL",
        queue_position=1,
    )

    with pytest.raises(RuntimeError, match="incomplete work orders must remain unplanned"):
        _upgrade_database(db_path, REVISION_INCOMPLETE_QUEUE_INVARIANT)

    assert _read_revision(db_path) == REVISION_BEFORE_INCOMPLETE_QUEUE_INVARIANT


def test_legacy_incomplete_status_blocks_upgrade_when_queued(tmp_path: Path) -> None:
    db_path = tmp_path / "incomplete_queue_status_dirty.db"

    _upgrade_database(db_path, REVISION_BEFORE_INCOMPLETE_QUEUE_INVARIANT)
    _insert_work_order(
        db_path,
        order_number="WO-2026-9903",
        status="INCOMPLETE",
        is_incomplete_on_arrival=0,
        production_type="MANUAL",
        queue_position=1,
    )

    with pytest.raises(RuntimeError, match="incomplete work orders must remain unplanned"):
        _upgrade_database(db_path, REVISION_INCOMPLETE_QUEUE_INVARIANT)

    assert _read_revision(db_path) == REVISION_BEFORE_INCOMPLETE_QUEUE_INVARIANT


def _insert_work_order(
    db_path: Path,
    *,
    order_number: str,
    status: str,
    is_incomplete_on_arrival: int,
    production_type: str | None = None,
    queue_position: int | None = None,
) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
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
                status,
                "RAL",
                production_type,
                "MAIN",
                queue_position,
                "2026-05-25",
                None,
                None,
                is_incomplete_on_arrival,
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