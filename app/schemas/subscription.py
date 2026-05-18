from datetime import date as DateType
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SubscriptionBase(BaseModel):
    """Bazowy schemat abonamentu/subskrypcji"""

    name: str = Field(
        ..., min_length=1, description="Nazwa abonamentu, np. Netflix, Telefon"
    )
    amount: float = Field(..., gt=0, description="Kwota cyklicznego wydatku")
    frequency_days: Optional[int] = Field(
        None,
        gt=0,
        description="Co ile dni powtarza się płatność. Null gdy billing_day_of_month jest ustawiony.",
    )
    billing_day_of_month: Optional[int] = Field(
        None,
        ge=1,
        le=31,
        description="Dzień miesiąca (1-31) dla trybu miesięcznego. Alternatywa dla frequency_days.",
    )
    start_date: DateType = Field(..., description="Data pierwszej płatności")
    end_date: Optional[DateType] = Field(
        None, description="Data ostatniej płatności (null jeśli bez końca)"
    )
    next_billing_date: DateType = Field(
        ...,
        description="Data kolejnej planowanej płatności (aktualizowana przez scheduler)",
    )
    remaining_installments: Optional[int] = Field(
        None, gt=0, description="Ile płatności pozostało (null jeśli bez limitu)"
    )
    category_id: Optional[int] = Field(
        None, description="ID kategorii przypisanej do abonamentu"
    )

    @model_validator(mode="after")
    def check_frequency_or_day(self):
        if self.frequency_days is None and self.billing_day_of_month is None:
            raise ValueError("Podaj frequency_days lub billing_day_of_month")
        if self.frequency_days is not None and self.billing_day_of_month is not None:
            raise ValueError("Podaj tylko jedno: frequency_days lub billing_day_of_month")
        return self


class SubscriptionCreate(SubscriptionBase):
    """Schemat do tworzenia nowego abonamentu"""

    pass


class SubscriptionUpdate(BaseModel):
    """Schemat do aktualizacji abonamentu (wszystkie pola opcjonalne)"""

    name: Optional[str] = Field(None, min_length=1)
    amount: Optional[float] = Field(None, gt=0)
    frequency_days: Optional[int] = Field(None, gt=0)
    billing_day_of_month: Optional[int] = Field(None, ge=1, le=31)
    start_date: Optional[DateType] = None
    end_date: Optional[DateType] = None
    next_billing_date: Optional[DateType] = None
    remaining_installments: Optional[int] = Field(None, gt=0)
    category_id: Optional[int] = None


class SubscriptionResponse(SubscriptionBase):
    """Schemat abonamentu zwracany w odpowiedzi API"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
