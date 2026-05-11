import csv
from collections import defaultdict
from datetime import date, timedelta
from io import StringIO
from typing import List, Optional

from sqlalchemy import extract, func
from sqlalchemy.orm import Session, joinedload

from app.models.models import Category, Expense, ExpenseItem


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
        if expense.items:
            for item in expense.items:
                item_amount = round(item.price * item.quantity, 4)
                cid = item.category_id
                cname = item.category.name if item.category else None
                cat_data[cid]["name"] = cname
                cat_data[cid]["total"] += item_amount
                cat_data[cid]["expense_ids"].add(expense.id)
            # Rozbieżność (rabaty / zaokrąglenia) → kategoria nagłówka
            items_sum = sum(item.price * item.quantity for item in expense.items)
            discrepancy = expense.amount - items_sum
            if abs(discrepancy) > 0.005:
                cid = expense.category_id
                cname = expense.category.name if expense.category else None
                cat_data[cid]["name"] = cname
                cat_data[cid]["total"] += discrepancy
                cat_data[cid]["expense_ids"].add(expense.id)
        else:
            cid = expense.category_id
            cname = expense.category.name if expense.category else None
            cat_data[cid]["name"] = cname
            cat_data[cid]["total"] += expense.amount
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
