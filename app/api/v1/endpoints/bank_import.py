from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.v1.endpoints.auth import get_current_user
from app.db.session import get_db
from app.models.models import Expense, User
from app.schemas.bank_import import BankImportResponse, ImportSummary
from app.services.bank_import import DATE_TOLERANCE, PARSERS, match_operations

router = APIRouter()


@router.post(
    "/bank-csv",
    response_model=BankImportResponse,
    summary="Porównaj wyciąg bankowy (CSV) z zapisanymi wydatkami",
    description=(
        "Wgrywa eksport operacji z banku i dla każdego obciążenia sprawdza "
        "deterministycznie (kwota do grosza, data ±1 dzień), czy wydatek jest już "
        "w bazie. Zwraca listę operacji ze statusem `matched` / `ambiguous` / "
        "`missing` i kandydatami z bazy. Nic nie zapisuje — dodanie brakującej "
        "operacji to osobne wywołanie `/ai/text` + `POST /expenses`. "
        "Wpływy są pomijane. Obsługiwane banki: " + ", ".join(PARSERS)
    ),
)
async def import_bank_csv(
    file: UploadFile = File(..., description="Plik CSV wyeksportowany z banku"),
    bank: str = Form("mbank", description="Format wyciągu: " + ", ".join(PARSERS)),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    parser = PARSERS.get(bank)
    if parser is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Nieznany bank '{bank}'. Obsługiwane: {', '.join(PARSERS)}",
        )
    try:
        ops, skipped_income = parser(await file.read())
    except (ValueError, UnicodeDecodeError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    expenses = []
    if ops:
        dates = [o.date for o in ops]
        expenses = (
            db.query(Expense)
            .filter(
                Expense.user_id == current_user.id,
                Expense.date >= min(dates) - DATE_TOLERANCE,
                Expense.date <= max(dates) + DATE_TOLERANCE,
            )
            .all()
        )

    rows = match_operations(ops, expenses)
    return BankImportResponse(
        bank=bank,
        summary=ImportSummary(
            matched=sum(r.status == "matched" for r in rows),
            ambiguous=sum(r.status == "ambiguous" for r in rows),
            missing=sum(r.status == "missing" for r in rows),
            skipped_income=skipped_income,
        ),
        rows=rows,
    )
