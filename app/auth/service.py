from datetime import UTC, datetime, timedelta

import bcrypt
from jose import jwt
from sqlalchemy.orm import Session

from app.auth.models import User
from app.core.config import get_settings

# bcrypt only considers the first 72 bytes of a password. bcrypt 5.x raises on longer
# input (older versions truncated silently); we guard explicitly so the limit is handled
# deterministically (a clear error on hashing, a clean auth failure on verification)
# instead of leaking a raw ValueError as a 500. (NA10)
MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    if len(password.encode()) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must not exceed {MAX_PASSWORD_BYTES} bytes.")
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    if len(plain.encode()) > MAX_PASSWORD_BYTES:
        return False
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user: User) -> str:
    # Deliberately real wall-clock time, NOT the dev virtual clock: a JWT's lifetime is a real-session
    # concern and the ``exp`` claim is validated by the JWT library against real time. Issuing tokens on
    # simulated factory time would make them born-expired during a workflow simulation run.
    now = datetime.now(UTC)
    payload = {
        "sub": user.login,
        "station_id": user.station_id,
        "is_admin": user.is_admin,
        "iat": now,
        "exp": now + timedelta(minutes=get_settings().jwt_expiry_minutes),
    }
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")


def authenticate_user(db: Session, login: str, password: str) -> User | None:
    user = db.query(User).filter(User.login == login).first()
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except Exception:
        return {}
