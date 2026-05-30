from datetime import date
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import Expense, PaymentCard
from app.schemas.card import CardMonthStats, CardStatsResponse, PaymentCardCreate, PaymentCardUpdate

POLISH_MONTHS = [
    "", "Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec",
    "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień",
]


def get_cards(db: Session, user_id: int) -> List[PaymentCard]:
    return db.query(PaymentCard).filter(PaymentCard.user_id == user_id).order_by(PaymentCard.name).all()


def get_card(db: Session, card_id: int, user_id: int) -> Optional[PaymentCard]:
    return db.query(PaymentCard).filter(PaymentCard.id == card_id, PaymentCard.user_id == user_id).first()


def create_card(db: Session, user_id: int, data: PaymentCardCreate) -> PaymentCard:
    card = PaymentCard(user_id=user_id, **data.model_dump())
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


def update_card(db: Session, card_id: int, user_id: int, data: PaymentCardUpdate) -> Optional[PaymentCard]:
    card = get_card(db, card_id, user_id)
    if not card:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(card, field, value)
    db.commit()
    db.refresh(card)
    return card


def delete_card(db: Session, card_id: int, user_id: int) -> bool:
    card = get_card(db, card_id, user_id)
    if not card:
        return False
    # odepnij wydatki od karty przed usunięciem
    db.query(Expense).filter(Expense.card_id == card_id, Expense.user_id == user_id).update({"card_id": None})
    db.delete(card)
    db.commit()
    return True


def _compute_is_free(card: PaymentCard, count: int, amount: float) -> tuple[bool, Optional[bool], Optional[bool]]:
    """Zwraca (is_free, met_transactions, met_amount)."""
    has_tx_rule = card.min_transactions is not None
    has_amt_rule = card.min_amount is not None

    if not has_tx_rule and not has_amt_rule:
        return True, None, None

    met_tx = (count >= card.min_transactions) if has_tx_rule else None
    met_amt = (amount >= card.min_amount) if has_amt_rule else None

    if has_tx_rule and has_amt_rule:
        if card.rules_require_all:
            is_free = met_tx and met_amt
        else:
            is_free = met_tx or met_amt
    elif has_tx_rule:
        is_free = met_tx
    else:
        is_free = met_amt

    return bool(is_free), met_tx, met_amt


def get_cards_stats(db: Session, user_id: int, num_months: int = 4) -> List[CardStatsResponse]:
    cards = get_cards(db, user_id)
    today = date.today()

    # Wygeneruj ostatnie num_months miesięcy (od najstarszego do najnowszego)
    months_list = []
    year, month = today.year, today.month
    for _ in range(num_months):
        months_list.append((year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    months_list.reverse()

    result = []
    for card in cards:
        month_stats = []
        for y, m in months_list:
            start = date(y, m, 1)
            if m == 12:
                end = date(y + 1, 1, 1)
            else:
                end = date(y, m + 1, 1)

            row = (
                db.query(
                    func.count(Expense.id).label("cnt"),
                    func.coalesce(func.sum(Expense.amount), 0).label("total"),
                )
                .filter(
                    Expense.card_id == card.id,
                    Expense.user_id == user_id,
                    Expense.date >= start,
                    Expense.date < end,
                )
                .one()
            )
            cnt, total = row.cnt, float(row.total)
            is_free, met_tx, met_amt = _compute_is_free(card, cnt, total)

            month_stats.append(CardMonthStats(
                year=y,
                month=m,
                label=f"{POLISH_MONTHS[m]} {y}",
                transaction_count=cnt,
                total_amount=round(total, 2),
                met_transactions=met_tx,
                met_amount=met_amt,
                is_free=is_free,
            ))

        result.append(CardStatsResponse(
            id=card.id,
            name=card.name,
            last_six_digits=card.last_six_digits,
            min_transactions=card.min_transactions,
            min_amount=card.min_amount,
            rules_require_all=card.rules_require_all,
            months=month_stats,
        ))

    return result


def get_card_expenses(db: Session, card_id: int, user_id: int, year: int, month: int) -> List[Expense]:
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return (
        db.query(Expense)
        .filter(
            Expense.card_id == card_id,
            Expense.user_id == user_id,
            Expense.date >= start,
            Expense.date < end,
        )
        .order_by(Expense.date.desc())
        .all()
    )
