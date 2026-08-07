import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.v1.endpoints.auth import get_current_user
from app.crud.expense import (
    create_expense,
    delete_expense,
    get_expense,
    get_expenses,
    update_expense,
)
from app.db.session import get_db
from app.models.models import Category, PaymentCard, User
from app.schemas.expense import ExpenseCreate, ExpenseResponse, ExpenseUpdate

router = APIRouter()


def _assert_category_allowed(db: Session, user_id: int, category_id: Optional[int]) -> None:
    """Kategoria musi należeć do użytkownika lub być globalna (user_id IS NULL)."""
    if category_id is None:
        return
    cat = db.query(Category).filter(Category.id == category_id).first()
    if cat is None or (cat.user_id is not None and cat.user_id != user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Nieprawidłowa kategoria: {category_id}",
        )


def _assert_card_allowed(db: Session, user_id: int, card_id: Optional[int]) -> None:
    """Karta płatnicza musi należeć do użytkownika."""
    if card_id is None:
        return
    card = (
        db.query(PaymentCard)
        .filter(PaymentCard.id == card_id, PaymentCard.user_id == user_id)
        .first()
    )
    if card is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Nieprawidłowa karta płatnicza: {card_id}",
        )


def _validate_expense_refs(db: Session, user_id: int, category_id, card_id, items) -> None:
    _assert_category_allowed(db, user_id, category_id)
    _assert_card_allowed(db, user_id, card_id)
    for item in items or []:
        _assert_category_allowed(db, user_id, item.get("category_id"))


@router.post(
    "/",
    response_model=ExpenseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Utwórz nowy wydatek z pozycjami",
)
def create_new_expense(
    expense: ExpenseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Tworzy nowy wydatek wraz z pozycjami (items).
    Każda pozycja może mieć własną kategorię (category_id).
    """
    items = [item.model_dump() for item in expense.items]
    _validate_expense_refs(db, current_user.id, expense.category_id, expense.card_id, items)
    db_expense = create_expense(
        db=db,
        user_id=current_user.id,
        amount=expense.amount,
        description=expense.description,
        expense_date=expense.date,
        category_id=expense.category_id,
        card_id=expense.card_id,
        items=items,
    )
    return db_expense


@router.get(
    "/",
    response_model=List[ExpenseResponse],
    summary="Pobierz listę wydatków",
)
def list_expenses(
    skip: int = 0,
    limit: int = 100,
    category_id: Optional[int] = None,
    item_category_id: Optional[int] = None,
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
    search: Optional[str] = None,
    search_items: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    expenses = get_expenses(
        db,
        user_id=current_user.id,
        skip=skip,
        limit=limit,
        category_id=category_id,
        item_category_id=item_category_id,
        start_date=start_date,
        end_date=end_date,
        search=search,
        search_items=search_items,
    )
    return expenses


@router.get(
    "/{expense_id}",
    response_model=ExpenseResponse,
    summary="Pobierz wydatek po ID",
)
def read_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Zwraca szczegóły konkretnego wydatku użytkownika wraz z pozycjami.
    """
    db_expense = get_expense(db, expense_id=expense_id, user_id=current_user.id)
    if not db_expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wydatek nie został znaleziony",
        )
    return db_expense


@router.put(
    "/{expense_id}",
    response_model=ExpenseResponse,
    summary="Zaktualizuj wydatek",
)
def update_existing_expense(
    expense_id: int,
    expense_update: ExpenseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Aktualizuje wydatek użytkownika.
    Jeśli przekazano nowe pozycje (items), stare zostaną usunięte i zastąpione nowymi.
    """
    update_data = expense_update.model_dump(exclude_unset=True)

    items = update_data.pop("items", None)
    items_list = items if items is not None else None

    _validate_expense_refs(
        db,
        current_user.id,
        update_data.get("category_id"),
        update_data.get("card_id"),
        items_list,
    )

    updated = update_expense(
        db,
        expense_id=expense_id,
        user_id=current_user.id,
        amount=update_data.get("amount"),
        description=update_data.get("description"),
        expense_date=update_data.get("date"),
        category_id=update_data.get("category_id"),
        card_id=update_data.get("card_id"),
        items=items_list,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wydatek nie został znaleziony",
        )
    return updated


@router.delete(
    "/{expense_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Usuń wydatek",
)
def delete_existing_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Usuwa wydatek użytkownika wraz ze wszystkimi jego pozycjami.
    """
    deleted = delete_expense(db, expense_id=expense_id, user_id=current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wydatek nie został znaleziony",
        )
    return None
