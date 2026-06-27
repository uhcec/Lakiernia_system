from __future__ import annotations

import os
import re
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

from app.core.config import get_settings


REVISION_0006 = "20260525_0006"
REVISION_0007 = "20260525_0007"
BROKEN_COLUMNS = ("parent_order_id", "is_correction")
WORK_ORDERS_TABLE = "work_orders"


@dataclass(slots=True)
class RepairResult:
    action: str
    message: str
    backup_path: Path | None = None


@dataclass(slots=True)
class WorkOrdersState:
    alembic_version: str | None
    columns: dict[str, sqlite3.Row]
    foreign_keys: list[sqlite3.Row]


@dataclass(slots=True)
class ReferenceSchema:
    create_table_sql: str
    create_index_sql: list[str]
    columns: list[str]


def repair_local_sqlite_migration_0007(database_url: str | None = None, repo_root: Path | None = None) -> RepairResult:
    repo_root = repo_root or Path(__file__).resolve().parents[1]
    database_url = database_url or get_settings().database_url
    database_path = _resolve_local_sqlite_path(database_url, repo_root)

    if database_path is None:
        return RepairResult(
            action="skipped",
            message="Skipping repair: DATABASE_URL is not a local SQLite local.db file.",
        )

    if get_settings().app_env.lower() != "development":
        return RepairResult(
            action="skipped",
            message="Skipping repair: APP_ENV is not development.",
        )

    if not database_path.exists():
        return RepairResult(
            action="noop",
            message=f"No repair needed: {database_path.name} does not exist yet.",
        )

    state = _read_work_orders_state(database_path)
    if not _is_partial_0007(state):
        return RepairResult(
            action="noop",
            message=(
                "No repair needed: work_orders does not show a partially applied 0007 migration "
                f"while alembic_version is {state.alembic_version or 'unset'}."
            ),
        )

    backup_path = _create_backup(database_path)
    if _matches_completed_0007_schema(state):
        _stamp_revision(database_path, REVISION_0007)
        return RepairResult(
            action="stamped",
            backup_path=backup_path,
            message=(
                "Backed up local.db and stamped alembic_version to 20260525_0007 because the "
                "work_orders schema already matches the completed 0007 migration."
            ),
        )

    reference_schema = _build_reference_schema(repo_root)
    _rebuild_work_orders_to_reference_schema(database_path, reference_schema)
    return RepairResult(
        action="repaired",
        backup_path=backup_path,
        message=(
            "Backed up local.db and rebuilt work_orders back to the clean 20260525_0006 schema. "
            "You can now run `python -m alembic upgrade head`."
        ),
    )


def main() -> int:
    result = repair_local_sqlite_migration_0007()
    print(result.message)
    if result.backup_path is not None:
        print(f"Backup created: {result.backup_path}")
    return 0


def _resolve_local_sqlite_path(database_url: str, repo_root: Path) -> Path | None:
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite"):
        return None

    database_name = url.database
    if not database_name or database_name == ":memory:":
        return None

    database_path = Path(database_name)
    if not database_path.is_absolute():
        database_path = (repo_root / database_path).resolve()

    if database_path.name != "local.db":
        return None

    return database_path


def _read_work_orders_state(database_path: Path) -> WorkOrdersState:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        alembic_version = _read_alembic_version(connection)
        columns = {
            row["name"]: row
            for row in connection.execute(f"PRAGMA table_info({WORK_ORDERS_TABLE})").fetchall()
        }
        foreign_keys = connection.execute(f"PRAGMA foreign_key_list({WORK_ORDERS_TABLE})").fetchall()
    return WorkOrdersState(alembic_version=alembic_version, columns=columns, foreign_keys=foreign_keys)


def _read_alembic_version(connection: sqlite3.Connection) -> str | None:
    table_exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'alembic_version'"
    ).fetchone()
    if table_exists is None:
        return None

    row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    return row[0] if row is not None else None


def _is_partial_0007(state: WorkOrdersState) -> bool:
    if state.alembic_version != REVISION_0006:
        return False
    return any(column in state.columns for column in BROKEN_COLUMNS)


def _matches_completed_0007_schema(state: WorkOrdersState) -> bool:
    if not all(column in state.columns for column in BROKEN_COLUMNS):
        return False

    parent_order = state.columns["parent_order_id"]
    is_correction = state.columns["is_correction"]
    has_self_fk = any(
        foreign_key["table"] == WORK_ORDERS_TABLE
        and foreign_key["from"] == "parent_order_id"
        and foreign_key["to"] == "id"
        and foreign_key["on_delete"].upper() == "SET NULL"
        for foreign_key in state.foreign_keys
    )

    return (
        parent_order["notnull"] == 0
        and parent_order["dflt_value"] is None
        and is_correction["notnull"] == 1
        and is_correction["dflt_value"] is None
        and has_self_fk
    )


def _create_backup(database_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = database_path.with_name(f"{database_path.name}.backup_{timestamp}")
    shutil.copy2(database_path, backup_path)
    return backup_path


def _build_reference_schema(repo_root: Path) -> ReferenceSchema:
    temp_dir = Path(tempfile.mkdtemp(prefix="repair_sqlite_migration_0007_"))
    try:
        reference_db_path = temp_dir / "local.db"
        config = Config(str(repo_root / "alembic.ini"))
        config.set_main_option("script_location", str(repo_root / "alembic"))

        with _temporary_database_url(_sqlite_url(reference_db_path)):
            command.upgrade(config, REVISION_0006)

        with sqlite3.connect(reference_db_path) as connection:
            table_row = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
                (WORK_ORDERS_TABLE,),
            ).fetchone()
            if table_row is None or table_row[0] is None:
                raise RuntimeError("Could not build a reference work_orders schema for revision 0006.")

            index_rows = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'index' AND tbl_name = ? AND sql IS NOT NULL ORDER BY name",
                (WORK_ORDERS_TABLE,),
            ).fetchall()
            columns = [
                row[1]
                for row in connection.execute(f"PRAGMA table_info({WORK_ORDERS_TABLE})").fetchall()
            ]
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return ReferenceSchema(
        create_table_sql=table_row[0],
        create_index_sql=[row[0] for row in index_rows if row[0]],
        columns=columns,
    )


def _rebuild_work_orders_to_reference_schema(database_path: Path, reference_schema: ReferenceSchema) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        current_columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({WORK_ORDERS_TABLE})").fetchall()
        }
        missing_columns = [column for column in reference_schema.columns if column not in current_columns]
        if missing_columns:
            raise RuntimeError(
                "Cannot repair local.db automatically because work_orders is missing expected 0006 columns: "
                + ", ".join(missing_columns)
            )

        repair_table_sql = _rename_create_table_sql(reference_schema.create_table_sql, WORK_ORDERS_TABLE, f"{WORK_ORDERS_TABLE}__repair")
        column_list = ", ".join(_quote_identifier(column) for column in reference_schema.columns)

        connection.execute("PRAGMA foreign_keys = OFF")
        try:
            connection.execute("BEGIN")
            connection.execute(f"DROP TABLE IF EXISTS {WORK_ORDERS_TABLE}__repair")
            connection.execute(repair_table_sql)
            connection.execute(
                f"INSERT INTO {WORK_ORDERS_TABLE}__repair ({column_list}) "
                f"SELECT {column_list} FROM {WORK_ORDERS_TABLE}"
            )
            connection.execute(f"DROP TABLE {WORK_ORDERS_TABLE}")
            connection.execute(f"ALTER TABLE {WORK_ORDERS_TABLE}__repair RENAME TO {WORK_ORDERS_TABLE}")
            for create_index_sql in reference_schema.create_index_sql:
                connection.execute(create_index_sql)
            foreign_key_violations = connection.execute("PRAGMA foreign_key_check").fetchall()
            if foreign_key_violations:
                raise RuntimeError("Foreign key validation failed after repairing local.db.")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.execute("PRAGMA foreign_keys = ON")


def _stamp_revision(database_path: Path, revision: str) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute("UPDATE alembic_version SET version_num = ?", (revision,))
        connection.commit()


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


def _sqlite_url(database_path: Path) -> str:
    return f"sqlite:///{database_path.resolve().as_posix()}"


def _rename_create_table_sql(create_sql: str, source_table: str, target_table: str) -> str:
    pattern = rf'CREATE TABLE\s+"?{re.escape(source_table)}"?'
    return re.sub(pattern, f'CREATE TABLE {target_table}', create_sql, count=1)


def _quote_identifier(identifier: str) -> str:
    escaped_identifier = identifier.replace('"', '""')
    return f'"{escaped_identifier}"'


if __name__ == "__main__":
    raise SystemExit(main())
