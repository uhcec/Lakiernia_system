from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.service import decode_token
from app.database.session import get_db_session

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db_session)],
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Nie jesteś zalogowany")
    payload = decode_token(credentials.credentials)
    login: str | None = payload.get("sub")
    if not login:
        raise HTTPException(status_code=401, detail="Nieprawidłowy token")
    user = db.query(User).filter(User.login == login).first()
    if user is None:
        raise HTTPException(status_code=401, detail="Użytkownik nie istnieje")
    return user
