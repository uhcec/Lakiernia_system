import pytest
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
    app.dependency_overrides[get_current_user] = _mock_admin_user

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()