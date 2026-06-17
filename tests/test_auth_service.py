from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt

from app.auth.models import User
from app.auth.service import (
    MAX_PASSWORD_BYTES,
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.config import get_settings


def _user() -> User:
    return User(id=1, login="biuro", hashed_password="", station_id="OFFICE", is_admin=False)


# NA6 — JWT expiry


def test_access_token_includes_expiry_claim() -> None:
    token = create_access_token(_user())
    payload = decode_token(token)
    assert payload["sub"] == "biuro"
    assert "exp" in payload and "iat" in payload

    expected = datetime.now(UTC) + timedelta(minutes=get_settings().jwt_expiry_minutes)
    actual = datetime.fromtimestamp(payload["exp"], tz=UTC)
    assert abs((actual - expected).total_seconds()) < 60


def test_decode_token_rejects_expired_token() -> None:
    expired = jwt.encode(
        {"sub": "biuro", "exp": datetime.now(UTC) - timedelta(minutes=1)},
        get_settings().jwt_secret,
        algorithm="HS256",
    )
    # decode_token swallows the ExpiredSignatureError and yields no claims, so
    # get_current_user sees no "sub" and returns 401.
    assert decode_token(expired) == {}


# NA10 — bcrypt 72-byte limit handled deterministically


def test_hash_password_rejects_over_long_password() -> None:
    with pytest.raises(ValueError):
        hash_password("a" * (MAX_PASSWORD_BYTES + 1))


def test_verify_password_rejects_over_long_password_without_truncation() -> None:
    hashed = hash_password("a" * MAX_PASSWORD_BYTES)
    # An over-long attempt must not match via silent truncation to 72 bytes.
    assert verify_password("a" * (MAX_PASSWORD_BYTES + 8), hashed) is False


def test_password_round_trip_at_limit() -> None:
    hashed = hash_password("a" * MAX_PASSWORD_BYTES)
    assert verify_password("a" * MAX_PASSWORD_BYTES, hashed) is True
    assert verify_password("wrong", hashed) is False
