import csv
from collections import defaultdict
from datetime import date, timedelta
from io import StringIO
from typing import List, Optional

from sqlalchemy import extract, func
from sqlalchemy.orm import Session, joinedload

from app.models.models import Category, Expense, ExpenseItem


def expense_category_contributions(expense: Expense) -> List[dict]:
    """
    Rozbija pojedynczy wydatek na wkłady do poszczególnych kategorii.

    Paragon może obejmować pozycje z różnych kategorii (np. w Lidlu serki i bułki
    → Jedzenie, proszek → Dom), dlatego kwota wydatku rozkłada się na kilka
    kategorii. Reguły:
      - są pozycje → sumujemy je per kategoria pozycji,
      - rozbieżność między sumą pozycji a kwotą wydatku (rabaty, zaokrąglenia)
        → kategoria nagłówka wydatku,
      - brak pozycji → cała kwota na kategorię nagłówka.

    To JEDYNE miejsce z tą regułą — korzysta z niej zarówno podsumowanie
    kategorii, jak i lista wydatków po rozwinięciu kategorii, żeby kwoty w obu
    widokach zawsze się zgadzały.

    Returns:
        Lista dictów: category_id, category_name, amount, items
    """
    contributions: dict = {}

    def add(cid, cname, amount, item=None):
        entry = contributions.setdefault(
            cid,
            {"category_id": cid, "category_name": cname, "amount": 0.0, "items": []},
        )
        entry["category_name"] = cname
        entry["amount"] += amount
        if item is not None:
            entry["items"].append(item)

    if expense.items:
        for item in expense.items:
            quantity = item.quantity if item.quantity is not None else 1.0
            add(
                item.category_id,
                item.category.name if item.category else None,
                round(item.price * quantity, 4),
                {
                    "name": item.name,
                    "quantity": quantity,
                    "price": item.price,
                    "total": round(item.price * quantity, 2),
                },
            )
        items_sum = sum(
            i.price * (i.quantity if i.quantity is not None else 1.0)
            for i in expense.items
        )
        discrepancy = expense.amount - items_sum
        if abs(discrepancy) > 0.005:
            add(
                expense.category_id,
                expense.category.name if expense.category else None,
                discrepancy,
            )
    else:
        add(
            expense.category_id,
            expense.category.name if expense.category else None,
            expense.amount,
        )

    return list(contributions.values())


def get_category_expenses(
    db: Session,
    user_id: int,
    category_id: Optional[int],
    start_date: date,
    end_date: date,
    limit: int = 500,
) -> List[dict]:
    """
    Zwraca wydatki składające się na daną kategorię w okresie — wraz z kwotą
    faktycznie przypisaną do tej kategorii.

    Paragon z pozycjami w kilku kategoriach pojawi się przy każdej z nich, ale
    za każdym razem tylko z częścią kwoty odpowiadającą jej pozycjom.
    `category_id=None` oznacza „Bez kategorii".
    """
    expenses = (
        db.query(Expense)
        .options(
            joinedload(Expense.items).joinedload(ExpenseItem.category),
            joinedload(Expense.category),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.date >= start_date,
            Expense.date <= end_date,
        )
        .order_by(Expense.date.desc(), Expense.id.desc())
        .all()
    )

    results = []
    for expense in expenses:
        for contribution in expense_category_contributions(expense):
            if contribution["category_id"] != category_id:
                continue
            amount = round(contribution["amount"], 2)
            results.append(
                {
                    "expense_id": expense.id,
                    "date": expense.date,
                    "description": expense.description,
                    "amount": amount,
                    "full_amount": round(expense.amount, 2),
                    "is_partial": abs(contribution["amount"] - expense.amount) > 0.005,
                    "items": contribution["items"],
                }
            )
            break

    return results[:limit]


def get_stats(
    db: Session,
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> dict:
    """
    Pobiera statystyki wydatków użytkownika za określony okres.
    """
    if not start_date:
        start_date = date.today().replace(day=1)
    if not end_date:
        end_date = date.today()

    # Base query
    base_query = db.query(Expense).filter(
        Expense.user_id == user_id,
        Expense.date >= start_date,
        Expense.date <= end_date,
    )

    # Totals
    total_amount = (
        db.query(func.sum(Expense.amount))
        .filter(
            Expense.user_id == user_id,
            Expense.date >= start_date,
            Expense.date <= end_date,
        )
        .scalar()
        or 0.0
    )

    total_count = base_query.count()

    # Days in period
    days_in_period = max((end_date - start_date).days + 1, 1)
    average_per_day = total_amount / days_in_period if days_in_period > 0 else 0.0
    average_per_expense = total_amount / total_count if total_count > 0 else 0.0

    # Monthly summary
    monthly_data = (
        db.query(
            extract("year", Expense.date).label("year"),
            extract("month", Expense.date).label("month"),
            func.sum(Expense.amount).label("total"),
            func.count(Expense.id).label("count"),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.date >= start_date,
            Expense.date <= end_date,
        )
        .group_by(extract("year", Expense.date), extract("month", Expense.date))
        .order_by(extract("year", Expense.date), extract("month", Expense.date))
        .all()
    )

    month_names = {
        1: "Styczeń",
        2: "Luty",
        3: "Marzec",
        4: "Kwiecień",
        5: "Maj",
        6: "Czerwiec",
        7: "Lipiec",
        8: "Sierpień",
        9: "Wrzesień",
        10: "Październik",
        11: "Listopad",
        12: "Grudzień",
    }

    monthly_summary = [
        {
            "year": int(m.year),
            "month": int(m.month),
            "month_name": month_names.get(int(m.month), ""),
            "total_amount": float(m.total),
            "expense_count": int(m.count),
        }
        for m in monthly_data
    ]

    # Category summary — item-aware:
    # jeśli wydatek ma pozycje, liczymy po kategoriach pozycji;
    # jeśli nie ma, bierzemy kategorię nagłówka wydatku.
    expenses_for_cats = (
        base_query
        .options(
            joinedload(Expense.items).joinedload(ExpenseItem.category),
            joinedload(Expense.category),
        )
        .all()
    )

    cat_data = defaultdict(lambda: {"name": None, "total": 0.0, "expense_ids": set()})

    for expense in expenses_for_cats:
        for contribution in expense_category_contributions(expense):
            cid = contribution["category_id"]
            cat_data[cid]["name"] = contribution["category_name"]
            cat_data[cid]["total"] += contribution["amount"]
            cat_data[cid]["expense_ids"].add(expense.id)

    category_summary = []
    for cid, data in sorted(cat_data.items(), key=lambda x: -x[1]["total"]):
        percentage = (data["total"] / total_amount * 100) if total_amount > 0 else 0.0
        category_summary.append(
            {
                "category_id": cid,
                "category_name": data["name"] or "Bez kategorii",
                "total_amount": round(data["total"], 2),
                "percentage": round(percentage, 2),
                "expense_count": len(data["expense_ids"]),
            }
        )

    # Daily expenses for line chart
    daily_data = (
        db.query(Expense.date, func.sum(Expense.amount).label("total"))
        .filter(
            Expense.user_id == user_id,
            Expense.date >= start_date,
            Expense.date <= end_date,
        )
        .group_by(Expense.date)
        .order_by(Expense.date)
        .all()
    )

    daily_expenses = [{"date": d.date, "amount": float(d.total)} for d in daily_data]

    return {
        "period_start": start_date,
        "period_end": end_date,
        "total_amount": total_amount,
        "total_count": total_count,
        "average_per_day": round(average_per_day, 2),
        "average_per_expense": round(average_per_expense, 2),
        "monthly_summary": monthly_summary,
        "category_summary": category_summary,
        "daily_expenses": daily_expenses,
    }


def export_expenses_to_csv(
    db: Session,
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    category_id: Optional[int] = None,
) -> str:
    """
    Eksportuje wydatki użytkownika do formatu CSV.
    Zwraca zawartość CSV jako string.
    """
    query = db.query(Expense).filter(Expense.user_id == user_id)

    if start_date:
        query = query.filter(Expense.date >= start_date)
    if end_date:
        query = query.filter(Expense.date <= end_date)
    if category_id:
        query = query.filter(Expense.category_id == category_id)

    expenses = query.order_by(Expense.date.desc()).all()

    output = StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow(
        [
            "ID",
            "Data",
            "Opis",
            "Kwota",
            "Kategoria",
            "Pozycje",
            "Źródło AI",
            "Ścieżka do zdjęcia",
        ]
    )

    for expense in expenses:
        # Format items as string
        items_str = "; ".join(
            [
                f"{item.name} ({item.quantity}x {item.price} zł)"
                for item in expense.items
            ]
        )

        category_name = expense.category.name if expense.category else ""

        writer.writerow(
            [
                expense.id,
                expense.date,
                expense.description or "",
                expense.amount,
                category_name,
                items_str,
                expense.metadata_ai or "",
                expense.receipt_image_path or "",
            ]
        )

    return output.getvalue()
