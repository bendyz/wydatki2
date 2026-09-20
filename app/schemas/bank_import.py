from datetime import date as DateType
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

ImportStatus = Literal["matched", "ambiguous", "missing"]


class ImportCandidate(BaseModel):
    """Wydatek z bazy o tej samej kwocie w oknie ±1 dzień od operacji"""

    id: int
    date: DateType
    amount: float
    description: Optional[str] = None
    category_name: Optional[str] = None


class ImportRow(BaseModel):
    """Jedna operacja z wyciągu wraz z wynikiem porównania z bazą"""

    date: DateType = Field(..., description="Data operacji z wyciągu")
    amount: float = Field(..., description="Kwota obciążenia (dodatnia), PLN")
    description: str = Field(..., description="Opis operacji z wyciągu, zwinięte białe znaki")
    bank_category: Optional[str] = Field(None, description="Kategoria nadana przez bank")
    status: ImportStatus = Field(
        ...,
        description=(
            "matched — tyle samo wydatków w bazie co operacji w wyciągu (zielony); "
            "ambiguous — liczby się nie zgadzają, patrz `candidates` (żółty); "
            "missing — brak wydatku o tej kwocie w oknie ±1 dzień (pomarańczowy)"
        ),
    )
    candidates: List[ImportCandidate] = Field(
        default_factory=list, description="Wydatki z bazy, które mogą odpowiadać tej operacji"
    )


class ImportSummary(BaseModel):
    matched: int
    ambiguous: int
    missing: int
    skipped_income: int = Field(..., description="Wpływy pominięte przy imporcie")


class BankImportResponse(BaseModel):
    bank: str
    summary: ImportSummary
    rows: List[ImportRow]
