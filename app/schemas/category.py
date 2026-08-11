from typing import Optional

from pydantic import BaseModel, ConfigDict


class CategoryBase(BaseModel):
    """Bazowy schemat kategorii"""

    name: str
    user_id: Optional[int] = None
    # Muszą mieć wartości domyślne — CategoryResponse dziedziczy po CategoryBase,
    # więc pola bez domyślnych stałyby się wymagane w CategoryCreate i zepsuły
    # istniejących klientów (m.in. aplikację na Androida).
    color: Optional[str] = None  # hex, np. "#22d3ee"; brak → nadawany automatycznie
    icon: Optional[str] = None  # klasa Font Awesome, np. "fa-cart-shopping"


class CategoryCreate(CategoryBase):
    """Schemat do tworzenia nowej kategorii"""

    pass


class CategoryUpdate(BaseModel):
    """Schemat do aktualizacji kategorii (wszystkie pola opcjonalne)"""

    name: Optional[str] = None
    user_id: Optional[int] = None
    color: Optional[str] = None
    icon: Optional[str] = None


class CategoryResponse(CategoryBase):
    """Schemat zwracany w odpowiedziach API"""

    model_config = ConfigDict(from_attributes=True)

    id: int
