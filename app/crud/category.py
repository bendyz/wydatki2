from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.models import Category


def get_category(db: Session, category_id: int, user_id: int):
    """
    Pobiera kategorię należącą do konkretnego użytkownika.

    Args:
        db: Sesja bazy danych SQLAlchemy
        category_id: ID kategorii
        user_id: ID właściciela

    Returns:
        Obiekt Category lub None
    """
    return (
        db.query(Category)
        .filter(Category.id == category_id, Category.user_id == user_id)
        .first()
    )


def get_categories(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 100,
    include_global: bool = True,
) -> List[Category]:
    """
    Pobiera listę kategorii użytkownika.
    Opcjonalnie dołącza kategorie globalne (bez user_id).

    Args:
        db: Sesja bazy danych SQLAlchemy
        user_id: ID właściciela
        skip: Ilość rekordów do pominięcia (paginacja)
        limit: Maksymalna ilość rekordów
        include_global: Czy dołączyć kategorie globalne

    Returns:
        Lista obiektów Category
    """
    query = db.query(Category).filter(
        (Category.user_id == user_id) | (Category.user_id.is_(None))
        if include_global
        else Category.user_id == user_id
    )

    return query.offset(skip).limit(limit).all()


def create_category(db: Session, name: str, user_id: int) -> Optional[Category]:
    """
    Tworzy nową kategorię dla użytkownika.
    Zwraca None jeśli kategoria o tej nazwie już istnieje dla tego użytkownika.
    """
    existing = (
        db.query(Category)
        .filter(Category.name == name, Category.user_id == user_id)
        .first()
    )
    if existing:
        return None
    db_category = Category(name=name, user_id=user_id)
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category


def update_category(
    db: Session, category_id: int, user_id: int, name: str
) -> Optional[Category]:
    """
    Aktualizuje nazwę kategorii użytkownika.

    Args:
        db: Sesja bazy danych SQLAlchemy
        category_id: ID kategorii do aktualizacji
        user_id: ID właściciela
        name: Nowa nazwa kategorii

    Returns:
        Zaktualizowany obiekt Category lub None jeśli nie znaleziono
    """
    db_category = get_category(db, category_id=category_id, user_id=user_id)
    if not db_category:
        return None

    db_category.name = name
    db.commit()
    db.refresh(db_category)
    return db_category


def delete_category(db: Session, category_id: int, user_id: int) -> bool:
    """
    Usuwa kategorię użytkownika.

    Args:
        db: Sesja bazy danych SQLAlchemy
        category_id: ID kategorii do usunięcia
        user_id: ID właściciela

    Returns:
        True jeśli usunięto, False jeśli nie znaleziono
    """
    db_category = get_category(db, category_id=category_id, user_id=user_id)
    if not db_category:
        return False

    db.delete(db_category)
    db.commit()
    return True
