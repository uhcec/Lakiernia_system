from datetime import datetime, UTC

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.config import get_settings
from app.database.base import Base
from app.database import models  # noqa: F401  (registers all models)
from app.database.session import get_db_session
from app.main import create_app
from app.process.enums import ProcessStage, StageStatus
from app.process.models import StageTransitionEvent, WorkOrderStageState
from app.shared.enums import StationId
from app.work_orders.models import WorkOrder


# NA-tracking — the append-only stage-transition log (StageTransitionEvent) is the durable
# analytics backbone: it records every meaningful stage transition with the moment it occurred,
# and throughput is attributed from it (with a stage-state updated_at fallback for historical rows).


@pytest.fixture
def admin_client_and_sessions(tmp_path, monkeypatch):
    """An admin-authenticated client plus a session factory on the SAME in-memory engine.

    Admin bypasses station-action authorization, so a single identity can drive the whole flow;
    the session factory lets the test read back the stage-transition log written by those calls.
    """
    monkeypatch.setenv("WORK_ORDER_ATTACHMENTS_DIR", str(tmp_path / "attachments"))
    get_settings.cache_clear()

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

    def override_current_user() -> User:
        return User(id=1, login="admin", hashed_password="", station_id="OFFICE", is_admin=True)

    app = create_app()
    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_current_user] = override_current_user

    with TestClient(app) as client:
        yield client, session_factory

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()


def _create_payload(title: str, **overrides: object) -> dict:
    payload = {
        "title": title,
        "coating_type": "RAL",
        "total_quantity": 100,
        "customer_name": "ACME",
        "ral_code": "RAL 7016",
        "paint_code": "P-7016",
        "paint_producer": "AkzoNobel",
        "received_date": "2026-05-25",
        "total_area_m2": 24.0,
        "profiles_to_count": True,
        "accessories_to_count": True,
    }
    payload.update(overrides)
    return payload


def _complete_manual_ral_order(client: TestClient, work_order_id: int, quantity: int = 100) -> None:
    assert client.post(
        f"/manager/work-orders/{work_order_id}/plan",
        json={"production_type": "MANUAL", "queue_position": 1},
    ).status_code == 200
    assert client.post(f"/process/work-orders/{work_order_id}/stages/SURFACE_PREPARATION/start").status_code == 200
    assert client.post(
        f"/process/work-orders/{work_order_id}/stages/SURFACE_PREPARATION/finish",
        json={"counted_quantity": quantity},
    ).status_code == 200
    assert client.post(f"/process/work-orders/{work_order_id}/stages/PRODUCTION/start").status_code == 200
    assert client.post(f"/process/work-orders/{work_order_id}/stages/PRODUCTION/finish").status_code == 200
    assert client.post(f"/process/work-orders/{work_order_id}/stages/PACKING/start").status_code == 200
    assert client.post(
        f"/process/work-orders/{work_order_id}/packing/complete",
        json={"counted_quantity": quantity, "ok_quantity": quantity, "correction_quantity": 0},
    ).status_code == 200


def test_stage_transitions_are_logged_with_timestamp_station_and_user(admin_client_and_sessions) -> None:
    client, session_factory = admin_client_and_sessions
    created = client.post("/work-orders", json=_create_payload("Logged manual RAL")).json()

    _complete_manual_ral_order(client, created["id"])

    with session_factory() as session:
        events = session.execute(
            select(StageTransitionEvent)
            .where(StageTransitionEvent.work_order_id == created["id"])
            .order_by(StageTransitionEvent.id)
        ).scalars().all()

    pairs = [(event.stage, event.status) for event in events]
    # Manual RAL path: each manual stage start/finish is logged, ending with PACKING completion.
    assert (ProcessStage.SURFACE_PREPARATION, StageStatus.IN_PROGRESS) in pairs
    assert (ProcessStage.SURFACE_PREPARATION, StageStatus.DONE) in pairs
    assert (ProcessStage.PRODUCTION, StageStatus.IN_PROGRESS) in pairs
    assert (ProcessStage.PRODUCTION, StageStatus.DONE) in pairs
    assert (ProcessStage.PACKING, StageStatus.DONE) in pairs

    # Every row carries the analytics essentials: a durable timestamp, the station, and the user id.
    for event in events:
        assert event.occurred_at is not None
        assert event.station_id == StationId.OFFICE
        assert event.user_id == 1

    packing_done = next(e for e in events if e.stage == ProcessStage.PACKING and e.status == StageStatus.DONE)
    assert packing_done.counted_quantity == 100


def test_throughput_attributes_from_the_transition_log(admin_client_and_sessions) -> None:
    client, _ = admin_client_and_sessions
    created = client.post("/work-orders", json=_create_payload("Throughput from log", total_area_m2=18.0)).json()

    _complete_manual_ral_order(client, created["id"])

    response = client.get(
        "/manager/stats/throughput",
        params={"date_from": "2000-01-01", "date_to": "2100-01-01"},
    )
    assert response.status_code == 200
    totals = response.json()["totals"]
    # The PACKING->DONE event drives attribution; the order's m² shows up in the totals.
    assert totals["m2_total"] == 18.0
    assert totals["m2_manual"] == 18.0


def test_throughput_falls_back_to_stage_state_when_no_event_exists(admin_client_and_sessions) -> None:
    # Orders packed before the transition log existed have no event; COALESCE keeps counting them
    # via the PACKING stage state's updated_at so historical throughput is preserved.
    client, session_factory = admin_client_and_sessions

    with session_factory() as session:
        work_order = WorkOrder(
            order_number="WO-LEGACY-1",
            title="Legacy packed order",
            total_quantity=10,
            completed_quantity=10,
            customer_name="ACME",
            ral_code="RAL 9005",
            paint_producer="AkzoNobel",
            received_date=datetime(2026, 3, 1, tzinfo=UTC).date(),
            total_area_m2=12.0,
        )
        session.add(work_order)
        session.flush()
        session.add(
            WorkOrderStageState(
                work_order_id=work_order.id,
                stage=ProcessStage.PACKING,
                status=StageStatus.DONE,
                updated_at=datetime(2026, 3, 15, 9, 0, tzinfo=UTC),
            )
        )
        session.commit()

    response = client.get(
        "/manager/stats/throughput",
        params={"date_from": "2000-01-01", "date_to": "2100-01-01"},
    )
    assert response.status_code == 200
    totals = response.json()["totals"]
    assert totals["m2_total"] == 12.0
