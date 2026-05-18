from calendar import monthrange
from datetime import date, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.models import Expense, Subscription


def _next_monthly_date(current_date: date, day_of_month: int) -> date:
    """Zwraca datę tego samego dnia w następnym miesiącu."""
    month = current_date.month + 1
    year = current_date.year
    if month > 12:
        month = 1
        year += 1
    max_day = monthrange(year, month)[1]
    return date(year, month, min(day_of_month, max_day))


def get_subscription(
    db: Session, subscription_id: int, user_id: int
) -> Optional[Subscription]:
    """
    Pobiera pojedynczy abonament należący do użytkownika.
    """
    return (
        db.query(Subscription)
        .filter(Subscription.id == subscription_id, Subscription.user_id == user_id)
        .first()
    )


def get_subscriptions(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 100,
    active_only: bool = False,
) -> List[Subscription]:
    """
    Pobiera listę abonamentów użytkownika.
    """
    query = db.query(Subscription).filter(Subscription.user_id == user_id)

    if active_only:
        today = date.today()
        query = query.filter(
            (Subscription.end_date.is_(None)) | (Subscription.end_date >= today)
        )

    return query.offset(skip).limit(limit).all()


def get_due_subscriptions(db: Session) -> List[Subscription]:
    """
    Pobiera wszystkie abonamenty, których next_billing_date <= dzisiaj.
    Używane przez scheduler do generowania wydatków.
    """
    today = date.today()
    return (
        db.query(Subscription)
        .filter(
            Subscription.next_billing_date <= today,
            (Subscription.end_date.is_(None)) | (Subscription.end_date >= today),
            (Subscription.remaining_installments.is_(None))
            | (Subscription.remaining_installments > 0),
        )
        .all()
    )


def create_subscription(
    db: Session,
    user_id: int,
    name: str,
    amount: float,
    start_date: date,
    frequency_days: Optional[int] = None,
    billing_day_of_month: Optional[int] = None,
    end_date: Optional[date] = None,
    next_billing_date: Optional[date] = None,
    remaining_installments: Optional[int] = None,
    category_id: Optional[int] = None,
) -> Subscription:
    """
    Tworzy nowy abonament/subskrypcję.
    Jeśli nie podano next_billing_date, ustawia start_date.
    """
    if next_billing_date is None:
        next_billing_date = start_date
    if frequency_days is None:
        frequency_days = 30  # placeholder; scheduling uses billing_day_of_month

    db_subscription = Subscription(
        user_id=user_id,
        name=name,
        amount=amount,
        frequency_days=frequency_days,
        billing_day_of_month=billing_day_of_month,
        start_date=start_date,
        end_date=end_date,
        next_billing_date=next_billing_date,
        remaining_installments=remaining_installments,
        category_id=category_id,
    )
    db.add(db_subscription)
    db.commit()
    db.refresh(db_subscription)
    return db_subscription


def update_subscription(
    db: Session,
    subscription_id: int,
    user_id: int,
    **kwargs,
) -> Optional[Subscription]:
    """
    Aktualizuje abonament użytkownika.
    Przekaż tylko pola, które chcesz zmienić jako keyword arguments.
    """
    db_subscription = get_subscription(db, subscription_id, user_id)
    if not db_subscription:
        return None

    allowed_fields = {
        "name",
        "amount",
        "frequency_days",
        "billing_day_of_month",
        "start_date",
        "end_date",
        "next_billing_date",
        "remaining_installments",
        "category_id",
    }

    # Pola, które mogą być jawnie wyzerowane (None = usuń wartość)
    nullable_fields = {"end_date", "category_id", "remaining_installments",
                       "billing_day_of_month"}

    for key, value in kwargs.items():
        if key not in allowed_fields:
            continue
        # frequency_days NOT NULL w DB — nigdy nie zerujemy
        if key == "frequency_days" and value is None:
            continue
        if value is None and key not in nullable_fields:
            continue
        setattr(db_subscription, key, value)

    db.commit()
    db.refresh(db_subscription)
    return db_subscription


def delete_subscription(db: Session, subscription_id: int, user_id: int) -> bool:
    """
    Usuwa abonament użytkownika.
    """
    db_subscription = get_subscription(db, subscription_id, user_id)
    if not db_subscription:
        return False

    db.delete(db_subscription)
    db.commit()
    return True


def process_subscription_billing(
    db: Session, subscription: Subscription
) -> Optional[Expense]:
    """
    Przetwarza pojedynczy abonament – tworzy wydatek i aktualizuje datę kolejnej płatności.
    Zwraca utworzony wydatek lub None jeśli abonament wygasł.
    """
    today = date.today()

    # Sprawdź czy abonament nie wygasł
    if subscription.end_date and subscription.end_date < today:
        return None

    if (
        subscription.remaining_installments is not None
        and subscription.remaining_installments <= 0
    ):
        return None

    # Utwórz wydatek na podstawie abonamentu
    db_expense = Expense(
        user_id=subscription.user_id,
        amount=subscription.amount,
        description=subscription.name,
        date=subscription.next_billing_date,
        category_id=subscription.category_id,
        metadata_ai='{"source": "subscription", "subscription_id": %d}'
        % subscription.id,
    )
    db.add(db_expense)
    db.commit()
    db.refresh(db_expense)

    # Aktualizuj datę kolejnej płatności
    if subscription.billing_day_of_month:
        subscription.next_billing_date = _next_monthly_date(
            subscription.next_billing_date, subscription.billing_day_of_month
        )
    else:
        subscription.next_billing_date = subscription.next_billing_date + timedelta(
            days=subscription.frequency_days
        )

    # Zmniejsz licznik pozostałych płatności
    if subscription.remaining_installments is not None:
        subscription.remaining_installments -= 1

    db.commit()
    db.refresh(subscription)

    return db_expense
