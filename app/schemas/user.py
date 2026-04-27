from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    """Bazowy schemat użytkownika z wspólnymi polami"""

    email: EmailStr
    full_name: Optional[str] = None


class UserCreate(UserBase):
    """Schemat do tworzenia nowego użytkownika (rejestracja)"""

    password: str = Field(
        ..., min_length=6, description="Hasło użytkownika (min. 6 znaków)"
    )


class UserResponse(UserBase):
    """Schemat zwracany w odpowiedziach API (bez hasła)"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    created_at: datetime


class UserInDB(UserBase):
    """Schemat wewnętrzny używany przy operacjach na bazie danych"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    hashed_password: str
    is_active: bool
    created_at: datetime
