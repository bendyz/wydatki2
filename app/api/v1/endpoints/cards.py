from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1.endpoints.auth import get_current_user
from app.crud.card import (
    create_card,
    delete_card,
    get_card,
    get_card_expenses,
    get_cards,
    get_cards_stats,
    update_card,
)
from app.db.session import get_db
from app.models.models import User
from app.schemas.card import (
    CardStatsResponse,
    PaymentCardCreate,
    PaymentCardResponse,
    PaymentCardUpdate,
)
from app.schemas.expense import ExpenseResponse

router = APIRouter()


@router.get("/", response_model=List[PaymentCardResponse], summary="Lista kart płatniczych")
def list_cards(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return get_cards(db, current_user.id)


@router.post("/", response_model=PaymentCardResponse, status_code=status.HTTP_201_CREATED, summary="Dodaj kartę")
def create_new_card(
    data: PaymentCardCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return create_card(db, current_user.id, data)


@router.get("/stats", response_model=List[CardStatsResponse], summary="Statystyki kart (ostatnie miesiące)")
def cards_stats(
    months: int = Query(4, ge=1, le=12),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_cards_stats(db, current_user.id, num_months=months)


@router.get("/{card_id}", response_model=PaymentCardResponse, summary="Pobierz kartę")
def read_card(card_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    card = get_card(db, card_id, current_user.id)
    if not card:
        raise HTTPException(status_code=404, detail="Karta nie istnieje")
    return card


@router.put("/{card_id}", response_model=PaymentCardResponse, summary="Zaktualizuj kartę")
def update_existing_card(
    card_id: int,
    data: PaymentCardUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    card = update_card(db, card_id, current_user.id, data)
    if not card:
        raise HTTPException(status_code=404, detail="Karta nie istnieje")
    return card


@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Usuń kartę")
def delete_existing_card(
    card_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not delete_card(db, card_id, current_user.id):
        raise HTTPException(status_code=404, detail="Karta nie istnieje")


@router.get(
    "/{card_id}/expenses",
    response_model=List[ExpenseResponse],
    summary="Wydatki karty w danym miesiącu",
)
def card_expenses(
    card_id: int,
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    card = get_card(db, card_id, current_user.id)
    if not card:
        raise HTTPException(status_code=404, detail="Karta nie istnieje")
    return get_card_expenses(db, card_id, current_user.id, year, month)
