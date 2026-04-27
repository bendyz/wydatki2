from datetime import date as DateType
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SubscriptionBase(BaseModel):
    """Bazowy schemat abonamentu/subskrypcji"""

    name: str = Field(
        ..., min_length=1, description="Nazwa abonamentu, np. Netflix, Telefon"
    )
    amount: float = Field(..., gt=0, description="Kwota cyklicznego wydatku")
    frequency_days: int = Field(
        ...,
        gt=0,
        description="Co ile dni powtarza się płatność (np. 30 dla miesięcznego)",
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


class SubscriptionCreate(SubscriptionBase):
    """Schemat do tworzenia nowego abonamentu"""

    pass


class SubscriptionUpdate(BaseModel):
    """Schemat do aktualizacji abonamentu (wszystkie pola opcjonalne)"""

    name: Optional[str] = Field(None, min_length=1)
    amount: Optional[float] = Field(None, gt=0)
    frequency_days: Optional[int] = Field(None, gt=0)
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
