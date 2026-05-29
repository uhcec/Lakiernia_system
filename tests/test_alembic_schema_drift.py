import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.config import get_settings


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_alembic_check_passes_after_upgrade_head(tmp_path: Path) -> None:
    db_path = tmp_path / "local.db"
    config = _alembic_config()

    with _temporary_database_url(_sqlite_url(db_path)):
        command.upgrade(config, "head")
        command.check(config)

    columns = _work_order_columns(db_path)
    work_order_indexes = _table_indexes(db_path, "work_orders")
    quantity_batch_indexes = _table_indexes(db_path, "work_order_quantity_batches")
    audit_event_indexes = _table_indexes(db_path, "audit_events")

    assert "due_date" not in columns
    assert "ix_work_orders_queue_namespace" in work_order_indexes
    assert "uq_work_orders_queue_position" in work_order_indexes
    assert "uq_work_order_quantity_batches_one_active_per_work_order" in quantity_batch_indexes
    assert "ix_audit_events_event_type" in audit_event_indexes
    assert "ix_audit_events_work_order_id" in audit_event_indexes
    assert "ix_audit_events_created_at" in audit_event_indexes
    assert "ix_audit_events_id" in audit_event_indexes


def _alembic_config() -> Config:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    return config


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


def _work_order_columns(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute("PRAGMA table_info(work_orders)").fetchall()
    return {row[1] for row in rows}


def _table_indexes(db_path: Path, table_name: str) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(f"PRAGMA index_list({table_name})").fetchall()
    return {row[1] for row in rows}