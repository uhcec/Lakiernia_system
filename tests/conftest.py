from typing import Annotated

import pytest
from fastapi import Header
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.config import get_settings
from app.database.base import Base
from app.database import models  # noqa: F401
from app.database.session import _apply_sqlite_pragmas, get_db_session
from app.main import create_app


def _make_test_engine():
    """In-memory engine that mirrors production connection setup.

    Attaching ``_apply_sqlite_pragmas`` keeps tests honest: most importantly it turns on
    ``PRAGMA foreign_keys`` so ``ON DELETE CASCADE``/``SET NULL`` are enforced exactly as in
    production, instead of silently leaving orphan rows.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    event.listen(engine, "connect", _apply_sqlite_pragmas)
    return engine


def _mock_admin_user() -> User:
    return User(id=1, login="admin", hashed_password="", station_id="OFFICE", is_admin=True)


def _current_user_from_station_header(
    x_station_id: Annotated[str | None, Header(alias="X-Station-Id")] = None,
) -> User:
    """Authenticate tests as the station named in ``X-Station-Id``.

    Authorization now derives from the authenticated user (NA1), not the header. To keep the existing
    per-request station semantics in the suite, this override logs in as the station's (non-admin)
    user when a header is supplied, and as the admin user otherwise (admin bypasses authz). The raw
    header value is kept as ``station_id`` so invalid values still surface as a 400 via
    ``parse_station_id`` in ``get_station_context``.
    """

    if x_station_id is None or not x_station_id.strip():
        return _mock_admin_user()
    raw_station = x_station_id.strip()
    return User(id=2, login=raw_station.lower(), hashed_password="", station_id=raw_station, is_admin=False)


@pytest.fixture(autouse=True)
def attachment_storage_env(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WORK_ORDER_ATTACHMENTS_DIR", str(tmp_path / "attachments"))
    monkeypatch.setenv("WORK_ORDER_ATTACHMENT_MAX_SIZE_BYTES", str(1024 * 1024))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def db_session() -> Session:
    engine = _make_test_engine()
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    Base.metadata.create_all(bind=engine)
    session = session_factory()

    try:
        yield session
    finally:
        session.close()
        # No drop_all: the in-memory DB lives only on this StaticPool connection, so dispose()
        # discards it entirely. (drop_all would also fail under foreign_keys=ON, because dropping
        # work_orders fires the self-referential parent_order_id SET NULL, violating the
        # correction_requires_parent CHECK on any correction children the test created.)
        engine.dispose()


@pytest.fixture
def test_client() -> TestClient:
    engine = _make_test_engine()
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    Base.metadata.create_all(bind=engine)

    # The auth override fabricates users with fixed ids (1 = admin, 2 = a station operator) but never
    # persists them. Under foreign_keys=ON those ids must exist, because audited actions write rows
    # (e.g. stage_transition_events.user_id) that reference users.id. Seed the two ids the override uses.
    seed_session = session_factory()
    seed_session.add_all(
        [
            User(id=1, login="admin", hashed_password="", station_id="OFFICE", is_admin=True),
            User(id=2, login="station", hashed_password="", station_id="OFFICE", is_admin=False),
        ]
    )
    seed_session.commit()
    seed_session.close()

    def override_get_db_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_current_user] = _current_user_from_station_header

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    # See db_session teardown: dispose() drops the in-memory DB; drop_all is redundant and would
    # fail under foreign_keys=ON.
    engine.dispose()
