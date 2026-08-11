from datetime import date
from typing import List, Optional

from pydantic import BaseModel


class MonthlySummary(BaseModel):
    """Podsumowanie wydatków za konkretny miesiąc"""

    year: int
    month: int
    month_name: str
    total_amount: float
    expense_count: int


class CategorySummary(BaseModel):
    """Podsumowanie wydatków per kategoria"""

    category_id: Optional[int]
    category_name: Optional[str]
    total_amount: float
    percentage: float
    expense_count: int


class CategoryExpenseItem(BaseModel):
    """Pozycja paragonu należąca do rozwijanej kategorii"""

    name: str
    quantity: float
    price: float
    total: float


class CategoryExpenseEntry(BaseModel):
    """
    Wydatek składający się na daną kategorię.

    `amount` to kwota przypisana do TEJ kategorii, nie cała kwota paragonu —
    paragon z pozycjami w kilku kategoriach pojawi się przy każdej z nich,
    za każdym razem tylko z odpowiadającą jej częścią.
    """

    expense_id: int
    date: date
    description: Optional[str] = None
    amount: float
    full_amount: float
    is_partial: bool
    items: List[CategoryExpenseItem] = []


class DailyExpense(BaseModel):
    """Wydatek w konkretnym dniu (do wykresów liniowych)"""

    date: date
    amount: float


class StatsResponse(BaseModel):
    """Główna odpowiedź ze statystykami"""

    period_start: Optional[date] = None
    period_end: Optional[date] = None
    total_amount: float
    total_count: int
    average_per_day: Optional[float] = None
    average_per_expense: float
    monthly_summary: List[MonthlySummary] = []
    category_summary: List[CategorySummary] = []
    daily_expenses: List[DailyExpense] = []


class ExportRequest(BaseModel):
    """Żądanie eksportu wydatków do CSV"""

    start_date: Optional[date] = None
    end_date: Optional[date] = None
    category_id: Optional[int] = None
