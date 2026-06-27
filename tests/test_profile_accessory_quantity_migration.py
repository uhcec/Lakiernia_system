import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_profile_accessory_quantity_migration_marks_invalid_known_pairs_to_count(tmp_path: Path) -> None:
    db_path = tmp_path / "profile_accessory_quantities.db"

    _upgrade_database(db_path, "20260531_0023")
    _insert_work_order(
        db_path,
        order_number="WO-2026-9800",
        total_quantity=10,
        profiles_quantity=10,
        profiles_to_count=0,
        accessories_quantity=10,
        accessories_to_count=0,
    )

    _upgrade_database(db_path, "20260531_0024")

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT profiles_quantity, profiles_to_count, accessories_quantity, accessories_to_count
            FROM work_orders
            WHERE order_number = ?
            """,
            ("WO-2026-9800",),
        ).fetchone()
        connection.execute(
            _insert_work_order_sql(),
            _work_order_params(
                order_number="WO-2026-9801",
                total_quantity=10,
                profiles_quantity=4,
                profiles_to_count=0,
                accessories_quantity=6,
                accessories_to_count=0,
            ),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                _insert_work_order_sql(),
                _work_order_params(
                    order_number="WO-2026-9802",
                    total_quantity=10,
                    profiles_quantity=5,
                    profiles_to_count=0,
                    accessories_quantity=10,
                    accessories_to_count=0,
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                _insert_work_order_sql(),
                _work_order_params(
                    order_number="WO-2026-9803",
                    total_quantity=10,
                    profiles_quantity=11,
                    profiles_to_count=0,
                    accessories_quantity=None,
                    accessories_to_count=1,
                ),
            )

    assert row == (None, 1, None, 1)


def _insert_work_order(
    db_path: Path,
    *,
    order_number: str,
    total_quantity: int,
    profiles_quantity: int | None,
    profiles_to_count: int,
    accessories_quantity: int | None,
    accessories_to_count: int,
) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            _insert_work_order_sql(),
            _work_order_params(
                order_number=order_number,
                total_quantity=total_quantity,
                profiles_quantity=profiles_quantity,
                profiles_to_count=profiles_to_count,
                accessories_quantity=accessories_quantity,
                accessories_to_count=accessories_to_count,
            ),
        )
        connection.commit()


def _insert_work_order_sql() -> str:
    return """
        INSERT INTO work_orders (
            order_number,
            title,
            total_quantity,
            completed_quantity,
            current_active_batch_id,
            parent_order_id,
            is_correction,
            correction_reason_category,
            correction_reason_note,
            description,
            customer_name,
            ral_code,
            paint_producer,
            status,
            coating_type,
            work_order_kind,
            is_ocynk,
            production_type,
            queue_namespace,
            queue_position,
            received_date,
            planned_pickup_date,
            released_to_client_at,
            total_area_m2,
            is_incomplete_on_arrival,
            profiles_quantity,
            profiles_to_count,
            accessories_quantity,
            accessories_to_count,
            notes,
            created_at,
            updated_at
        ) VALUES (
            :order_number,
            :title,
            :total_quantity,
            0,
            NULL,
            NULL,
            0,
            NULL,
            NULL,
            NULL,
            'Customer',
            'RAL 9005',
            'Producer',
            'ENTERED',
            'RAL',
            'STANDARD',
            0,
            NULL,
            'MAIN',
            NULL,
            '2026-05-25',
            NULL,
            NULL,
            NULL,
            0,
            :profiles_quantity,
            :profiles_to_count,
            :accessories_quantity,
            :accessories_to_count,
            NULL,
            '2026-05-25T00:00:00+00:00',
            '2026-05-25T00:00:00+00:00'
        )
        """


def _work_order_params(
    *,
    order_number: str,
    total_quantity: int,
    profiles_quantity: int | None,
    profiles_to_count: int,
    accessories_quantity: int | None,
    accessories_to_count: int,
) -> dict[str, object]:
    return {
        "order_number": order_number,
        "title": order_number,
        "total_quantity": total_quantity,
        "profiles_quantity": profiles_quantity,
        "profiles_to_count": profiles_to_count,
        "accessories_quantity": accessories_quantity,
        "accessories_to_count": accessories_to_count,
    }


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
