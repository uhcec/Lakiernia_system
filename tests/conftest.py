from typing import Annotated

import pytest
from fastapi import Header
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.config import get_settings
from app.database.base import Base
from app.database import models  # noqa: F401
from app.database.session import get_db_session
from app.main import create_app


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
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    Base.metadata.create_all(bind=engine)
    session = session_factory()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def test_client() -> TestClient:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    Base.metadata.create_all(bind=engine)

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
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
