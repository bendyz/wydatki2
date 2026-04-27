from datetime import date as DateType
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ExpenseItemBase(BaseModel):
    """Bazowy schemat pozycji wydatku (produkt na paragonie)"""

    name: str = Field(..., min_length=1, description="Nazwa produktu/usługi")
    price: float = Field(..., gt=0, description="Cena jednostkowa")
    quantity: float = Field(default=1.0, gt=0, description="Ilość")
    category_id: Optional[int] = Field(
        None, description="ID kategorii dla tej konkretnej pozycji (opcjonalne)"
    )


class ExpenseItemCreate(ExpenseItemBase):
    """Schemat do tworzenia pozycji wydatku"""

    pass


class ExpenseItemResponse(ExpenseItemBase):
    """Schemat pozycji zwracany w odpowiedzi API"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    expense_id: int


class ExpenseBase(BaseModel):
    """Bazowy schemat wydatku"""

    amount: float = Field(..., gt=0, description="Całkowita kwota wydatku")
    description: Optional[str] = Field(None, description="Opis lub nazwa sklepu")
    date: DateType = Field(..., description="Data wydatku")
    category_id: Optional[int] = Field(
        None, description="ID kategorii ogólnej dla całego wydatku (opcjonalne)"
    )


class ExpenseCreate(ExpenseBase):
    """Schemat do tworzenia nowego wydatku z pozycjami"""

    items: List[ExpenseItemCreate] = Field(
        default_factory=list, description="Pozycje na paragonie"
    )


class ExpenseUpdate(BaseModel):
    """Schemat do aktualizacji wydatku (wszystkie pola opcjonalne)"""

    amount: Optional[float] = Field(None, gt=0)
    description: Optional[str] = None
    date: Optional[DateType] = None
    category_id: Optional[int] = None
    receipt_image_path: Optional[str] = Field(
        None, description="Ścieżka do zdjęcia paragonu (null aby usunąć)"
    )
    items: Optional[List[ExpenseItemCreate]] = None


class ExpenseResponse(ExpenseBase):
    """Schemat wydatku zwracany w odpowiedzi API"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    metadata_ai: Optional[str] = None
    receipt_image_path: Optional[str] = Field(
        None, description="Ścieżka do przetworzonego zdjęcia paragonu na dysku"
    )
    created_at: Optional[datetime] = None
    items: List[ExpenseItemResponse] = Field(
        default_factory=list, description="Rozszerzone pozycje wydatku"
    )
