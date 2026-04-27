from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.v1.endpoints.auth import get_current_user
from app.crud.stats import export_expenses_to_csv, get_stats
from app.db.session import get_db
from app.models.models import User
from app.schemas.stats import StatsResponse

router = APIRouter()


@router.get(
    "/",
    response_model=StatsResponse,
    summary="Pobierz statystyki wydatków",
)
def read_stats(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Zwraca statystyki wydatków użytkownika za określony okres.
    Jeśli nie podano dat, domyślnie zwraca bieżący miesiąc.
    """
    stats = get_stats(
        db,
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date,
    )
    return stats


@router.get(
    "/export",
    summary="Eksportuj wydatki do CSV",
    response_class=StreamingResponse,
)
def export_csv(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    category_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Eksportuje wydatki użytkownika do pliku CSV.
    """
    csv_content = export_expenses_to_csv(
        db,
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date,
        category_id=category_id,
    )

    filename = f"wydatki_{current_user.id}"
    if start_date:
        filename += f"_{start_date}"
    if end_date:
        filename += f"_{end_date}"
    filename += ".csv"

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
