"""
Import wyciągu bankowego: parser per bank → wspólne porównanie z bazą.

Granica: parser zwraca `list[BankOperation]` i nic więcej. Matching, endpoint
i frontend nie wiedzą, z jakiego banku są dane. Nowy bank = nowa funkcja
`parse_<bank>(data: bytes) -> (ops, skipped_income)` + wpis w `PARSERS`.
"""
import csv
import io
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Dict, Iterable, List, Sequence, Tuple

from app.schemas.bank_import import ImportCandidate, ImportRow

DATE_TOLERANCE = timedelta(days=1)


@dataclass(frozen=True)
class BankOperation:
    date: date
    amount: float  # obciążenie jako liczba dodatnia, PLN
    description: str
    bank_category: str


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1250")


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _parse_pln(raw: str) -> float:
    # "-1 234,56 PLN" → -1234.56
    return float(raw.replace("PLN", "").replace("\xa0", "").replace(" ", "").replace(",", "."))


# ---------- mBank ----------

MBANK_HEADER = "#Data operacji"


def parse_mbank_csv(data: bytes) -> Tuple[List[BankOperation], int]:
    """
    Eksport „Lista operacji" z mBanku: nagłówek banku, potem tabela od linii
    `#Data operacji;#Opis operacji;#Rachunek;#Kategoria;#Kwota;`. Opisy w
    cudzysłowach zawierają entery, więc plik idzie do `csv` w całości, nie
    liniami.
    """
    text = _decode(data)
    start = text.find(MBANK_HEADER)
    if start < 0:
        raise ValueError("Nie znaleziono tabeli operacji (linii '#Data operacji') — to nie jest eksport mBank?")
    reader = csv.reader(io.StringIO(text[start:]), delimiter=";")
    next(reader)  # nagłówek tabeli

    ops: List[BankOperation] = []
    skipped_income = 0
    for row in reader:
        if len(row) < 5 or not row[0].strip():
            continue
        amount = _parse_pln(row[4])
        if amount >= 0:
            skipped_income += 1
            continue
        ops.append(
            BankOperation(
                date=date.fromisoformat(row[0].strip()),
                amount=round(-amount, 2),
                description=_squash(row[1]),
                bank_category=_squash(row[3]),
            )
        )
    return ops, skipped_income


PARSERS: Dict[str, Callable[[bytes], Tuple[List[BankOperation], int]]] = {
    "mbank": parse_mbank_csv,
}


# ---------- matching (niezależne od banku) ----------


def match_operations(ops: Sequence[BankOperation], expenses: Iterable) -> List[ImportRow]:
    """
    Kandydat = wydatek o identycznej kwocie (do grosza) w oknie ±1 dzień.
    `matched` gdy operacji z wyciągu dzielących tych samych kandydatów jest
    tyle samo co kandydatów; 0 kandydatów → `missing`; reszta → `ambiguous`.
    """
    by_amount: Dict[float, list] = {}
    for e in expenses:
        by_amount.setdefault(round(e.amount, 2), []).append(e)

    # ponytail: O(n²) po operacjach o tej samej kwocie — wyciągi mają setki wierszy, nie miliony
    candidate_ids: List[set] = []
    candidates: List[list] = []
    for op in ops:
        lo, hi = op.date - DATE_TOLERANCE, op.date + DATE_TOLERANCE
        found = [e for e in by_amount.get(round(op.amount, 2), []) if lo <= e.date <= hi]
        found.sort(key=lambda e: (abs(e.date - op.date), e.id))
        candidates.append(found)
        candidate_ids.append({e.id for e in found})

    rows: List[ImportRow] = []
    for i, op in enumerate(ops):
        if not candidate_ids[i]:
            status = "missing"
        else:
            peers = sum(1 for ids in candidate_ids if ids & candidate_ids[i])
            status = "matched" if peers == len(candidate_ids[i]) else "ambiguous"
        rows.append(
            ImportRow(
                date=op.date,
                amount=op.amount,
                description=op.description,
                bank_category=op.bank_category or None,
                status=status,
                candidates=[
                    ImportCandidate(
                        id=e.id,
                        date=e.date,
                        amount=e.amount,
                        description=e.description,
                        category_name=e.category_name,
                    )
                    for e in candidates[i]
                ],
            )
        )
    return rows
