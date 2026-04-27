import base64
import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud.category import get_categories
from app.crud.expense import get_expenses
from app.schemas.ai_draft import DraftDuplicateWarning, DraftExpenseItem, ExpenseDraft


def _build_system_prompt(user_categories: List[dict]) -> str:
    """Buduje prompt systemowy z kategoriami i kontekstem personalnym."""
    if user_categories:
        categories_text = "\n".join(
            [f"- ID {c['id']}: {c['name']}" for c in user_categories]
        )
    else:
        categories_text = "- Brak zdefiniowanych kategorii"

    if settings.personal_context:
        context_text = "\n".join([f"- {ctx}" for ctx in settings.personal_context])
    else:
        context_text = "- Brak dodatkowego kontekstu"

    return f"""Jesteś inteligentnym asystentem finansowym do analizy wydatków.
Twoim zadaniem jest przetworzenie dostarczonego paragonu lub opisu wydatku i zwrócenie wyniku WYŁĄCZNIE jako obiekt JSON. Nie dodawaj żadnego tekstu przed ani po JSON.

DOSTĘPNE KATEGORIE UŻYTKOWNIKA:
{categories_text}

KONTEKST PERSONALNY (pomocny przy kategoryzacji):
{context_text}

ZASADY:
1. Rozpoznaj sklep/miejsce (description), datę transakcji, kwotę całkowitą i pozycje.
2. Każda pozycja powinna mieć przypisaną kategorię z listy dostępnych (użyj ID). Jeśli nie pasuje do żadnej, użyj null.
3. Jeśli nie jesteś pewien kategorii, w polu confidence podaj niską wartość (0.0-1.0) i ustaw needs_review na true.
4. Data MUSI być w formacie YYYY-MM-DD. Jeśli nie znasz dokładnej daty, użyj dzisiejszej daty.
5. Kwota (amount) to suma wszystkich pozycji (ilość * cena jednostkowa).
6. Zwróć TYLKO obiekt JSON. Nie używaj markdown (```json), nie komentuj.

FORMAT ODPOWIEDZI:
{{
  "amount": 123.45,
  "description": "Nazwa sklepu lub krótki opis",
  "date": "2025-01-15",
  "category_id": 1,
  "category_name": "Nazwa kategorii",
  "items": [
    {{
      "name": "Nazwa produktu",
      "price": 10.50,
      "quantity": 1,
      "category_id": 1,
      "category_name": "Nazwa kategorii",
      "confidence": 0.95
    }}
  ],
  "user_hints": ["opcjonalna wskazówka dla użytkownika"],
  "needs_review": false
}}"""


def _get_mime_type_from_path(image_path: str) -> str:
    """Wykrywa MIME type na podstawie rozszerzenia pliku."""
    ext = Path(image_path).suffix.lower()
    mapping = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    return mapping.get(ext, "image/jpeg")


def _encode_image_to_base64(image_path: str) -> str:
    """Koduje obraz do base64."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Obraz nie istnieje: {image_path}")
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


async def _call_openrouter(
    messages: List[dict],
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> str:
    """Wykonuje zapytanie do API OpenRouter."""
    api_key = settings.openrouter.api_key
    if not api_key:
        raise ValueError(
            "Brak klucza API OpenRouter. Ustaw go w data/config/config.yaml "
            "lub w zmiennej środowiskowej OPENROUTER_API_KEY."
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": settings.app_name,
    }

    payload = {
        "model": model or settings.openrouter.model,
        "messages": messages,
        "max_tokens": max_tokens or settings.openrouter.max_tokens,
        "temperature": (
            temperature if temperature is not None else settings.openrouter.temperature
        ),
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


def _parse_ai_json_response(raw_text: str) -> dict:
    """Czyści odpowiedź z markdown i parsuje JSON."""
    text = raw_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    return json.loads(text)


def _check_duplicates(
    db: Session,
    user_id: int,
    amount: float,
    expense_date: date,
    description: Optional[str] = None,
) -> List[DraftDuplicateWarning]:
    """Sprawdza czy w bazie nie ma podobnego wydatku (potencjalny duplikat)."""
    warnings = []
    cfg = settings.duplicates

    date_from = expense_date - timedelta(days=cfg.date_range_days)
    date_to = expense_date + timedelta(days=cfg.date_range_days)

    candidates = get_expenses(
        db,
        user_id=user_id,
        start_date=date_from,
        end_date=date_to,
    )

    for exp in candidates:
        if abs(exp.amount - amount) <= cfg.amount_threshold:
            similarity = 0.8
            if description and exp.description:
                desc_lower = description.lower()
                exp_desc_lower = exp.description.lower()
                if desc_lower in exp_desc_lower or exp_desc_lower in desc_lower:
                    similarity = 0.95

            warnings.append(
                DraftDuplicateWarning(
                    expense_id=exp.id,
                    amount=exp.amount,
                    date=exp.date,
                    description=exp.description,
                    similarity_score=round(similarity, 2),
                    message=(
                        f"Znaleziono podobny wydatek: "
                        f"{exp.description or 'brak opisu'} "
                        f"({exp.amount} zł, {exp.date})"
                    ),
                )
            )

    return warnings


def _build_draft_from_parsed(
    parsed: dict,
    db: Session,
    user_id: int,
    receipt_image_path: Optional[str] = None,
    ai_raw_response: Optional[str] = None,
    ai_model: Optional[str] = None,
    processing_time_ms: Optional[int] = None,
) -> ExpenseDraft:
    """Buduje obiekt ExpenseDraft z sparsowanej odpowiedzi AI."""
    items = []
    for item_data in parsed.get("items", []):
        items.append(
            DraftExpenseItem(
                name=item_data.get("name", "Nieznana pozycja"),
                price=float(item_data.get("price", 0)),
                quantity=float(item_data.get("quantity", 1)),
                category_id=item_data.get("category_id"),
                category_name=item_data.get("category_name"),
                confidence=item_data.get("confidence"),
            )
        )

    expense_date_str = parsed.get("date")
    try:
        expense_date = (
            datetime.strptime(expense_date_str, "%Y-%m-%d").date()
            if expense_date_str
            else date.today()
        )
    except (ValueError, TypeError):
        expense_date = date.today()

    amount = float(parsed.get("amount", 0))

    duplicate_warnings = _check_duplicates(
        db=db,
        user_id=user_id,
        amount=amount,
        expense_date=expense_date,
        description=parsed.get("description"),
    )

    return ExpenseDraft(
        amount=amount,
        description=parsed.get("description"),
        date=expense_date,
        category_id=parsed.get("category_id"),
        category_name=parsed.get("category_name"),
        items=items,
        receipt_image_path=receipt_image_path,
        duplicate_warnings=duplicate_warnings,
        ai_raw_response=ai_raw_response,
        ai_model=ai_model,
        processing_time_ms=processing_time_ms,
        needs_review=parsed.get("needs_review", False) or len(items) == 0,
        user_hints=parsed.get("user_hints", []),
    )


async def parse_receipt_image(
    db: Session,
    user_id: int,
    image_path: str,
) -> ExpenseDraft:
    """
    Analizuje zdjęcie paragonu przez AI (OpenRouter Vision) i zwraca draft wydatku.
    Draft NIE jest zapisywany w bazie – użytkownik musi go zweryfikować.
    """
    start_time = time.time()

    user_categories = [
        {"id": c.id, "name": c.name}
        for c in get_categories(db, user_id=user_id, include_global=True)
    ]

    base64_image = _encode_image_to_base64(image_path)
    mime_type = _get_mime_type_from_path(image_path)

    system_prompt = _build_system_prompt(user_categories)

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Przeanalizuj ten paragon i zwróć wynik jako JSON "
                        "zgodnie z instrukcją systemową."
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{base64_image}"},
                },
            ],
        },
    ]

    raw_response = await _call_openrouter(messages)

    processing_time_ms = int((time.time() - start_time) * 1000)

    parsed = _parse_ai_json_response(raw_response)

    return _build_draft_from_parsed(
        parsed=parsed,
        db=db,
        user_id=user_id,
        receipt_image_path=image_path,
        ai_raw_response=raw_response,
        ai_model=settings.openrouter.model,
        processing_time_ms=processing_time_ms,
    )


async def parse_text_expense(
    db: Session,
    user_id: int,
    text: str,
    current_date: Optional[date] = None,
) -> ExpenseDraft:
    """
    Analizuje tekstowy opis wydatku przez AI i zwraca draft.
    Przykład: 'Wczoraj wydałem 10zł w żabce na batonika'

    Draft NIE jest zapisywany w bazie – użytkownik musi go zweryfikować.
    """
    start_time = time.time()

    if current_date is None:
        current_date = date.today()

    user_categories = [
        {"id": c.id, "name": c.name}
        for c in get_categories(db, user_id=user_id, include_global=True)
    ]

    system_prompt = _build_system_prompt(user_categories)

    user_prompt = f"""Przeanalizuj poniższy opis wydatku i zwróć wynik jako JSON.
Dzisiaj jest {current_date.strftime("%Y-%m-%d")} ({current_date.strftime("%A")}).

OPIS UŻYTKOWNIKA:
{text}

Pamiętaj: zwróć TYLKO obiekt JSON."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    raw_response = await _call_openrouter(messages)

    processing_time_ms = int((time.time() - start_time) * 1000)

    parsed = _parse_ai_json_response(raw_response)

    return _build_draft_from_parsed(
        parsed=parsed,
        db=db,
        user_id=user_id,
        ai_raw_response=raw_response,
        ai_model=settings.openrouter.model,
        processing_time_ms=processing_time_ms,
    )
