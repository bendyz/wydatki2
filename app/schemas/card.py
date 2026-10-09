from datetime import date
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PaymentCardBase(BaseModel):
    name: str = Field(..., min_length=1, description="Krótka nazwa karty")
    last_six_digits: Optional[str] = Field(None, min_length=6, max_length=6, description="Ostatnie 6 cyfr numeru karty")
    min_transactions: Optional[int] = Field(None, ge=1, description="Min. liczba transakcji/miesiąc do bezpłatnej karty")
    min_amount: Optional[float] = Field(None, gt=0, description="Min. kwota zł/miesiąc do bezpłatnej karty")
    rules_require_all: bool = Field(True, description="True=wszystkie warunki (AND), False=dowolny warunek (OR)")
    yearly_min_amount: Optional[float] = Field(None, gt=0, description="Min. kwota zł w roku (od rocznicy wydania karty)")
    issued_date: Optional[date] = Field(None, description="Data wydania karty; od jej rocznicy liczy się rok")


class PaymentCardCreate(PaymentCardBase):
    pass


class PaymentCardUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    last_six_digits: Optional[str] = Field(None, min_length=6, max_length=6)
    min_transactions: Optional[int] = Field(None, ge=1)
    min_amount: Optional[float] = Field(None, gt=0)
    rules_require_all: Optional[bool] = None
    yearly_min_amount: Optional[float] = Field(None, gt=0)
    issued_date: Optional[date] = None


class PaymentCardResponse(PaymentCardBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int


class CardMonthStats(BaseModel):
    year: int
    month: int
    label: str
    transaction_count: int
    total_amount: float
    met_transactions: Optional[bool] = None
    met_amount: Optional[bool] = None
    is_free: bool


class CardYearStats(BaseModel):
    period_start: date
    period_end: date
    total_amount: float
    target: float
    remaining: float
    percent: float
    is_met: bool


class CardStatsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    last_six_digits: Optional[str]
    min_transactions: Optional[int]
    min_amount: Optional[float]
    rules_require_all: bool
    yearly_min_amount: Optional[float] = None
    issued_date: Optional[date] = None
    year: Optional[CardYearStats] = None
    months: List[CardMonthStats]
