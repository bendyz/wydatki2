from datetime import date as DateType
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class DraftExpenseItem(BaseModel):
    """Pozycja wydatku zaproponowana przez AI do weryfikacji użytkownika"""

    name: str = Field(..., description="Nazwa produktu/usługi rozpoznana przez AI")
    price: float = Field(..., gt=0, description="Cena jednostkowa")
    quantity: float = Field(default=1.0, gt=0, description="Ilość")
    category_id: Optional[int] = Field(
        None, description="Zaproponowane ID kategorii dla tej pozycji"
    )
    category_name: Optional[str] = Field(
        None, description="Zaproponowana nazwa kategorii (do wyświetlenia)"
    )
    confidence: Optional[float] = Field(
        None, ge=0, le=1, description="Pewność AI co do kategorii (0-1)"
    )


class DraftDuplicateWarning(BaseModel):
    """Ostrzeżenie o potencjalnym duplikacie znalezionym w bazie"""

    expense_id: int = Field(..., description="ID istniejącego wydatku")
    amount: float = Field(..., description="Kwota istniejącego wydatku")
    date: DateType = Field(..., description="Data istniejącego wydatku")
    description: Optional[str] = Field(None, description="Opis istniejącego wydatku")
    similarity_score: float = Field(
        ..., ge=0, le=1, description="Wskaźnik podobieństwa (0-1)"
    )
    message: str = Field(..., description="Komunikat dla użytkownika")


class ExpenseDraft(BaseModel):
    """
    Propozycja wydatku wygenerowana przez AI.
    NIE jest zapisywana w bazie – użytkownik musi ją zweryfikować i zaakceptować.
    """

    model_config = ConfigDict(from_attributes=True)

    # Główne dane wydatku
    amount: float = Field(..., gt=0, description="Całkowita kwota wydatku")
    description: Optional[str] = Field(None, description="Nazwa sklepu / opis wydatku")
    date: DateType = Field(..., description="Data wydatku")
    category_id: Optional[int] = Field(
        None, description="Zaproponowane ID kategorii ogólnej"
    )
    category_name: Optional[str] = Field(
        None, description="Zaproponowana nazwa kategorii ogólnej"
    )

    # Pozycje (items) – kluczowe dla paragonów
    items: List[DraftExpenseItem] = Field(
        default_factory=list, description="Rozpoznane pozycje na paragonie"
    )

    # Ścieżka do zdjęcia paragonu (jeśli był upload)
    receipt_image_path: Optional[str] = Field(
        None, description="Ścieżka do przetworzonego zdjęcia paragonu"
    )

    # Ostrzeżenia
    duplicate_warnings: List[DraftDuplicateWarning] = Field(
        default_factory=list,
        description="Lista potencjalnych duplikatów w bazie (do wyświetlenia użytkownikowi)",
    )

    # Metadane AI
    ai_raw_response: Optional[str] = Field(
        None, description="Surowa odpowiedź od LLM (do debugowania/audytu)"
    )
    ai_model: Optional[str] = Field(None, description="Model AI użyty do analizy")
    processing_time_ms: Optional[int] = Field(
        None, description="Czas przetwarzania w milisekundach"
    )

    # Flagi dla frontendu
    is_draft: bool = Field(
        default=True,
        description="Zawsze True – wskazuje, że to propozycja do akceptacji",
    )
    needs_review: bool = Field(
        default=False,
        description="True jeśli AI ma niską pewność – zalecana weryfikacja użytkownika",
    )

    # Karta płatnicza rozpoznana przez AI
    card_id: Optional[int] = Field(None, description="ID karty płatniczej rozpoznanej przez AI")

    # Tagi zaproponowane przez AI (tylko jeśli pewność ≥ 0.7)
    suggested_tags: List[str] = Field(
        default_factory=list,
        description="Tagi zaproponowane przez AI z istniejącej listy tagów użytkownika",
    )

    # Sugestie dla użytkownika
    user_hints: List[str] = Field(
        default_factory=list,
        description="Dodatkowe wskazówki od AI, np. 'Sprawdź datę, rozpoznałem ją niepewnie'",
    )
