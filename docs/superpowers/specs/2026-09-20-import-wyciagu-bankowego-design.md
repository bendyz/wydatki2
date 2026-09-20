# Import wydatków z wyciągu bankowego (CSV)

Data: 2026-09-20. Gałąź: `feat/bank-import`.

## Cel

Czwarta zakładka w „Dodaj wydatek": użytkownik wrzuca CSV z banku, dostaje
listę operacji pokolorowaną według tego, czy wydatek już jest w bazie, i może
dodać brakujące przez istniejący przepływ AI (`/ai/text` → draft → zapis).
Porównanie jest deterministyczne (kwota + data), AI wchodzi dopiero przy
dodawaniu pojedynczego wiersza.

## Granica: parser per bank vs. matching wspólny

```
bytes ──parse_<bank>()──▶ list[BankOperation] ──match_operations()──▶ list[ImportRow]
        (zależne od banku)   (date, amount, description, bank_category)   (niezależne od banku)
```

- `BankOperation` to jedyny kontrakt między parserem a resztą. Nowy bank =
  nowa funkcja `parse_<bank>(data: bytes) -> list[BankOperation]` + wpis w
  słowniku `PARSERS`. Matching, endpoint i frontend nie wiedzą, skąd są dane.
- Parser zwraca **tylko obciążenia** jako dodatnie kwoty w PLN (wpływy
  odrzuca; ich liczbę zwraca obok, żeby `summary` mógł to pokazać).

## mBank

Plik: UTF-8 z BOM (fallback cp1250), `;`, CRLF, nagłówek banku na górze,
właściwa tabela zaczyna się od linii `#Data operacji;#Opis operacji;…`.
Opisy w cudzysłowach mogą zawierać enter — stdlib `csv` to obsługuje, byle
nie ciąć po liniach przed parserem. Kwota `-118,72 PLN`.

## Matching

Wejście: operacje + wydatki użytkownika z zakresu `[min(date)-1, max(date)+1]`
(jedno zapytanie).

Dla operacji `o`: kandydaci = wydatki z `round(amount, 2)` identyczną i datą
w `[o.date-1, o.date+1]`. Status:

- `missing` — 0 kandydatów (pomarańczowy),
- `matched` — liczba operacji z CSV o tej kwocie, których okna dat obejmują
  tego samego kandydata, jest równa liczbie kandydatów (zielony),
- `ambiguous` — pozostałe (żółty).

Kandydaci (id, date, amount, description, category_name) są zawsze w
odpowiedzi, żeby przy `ambiguous` dało się rozstrzygnąć na oko.

Nic nie jest zapisywane — endpoint jest czystym odczytem.

## API

`POST /api/v1/import/bank-csv` — multipart: `file`, `bank` (default `mbank`).

```json
{
  "bank": "mbank",
  "summary": {"matched": 9, "ambiguous": 2, "missing": 5, "skipped_income": 0},
  "rows": [
    {"date": "2026-09-18", "amount": 118.72, "description": "LIDL ZAKUP PRZY UŻYCIU KARTY W KRAJU",
     "bank_category": "Żywność i chemia domowa", "status": "matched",
     "candidates": [{"id": 1234, "date": "2026-09-18", "amount": 118.72,
                     "description": "Lidl", "category_name": "Jedzenie"}]}
  ]
}
```

Błędy: 400 gdy nie da się znaleźć tabeli / nieznany `bank`.

## Frontend

- Zakładka „Import" w `templates/views/add_expense.html`: input pliku, przycisk.
- Lista wierszy z paskiem koloru po lewej. Kandydaci wypisani pod wierszem
  gdy `ambiguous`. Przy `ambiguous`/`missing` przycisk „Dodaj".
- „Dodaj" otwiera mały modal z textarea prefilled:
  `"<date>, <amount> PLN, <description> (kategoria banku: <bank_category>)"`,
  przycisk „Analizuj przez AI" → `/ai/text` → istniejący `showDraft()`.
  Po zapisie draftu wiersz przechodzi w `matched` lokalnie.

## Testy

`tests/test_bank_import.py`: parser na fragmencie z enterem w cudzysłowie i
kwotą z przecinkiem; matching na 1:1, 2 CSV vs 1 DB, brak, ±1 dzień.

## Poza zakresem

Mapowanie kategorii banku na kategorie użytkownika, pamiętanie importów,
zwroty/wpływy, inne banki.
