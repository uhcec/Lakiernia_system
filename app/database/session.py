from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def _apply_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    """Make concurrent SQLite access wait instead of erroring (NA9).

    ``busy_timeout`` makes a blocked writer wait (up to 5s) for the lock rather than
    immediately raising ``database is locked``; WAL lets readers and a writer proceed
    concurrently. WAL is a no-op for in-memory databases and is harmless there.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA busy_timeout = 5000")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = NORMAL")
    finally:
        cursor.close()


@lru_cache
def get_engine():
    settings = get_settings()
    is_sqlite = settings.database_url.startswith("sqlite")
    engine = create_engine(
        settings.database_url,
        future=True,
        connect_args={"check_same_thread": False} if is_sqlite else {},
    )
    if is_sqlite:
        event.listen(engine, "connect", _apply_sqlite_pragmas)
    return engine


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, class_=Session)


def get_db_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
