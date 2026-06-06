import bcrypt
from jose import jwt
from sqlalchemy.orm import Session

from app.auth.models import User
from app.core.config import get_settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user: User) -> str:
    payload = {
        "sub": user.login,
        "station_id": user.station_id,
        "is_admin": user.is_admin,
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
