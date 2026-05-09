from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.models.models import User
from app.schemas.user import UserCreate


def get_users_count(db: Session) -> int:
    return db.query(User).count()


def get_user_by_email(db: Session, email: str):
    """
    Pobiera użytkownika z bazy danych na podstawie adresu email.

    Args:
        db: Sesja bazy danych SQLAlchemy
        email: Adres email użytkownika

    Returns:
        Obiekt User lub None jeśli nie znaleziono
    """
    return db.query(User).filter(User.email == email).first()


def get_user_by_id(db: Session, user_id: int):
    """
    Pobiera użytkownika z bazy danych na podstawie ID.

    Args:
        db: Sesja bazy danych SQLAlchemy
        user_id: Identyfikator użytkownika

    Returns:
        Obiekt User lub None jeśli nie znaleziono
    """
    return db.query(User).filter(User.id == user_id).first()


def create_user(db: Session, user: UserCreate, is_admin: bool = False):
    """
    Tworzy nowego użytkownika w bazie danych.

    Args:
        db: Sesja bazy danych SQLAlchemy
        user: Schemat danych nowego użytkownika
        is_admin: Czy użytkownik ma mieć uprawnienia administratora

    Returns:
        Utworzony obiekt User
    """
    hashed_password = get_password_hash(user.password)
    db_user = User(
        email=user.email,
        hashed_password=hashed_password,
        full_name=user.full_name,
        is_admin=is_admin,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def is_user_active(user: User) -> bool:
    """
    Sprawdza czy użytkownik jest aktywny.

    Args:
        user: Obiekt użytkownika

    Returns:
        True jeśli użytkownik jest aktywny, False w przeciwnym razie
    """
    return user.is_active
