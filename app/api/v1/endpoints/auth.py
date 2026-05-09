from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, decode_access_token, get_password_hash, verify_password
from app.crud.user import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    get_users_count,
    set_force_password_reset,
    update_user_password,
)
from app.db.session import get_db
from app.schemas.token import Token
from app.schemas.user import PasswordChangeRequest, SetPasswordRequest, UserCreate, UserResponse

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


@router.get("/registration-status", summary="Status rejestracji")
def registration_status():
    return {"enabled": settings.registration_enabled}


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Rejestracja nowego użytkownika",
)
def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """
    Tworzy nowe konto użytkownika w systemie.
    Pierwszy zarejestrowany użytkownik (id=1) automatycznie zostaje administratorem.
    """
    if not settings.registration_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Rejestracja nowych użytkowników jest wyłączona",
        )

    db_user = get_user_by_email(db, email=user_data.email)
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Użytkownik z tym adresem email już istnieje",
        )

    is_first_user = get_users_count(db) == 0
    user = create_user(db=db, user=user_data, is_admin=is_first_user)
    return user


@router.post(
    "/login",
    response_model=Token,
    summary="Logowanie użytkownika",
)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    """
    Uwierzytelnia użytkownika i zwraca token JWT.

    - Weryfikuje email i hasło
    - Generuje token JWT ważny przez 24 godziny
    """
    user = get_user_by_email(db, email=form_data.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nieprawidłowy email lub hasło",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Jeśli admin wymusił reset hasła — pomiń weryfikację i zwróć temp token
    if user.force_password_reset:
        temp_token = create_access_token(
            data={"sub": str(user.id), "password_reset": True},
            expires_delta=timedelta(minutes=15),
        )
        return {"password_reset_required": True, "temp_token": temp_token}

    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nieprawidłowy email lub hasło",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
):
    """
    Dependency (zależność) do pobierania aktualnie zalogowanego użytkownika
    na podstawie tokena JWT z nagłówka Authorization.
    """
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nieprawidłowy lub wygasły token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    email: str = payload.get("sub")
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nieprawidłowy token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = get_user_by_email(db, email=email)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Użytkownik nie istnieje",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_current_admin(current_user=Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Brak uprawnień administratora",
        )
    return current_user


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Informacje o zalogowanym użytkowniku",
)
def read_current_user(current_user=Depends(get_current_user)):
    return current_user


@router.post("/set-password", response_model=Token, summary="Ustaw nowe hasło (po wymuszonej zmianie)")
def set_password(data: SetPasswordRequest, db: Session = Depends(get_db)):
    payload = decode_access_token(data.temp_token)
    if not payload or not payload.get("password_reset"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nieprawidłowy lub wygasły token resetu")
    user_id = int(payload["sub"])
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Użytkownik nie istnieje")
    update_user_password(db, user_id, get_password_hash(data.new_password))
    set_force_password_reset(db, user_id, False)
    access_token = create_access_token(
        data={"sub": user.email},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/change-password", summary="Zmień hasło (zalogowany użytkownik)")
def change_password(
    data: PasswordChangeRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(data.old_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nieprawidłowe obecne hasło")
    update_user_password(db, current_user.id, get_password_hash(data.new_password))
    return {"message": "Hasło zmienione pomyślnie"}
