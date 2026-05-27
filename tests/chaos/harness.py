from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import models  # noqa: F401
from app.database.base import Base
from app.database.session import get_db_session
from app.main import create_app


ALLOWED_CHAOS_STATUS_CODES = {200, 201, 204, 409, 422}


@dataclass(slots=True)
class ChaosEvent:
    actor: str
    method: str
    path: str
    status_code: int
    request_json: Any | None
    response_json: Any | None
    response_text: str | None


class LoggedApiClient:
    def __init__(self, actor: str, client: TestClient, event_log: list[ChaosEvent], event_lock: Lock) -> None:
        self.actor = actor
        self._client = client
        self._event_log = event_log
        self._event_lock = event_lock

    def request(self, method: str, path: str, **kwargs: Any):
        response = self._client.request(method, path, **kwargs)
        request_json = kwargs.get("json")
        try:
            response_json = response.json()
        except Exception:
            response_json = None

        with self._event_lock:
            self._event_log.append(
                ChaosEvent(
                    actor=self.actor,
                    method=method.upper(),
                    path=path,
                    status_code=response.status_code,
                    request_json=request_json,
                    response_json=response_json,
                    response_text=None if response_json is not None else response.text,
                )
            )
        return response

    def get(self, path: str, **kwargs: Any):
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any):
        return self.request("POST", path, **kwargs)

    def patch(self, path: str, **kwargs: Any):
        return self.request("PATCH", path, **kwargs)


class ChaosEnvironment:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.engine = create_engine(
            f"sqlite:///{database_path}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, class_=Session)
        Base.metadata.create_all(bind=self.engine)

        self.app = create_app()

        def override_get_db_session():
            session = self.session_factory()
            try:
                yield session
            finally:
                session.close()

        self.app.dependency_overrides[get_db_session] = override_get_db_session
        self._event_log: list[ChaosEvent] = []
        self._event_lock = Lock()
        self._clients: list[TestClient] = []

    @property
    def event_log(self) -> list[ChaosEvent]:
        return list(self._event_log)

    def create_actor_client(self, actor: str) -> LoggedApiClient:
        client = TestClient(self.app)
        self._clients.append(client)
        return LoggedApiClient(actor, client, self._event_log, self._event_lock)

    def create_session(self) -> Session:
        return self.session_factory()

    def close(self) -> None:
        for client in self._clients:
            client.close()
        self.app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()
        if self.database_path.exists():
            self.database_path.unlink()
