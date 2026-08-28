from datetime import date as DateType
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.tag import TagResponse


def validate_price_not_zero(value: float) -> float:
    """Cena pozycji może być ujemna (rabat, zwrot), ale nigdy zerowa."""
    if value == 0:
        raise ValueError("Cena nie może być zerem (ujemna oznacza rabat lub zwrot)")
    return value


class ExpenseItemBase(BaseModel):
    """Bazowy schemat pozycji wydatku (produkt na paragonie)"""

    name: str = Field(..., min_length=1, description="Nazwa produktu/usługi")
    price: float = Field(
        ...,
        description=(
            "Cena jednostkowa (ujemna = rabat lub zwrot); "
            "przy zapisie nie może być zerem"
        ),
    )
    quantity: float = Field(default=1.0, gt=0, description="Ilość")
    category_id: Optional[int] = Field(
        None, description="ID kategorii dla tej konkretnej pozycji (opcjonalne)"
    )


class ExpenseItemCreate(ExpenseItemBase):
    """Schemat do tworzenia pozycji wydatku"""

    # Walidacja tylko na wejściu — ExpenseItemResponse dziedziczy z Base i musi
    # umieć zwrócić każdy wiersz, jaki faktycznie leży w bazie.
    _validate_price = field_validator("price")(validate_price_not_zero)


class ExpenseItemResponse(ExpenseItemBase):
    """Schemat pozycji zwracany w odpowiedzi API"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    expense_id: int


class ExpenseBase(BaseModel):
    """Bazowy schemat wydatku"""

    # Kwota 0 jest dozwolona przez API; o literówkę pyta GUI przed zapisem.
    # (`ne=0` nie było tu constraintem Pydantic v2 — nic nie sprawdzało.)
    amount: float = Field(..., description="Całkowita kwota wydatku")
    description: Optional[str] = Field(None, description="Opis lub nazwa sklepu")
    date: DateType = Field(..., description="Data wydatku")
    category_id: Optional[int] = Field(
        None, description="ID kategorii ogólnej dla całego wydatku (opcjonalne)"
    )
    card_id: Optional[int] = Field(None, description="ID karty płatniczej (opcjonalne)")


class ExpenseCreate(ExpenseBase):
    """Schemat do tworzenia nowego wydatku z pozycjami"""

    items: List[ExpenseItemCreate] = Field(
        default_factory=list, description="Pozycje na paragonie"
    )


class ExpenseUpdate(BaseModel):
    """Schemat do aktualizacji wydatku (wszystkie pola opcjonalne)"""

    amount: Optional[float] = None
    description: Optional[str] = None
    date: Optional[DateType] = None
    category_id: Optional[int] = None
    card_id: Optional[int] = None
    receipt_image_path: Optional[str] = Field(
        None, description="Ścieżka do zdjęcia paragonu (null aby usunąć)"
    )
    items: Optional[List[ExpenseItemCreate]] = None


class ExpenseResponse(ExpenseBase):
    """Schemat wydatku zwracany w odpowiedzi API"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    category_name: Optional[str] = None
    card_name: Optional[str] = None
    metadata_ai: Optional[str] = None
    receipt_image_path: Optional[str] = Field(
        None, description="Ścieżka do przetworzonego zdjęcia paragonu na dysku"
    )
    created_at: Optional[datetime] = None
    items: List[ExpenseItemResponse] = Field(
        default_factory=list, description="Rozszerzone pozycje wydatku"
    )
    tags: List[TagResponse] = Field(default_factory=list)
