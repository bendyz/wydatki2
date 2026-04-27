from typing import Optional

from pydantic import BaseModel


class LoginRequest(BaseModel):
    """Schemat żądania logowania użytkownika"""

    email: str
    password: str


class Token(BaseModel):
    """Schemat odpowiedzi z tokenem JWT"""

    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """Schemat payloadu JWT (używany przy dekodowaniu tokena)"""

    sub: Optional[str] = None  # zazwyczaj email użytkownika
    exp: Optional[int] = None  # timestamp wygaśnięcia
