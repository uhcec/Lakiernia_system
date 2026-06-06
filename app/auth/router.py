from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.schemas import LoginRequest, LoginResponse
from app.auth.service import authenticate_user, create_access_token
from app.database.session import get_db_session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(
    request: LoginRequest,
    db: Annotated[Session, Depends(get_db_session)],
) -> LoginResponse:
    user = authenticate_user(db, request.login, request.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Nieprawidłowy login lub hasło")
    return LoginResponse(
        access_token=create_access_token(user),
        station_id=user.station_id,
        is_admin=user.is_admin,
    )
