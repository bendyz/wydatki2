from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.v1.endpoints.auth import get_current_user
from app.crud.expense import get_expense
from app.db.session import get_db
from app.models.models import User
from app.services.image_service import (
    delete_receipt_images,
    get_receipt_image_path,
    save_and_process_receipt_image,
)

router = APIRouter()

ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/bmp",
    "image/tiff",
}


@router.post(
    "/{expense_id}/receipt",
    status_code=status.HTTP_201_CREATED,
    summary="Prześlij zdjęcie paragonu do wydatku",
)
async def upload_receipt_image(
    expense_id: int,
    file: UploadFile = File(..., description="Zdjęcie paragonu do przetworzenia"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Przesyła i przetwarza zdjęcie paragonu przypisując je do istniejącego wydatku.
    Zdjęcie jest konwertowane do skali szarości, poddawane thresholdingowi
    i zapisywane jako zoptymalizowany JPEG.
    """
    # Sprawdź czy wydatek istnieje i należy do użytkownika
    expense = get_expense(db, expense_id=expense_id, user_id=current_user.id)
    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wydatek nie został znaleziony",
        )

    # Walidacja typu pliku
    if not file.content_type or file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Nieprawidłowy format pliku. Dozwolone: {', '.join(ALLOWED_CONTENT_TYPES)}",
        )

    # Usuń stare zdjęcie jeśli istnieje (aby nie zaśmiecać dysku)
    if expense.receipt_image_path:
        delete_receipt_images(expense_id)

    # Zapisz i przetwórz nowe zdjęcie
    try:
        relative_path = await save_and_process_receipt_image(file, expense_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Zaktualizuj wydatek w bazie
    expense.receipt_image_path = relative_path
    db.commit()
    db.refresh(expense)

    return {
        "message": "Zdjęcie paragonu zostało przetworzone i zapisane",
        "expense_id": expense_id,
        "image_path": relative_path,
    }


@router.get(
    "/{expense_id}/receipt",
    summary="Pobierz zdjęcie paragonu",
    responses={
        200: {
            "description": "Przetworzone zdjęcie paragonu (czarno-białe, skompresowane)",
            "content": {"image/jpeg": {}},
        }
    },
)
async def get_receipt_image(
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Zwraca przetworzone zdjęcie paragonu powiązanego z wydatkiem.
    """
    expense = get_expense(db, expense_id=expense_id, user_id=current_user.id)
    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wydatek nie został znaleziony",
        )

    if not expense.receipt_image_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wydatek nie ma przypisanego zdjęcia paragonu",
        )

    # Parsuj ścieżkę aby wyciągnąć nazwę pliku
    stored_path = Path(expense.receipt_image_path)
    filename = stored_path.name

    image_path = get_receipt_image_path(expense_id, filename)
    if not image_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plik zdjęcia nie został znaleziony na dysku",
        )

    return FileResponse(
        path=str(image_path),
        media_type="image/jpeg",
        filename=f"receipt_{expense_id}.jpg",
    )


@router.delete(
    "/{expense_id}/receipt",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Usuń zdjęcie paragonu",
)
async def delete_receipt_image(
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Usuwa zdjęcie paragonu powiązane z wydatkiem z dysku i bazy danych.
    """
    expense = get_expense(db, expense_id=expense_id, user_id=current_user.id)
    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wydatek nie został znaleziony",
        )

    if expense.receipt_image_path:
        delete_receipt_images(expense_id)
        expense.receipt_image_path = None
        db.commit()

    return None
