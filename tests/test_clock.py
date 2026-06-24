"""The virtual clock (``app.shared.clock``) and its dev-only control endpoint.

Pins the two guarantees that keep it safe: in normal/production use it is exactly real UTC time and
cannot be frozen, while in development the workflow simulation can freeze and advance it.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.shared import clock


@pytest.fixture(autouse=True)
def _reset_virtual_clock():
    """No test may leak a frozen clock into the rest of the suite."""
    clock.set_virtual_now(None)
    yield
    clock.set_virtual_now(None)


def test_now_is_real_utc_when_not_frozen() -> None:
    before = datetime.now(UTC)
    value = clock.now()
    after = datetime.now(UTC)

    assert value.tzinfo is not None
    assert before <= value <= after
    assert clock.virtual_now() is None


def test_set_virtual_now_freezes_now_and_naive_local() -> None:
    frozen = datetime(2026, 6, 22, 7, 30, tzinfo=UTC)
    clock.set_virtual_now(frozen)

    assert clock.now() == frozen
    assert clock.virtual_now() == frozen
    # Hour-of-day logic (planner shift hours) reads naive wall-clock time.
    assert clock.now_naive_local() == frozen.replace(tzinfo=None)
    assert clock.now_naive_local().tzinfo is None


def test_naive_input_is_treated_as_utc() -> None:
    clock.set_virtual_now(datetime(2026, 6, 22, 7, 0))  # naive
    assert clock.now() == datetime(2026, 6, 22, 7, 0, tzinfo=UTC)


def test_clear_returns_to_real_time() -> None:
    clock.set_virtual_now(datetime(2026, 1, 1, tzinfo=UTC))
    clock.set_virtual_now(None)
    assert clock.virtual_now() is None
    assert abs((clock.now() - datetime.now(UTC)).total_seconds()) < 5


def test_set_virtual_now_refused_outside_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "a-secure-production-secret-value-please")
    get_settings.cache_clear()

    with pytest.raises(RuntimeError):
        clock.set_virtual_now(datetime(2026, 6, 22, tzinfo=UTC))

    get_settings.cache_clear()


def test_dev_clock_endpoint_round_trip(test_client: TestClient) -> None:
    # Mounted only in local/development environments (the test settings default).
    assert test_client.get("/dev/clock").json()["virtual_now"] is None

    set_response = test_client.put("/dev/clock", json={"now": "2026-06-22T07:00:00Z"})
    assert set_response.status_code == 200
    assert set_response.json()["virtual_now"] == "2026-06-22T07:00:00Z"
    assert set_response.json()["now"] == "2026-06-22T07:00:00Z"

    assert test_client.get("/dev/clock").json()["virtual_now"] == "2026-06-22T07:00:00Z"

    clear_response = test_client.delete("/dev/clock")
    assert clear_response.status_code == 200
    assert clear_response.json()["virtual_now"] is None
