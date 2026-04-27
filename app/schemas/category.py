from typing import Optional

from pydantic import BaseModel, ConfigDict


class CategoryBase(BaseModel):
    """Bazowy schemat kategorii"""

    name: str
    user_id: Optional[int] = None


class CategoryCreate(CategoryBase):
    """Schemat do tworzenia nowej kategorii"""

    pass


class CategoryUpdate(BaseModel):
    """Schemat do aktualizacji kategorii (wszystkie pola opcjonalne)"""

    name: Optional[str] = None
    user_id: Optional[int] = None


class CategoryResponse(CategoryBase):
    """Schemat zwracany w odpowiedziach API"""

    model_config = ConfigDict(from_attributes=True)

    id: int
