import csv
from datetime import date, timedelta
from io import StringIO
from typing import List, Optional

from sqlalchemy import extract, func
from sqlalchemy.orm import Session

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

    # Category summary
    category_data = (
        db.query(
            Expense.category_id,
            Category.name.label("category_name"),
            func.sum(Expense.amount).label("total"),
            func.count(Expense.id).label("count"),
        )
        .outerjoin(Category, Expense.category_id == Category.id)
        .filter(
            Expense.user_id == user_id,
            Expense.date >= start_date,
            Expense.date <= end_date,
        )
        .group_by(Expense.category_id, Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )

    category_summary = []
    for c in category_data:
        percentage = (float(c.total) / total_amount * 100) if total_amount > 0 else 0.0
        category_summary.append(
            {
                "category_id": c.category_id,
                "category_name": c.category_name or "Bez kategorii",
                "total_amount": float(c.total),
                "percentage": round(percentage, 2),
                "expense_count": int(c.count),
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
