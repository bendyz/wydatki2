from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.v1.endpoints.auth import get_current_user
from app.crud.category import (
    create_category,
    delete_category,
    get_categories,
    get_category,
    update_category,
)
from app.db.session import get_db
from app.models.models import User
from app.schemas.category import (
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
)

router = APIRouter()


@router.post(
    "/",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Utwórz nową kategorię",
)
def create_new_category(
    category: CategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Tworzy nową kategorię wydatków dla aktualnie zalogowanego użytkownika.
    """
    db_category = create_category(db=db, name=category.name, user_id=current_user.id)
    if db_category is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Kategoria o tej nazwie już istnieje",
        )
    return db_category


@router.get(
    "/",
    response_model=List[CategoryResponse],
    summary="Pobierz listę kategorii",
)
def list_categories(
    skip: int = 0,
    limit: int = 100,
    include_global: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Zwraca listę kategorii dostępnych dla użytkownika.
    Domyślnie zawiera zarówno własne kategorie jak i globalne (bez user_id).
    """
    categories = get_categories(
        db,
        user_id=current_user.id,
        skip=skip,
        limit=limit,
        include_global=include_global,
    )
    return categories


@router.get(
    "/{category_id}",
    response_model=CategoryResponse,
    summary="Pobierz kategorię po ID",
)
def read_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Zwraca szczegóły konkretnej kategorii użytkownika.
    """
    db_category = get_category(db, category_id=category_id, user_id=current_user.id)
    if not db_category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kategoria nie została znaleziona",
        )
    return db_category


@router.put(
    "/{category_id}",
    response_model=CategoryResponse,
    summary="Zaktualizuj kategorię",
)
def update_existing_category(
    category_id: int,
    category_update: CategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Aktualizuje nazwę istniejącej kategorii użytkownika.
    """
    if category_update.name is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pole 'name' jest wymagane do aktualizacji",
        )

    updated = update_category(
        db,
        category_id=category_id,
        user_id=current_user.id,
        name=category_update.name,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kategoria nie została znaleziona",
        )
    return updated


@router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Usuń kategorię",
)
def delete_existing_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Usuwa kategorię użytkownika.
    """
    deleted = delete_category(db, category_id=category_id, user_id=current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kategoria nie została znaleziona",
        )
    return None
