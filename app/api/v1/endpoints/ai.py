import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.endpoints.auth import get_current_user
from app.db.session import get_db
from app.models.models import User
from app.schemas.ai_draft import ExpenseDraft
from app.services.ai_service import (
    _encode_image_to_base64,
    parse_receipt_image,
    parse_text_expense,
)
from app.services.image_service import save_and_process_receipt_image

logger = logging.getLogger(__name__)

router = APIRouter()


def _preview_data_url(image_path: str) -> Optional[str]:
    """
    Przetworzone zdjęcie jako data URL do pokazania w modalu draftu.

    Brak pliku degraduje do braku podglądu, nie do błędu — draft jest tu
    rzeczą istotną, a miniatura dodatkiem.
    """
    try:
        return "data:image/jpeg;base64," + _encode_image_to_base64(image_path)
    except OSError:
        logger.warning("Nie udało się odczytać podglądu paragonu: %s", image_path)
        return None


class TextExpenseRequest(BaseModel):
    """Request body for text expense analysis"""

    text: str
    current_date: Optional[date] = None


@router.post(
    "/receipt",
    response_model=ExpenseDraft,
    summary="Analizuj zdjęcie paragonu przez AI",
    description=(
        "Wgrywa zdjęcie paragonu, przetwarza je przez AI (OpenRouter Vision) "
        "i zwraca DRAFT wydatku do weryfikacji przez użytkownika. "
        "Draft NIE jest zapisywany w bazie danych."
    ),
)
async def analyze_receipt(
    file: UploadFile = File(..., description="Zdjęcie paragonu (JPG, PNG, WEBP)"),
    already_cropped: bool = Form(
        False,
        description="Klient zgłasza, że paragon jest już wykadrowany — backend pominie detekcję",
    ),
    include_preview: bool = Form(
        False,
        description=(
            "Dołącz przetworzone zdjęcie do odpowiedzi (`receipt_preview`), "
            "żeby klient mógł je pokazać przed zapisem wydatku"
        ),
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Analizuje zdjęcie paragonu przez AI i zwraca propozycję wydatku (draft).
    Użytkownik musi zweryfikować dane przed zapisaniem.
    """
    # Walidacja typu pliku
    allowed = {"image/jpeg", "image/png", "image/webp", "image/bmp"}
    if not file.content_type or file.content_type not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Nieprawidłowy format pliku. Dozwolone: {', '.join(allowed)}",
        )

    # Zapisz zdjęcie tymczasowo (bez przypisania do wydatku, expense_id=0 jako temp)
    try:
        temp_path = await save_and_process_receipt_image(
            file, expense_id=0, already_cropped=already_cropped
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Analizuj przez AI
    try:
        draft = await parse_receipt_image(
            db=db,
            user_id=current_user.id,
            image_path=temp_path,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Błąd AI: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Nieoczekiwany błąd podczas analizy AI: {str(e)}",
        )

    if include_preview:
        draft.receipt_preview = _preview_data_url(temp_path)

    return draft


@router.post(
    "/text",
    response_model=ExpenseDraft,
    summary="Analizuj tekstowy opis wydatku przez AI",
    description=(
        "Przetwarza opis wydatku w języku naturalnym przez AI (OpenRouter LLM) "
        "i zwraca DRAFT wydatku do weryfikacji. "
        "Przykład: 'Wczoraj wydałem 10zł w żabce na batonika'"
    ),
)
async def analyze_text(
    request: TextExpenseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Analizuje tekstowy opis wydatku przez AI i zwraca propozycję (draft).
    Użytkownik musi zweryfikować dane przed zapisaniem.
    """
    text = request.text.strip()
    if not text or len(text) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tekst opisu jest zbyt krótki (min. 3 znaki).",
        )

    try:
        draft = await parse_text_expense(
            db=db,
            user_id=current_user.id,
            text=text,
            current_date=request.current_date,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Błąd AI: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Nieoczekiwany błąd podczas analizy AI: {str(e)}",
        )

    return draft
