"""Guardrail: business constants that are stated in the docs, pinned to their implementation.

This is the *fast* half of the repo's self-check loop (the *slow* half is the weekly `/doc-audit`).
Each test pins a value the documentation commits to. If code changes one of these without updating the
owning doc, this test fails in CI — catching exactly the doc<->code drift class that hit us before
(the paint threshold documented as 70 but coded as 100; NA24 A1, NA25). When a value here legitimately
changes, update **the code, its owning doc, and this registry together**.

Each assertion cites the doc that states the value so the two loops stay linked.
"""

from app.auth.service import MAX_PASSWORD_BYTES
from app.core.config import Settings
from app.work_orders.schemas import calculate_predicted_paint_quantity_kg


def test_paint_demand_threshold_is_100_m2_with_4_and_6_divisors() -> None:
    # Doc: WORKFLOW.md "Paint Inventory And Consumption" + FACTORY_DOMAIN_MODEL.md §4 / DOC_COHERENCE_AUDIT A1.
    # Below 100 m² -> /4; at or above 100 m² -> /6; rounded to whole kg (ROUND_HALF_UP).
    assert calculate_predicted_paint_quantity_kg(None) is None
    assert calculate_predicted_paint_quantity_kg(96.0) == 24.0  # 96/4, below threshold
    assert calculate_predicted_paint_quantity_kg(99.0) == 25.0  # 99/4 = 24.75 -> 25 (still below 100)
    assert calculate_predicted_paint_quantity_kg(100.0) == 17.0  # 100/6 = 16.67 -> 17 (threshold reached)
    assert calculate_predicted_paint_quantity_kg(120.0) == 20.0  # 120/6, above threshold


def test_packing_default_slots_is_2() -> None:
    # Doc: WORKFLOW.md "Packing capacity / slots" (NA22) — configurable N, default 2.
    assert Settings.model_fields["packing_max_concurrent_slots"].default == 2


def test_jwt_expiry_default_is_12_hours() -> None:
    # Doc: IMMEDIATE_NEXT_ACTIONS.md NA6 — default ~one operator shift (12h).
    assert Settings.model_fields["jwt_expiry_minutes"].default == 12 * 60


def test_bcrypt_password_byte_limit_is_72() -> None:
    # Doc: IMMEDIATE_NEXT_ACTIONS.md NA10 — bcrypt's 72-byte limit handled deterministically.
    assert MAX_PASSWORD_BYTES == 72


def test_insecure_jwt_secret_default_rejected_outside_development() -> None:
    # Doc: README.md / NA12 — the dev-only default secret must be refused outside a local APP_ENV.
    from app.core.config import INSECURE_DEFAULT_JWT_SECRET

    import pytest

    with pytest.raises(ValueError):
        Settings(app_env="production", jwt_secret=INSECURE_DEFAULT_JWT_SECRET)
    # A real secret is accepted in production.
    assert Settings(app_env="production", jwt_secret="a-real-secret").jwt_secret == "a-real-secret"
