from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.v1.endpoints.auth import get_current_user
from app.crud.subscription import (
    create_subscription,
    delete_subscription,
    get_subscription,
    get_subscriptions,
    update_subscription,
)
from app.db.session import get_db
from app.models.models import User
from app.schemas.subscription import (
    SubscriptionCreate,
    SubscriptionResponse,
    SubscriptionUpdate,
)

router = APIRouter()


@router.post(
    "/",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Utwórz nowy abonament",
)
def create_new_subscription(
    subscription: SubscriptionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Tworzy nowy abonament/subskrypcję cyklicznego wydatku.
    Przykład: Netflix 29.99zł co 30 dni od 2025-01-01 przez 24 miesiące.
    """
    db_subscription = create_subscription(
        db=db,
        user_id=current_user.id,
        name=subscription.name,
        amount=subscription.amount,
        frequency_days=subscription.frequency_days,
        billing_day_of_month=subscription.billing_day_of_month,
        start_date=subscription.start_date,
        end_date=subscription.end_date,
        next_billing_date=subscription.next_billing_date,
        remaining_installments=subscription.remaining_installments,
        category_id=subscription.category_id,
    )
    return db_subscription


@router.get(
    "/",
    response_model=List[SubscriptionResponse],
    summary="Pobierz listę abonamentów",
)
def list_subscriptions(
    skip: int = 0,
    limit: int = 100,
    active_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Zwraca listę abonamentów użytkownika.
    Opcjonalnie filtruje tylko aktywne (nie wygasłe).
    """
    subscriptions = get_subscriptions(
        db,
        user_id=current_user.id,
        skip=skip,
        limit=limit,
        active_only=active_only,
    )
    return subscriptions


@router.get(
    "/{subscription_id}",
    response_model=SubscriptionResponse,
    summary="Pobierz abonament po ID",
)
def read_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Zwraca szczegóły konkretnego abonamentu użytkownika.
    """
    db_subscription = get_subscription(
        db, subscription_id=subscription_id, user_id=current_user.id
    )
    if not db_subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Abonament nie został znaleziony",
        )
    return db_subscription


@router.put(
    "/{subscription_id}",
    response_model=SubscriptionResponse,
    summary="Zaktualizuj abonament",
)
def update_existing_subscription(
    subscription_id: int,
    subscription_update: SubscriptionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Aktualizuje dane abonamentu użytkownika.
    Można zmienić np. kwotę, datę kolejnej płatności lub liczbę rat.
    """
    update_data = subscription_update.model_dump(exclude_unset=True)

    updated = update_subscription(
        db,
        subscription_id=subscription_id,
        user_id=current_user.id,
        **update_data,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Abonament nie został znaleziony",
        )
    return updated


@router.delete(
    "/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Usuń abonament",
)
def delete_existing_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Usuwa abonament użytkownika. Wygenerowane wcześniej wydatki pozostają w bazie.
    """
    deleted = delete_subscription(
        db, subscription_id=subscription_id, user_id=current_user.id
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Abonament nie został znaleziony",
        )
    return None
