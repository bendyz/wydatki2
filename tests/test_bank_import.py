"""
Parser mBank + matching wyciągu z bazą — bez OpenRouter, bez dysku.

Matching dostaje gotową listę wydatków (SimpleNamespace), więc test nie
potrzebuje SQLite; endpoint pokrywa tylko to, że plik dociera do parsera.
"""
from datetime import date
from types import SimpleNamespace

import pytest

from app.services.bank_import import (
    BankOperation,
    match_operations,
    parse_mbank_csv,
)

MBANK_SAMPLE = (
    "﻿mBank S.A. Bankowość Detaliczna;\r\n"
    "\r\n"
    "#Waluta;#Wpływy;#Wydatki;\r\n"
    "PLN;50,00;-132,72;\r\n"
    "\r\n"
    "#Data operacji;#Opis operacji;#Rachunek;#Kategoria;#Kwota;\r\n"
    '2026-09-18;"LIDL  ZAKUP PRZY UŻYCIU KARTY W KRAJU          ";"Moje konto";"Żywność i chemia domowa";-118,72 PLN;;\r\n'
    '2026-09-19;"Skycash  WWW.SKYCASH.COM\r\n'
    '     BLIK ZAKUP E-COMMERCE   ";"Moje konto";"Przejazdy";-14,00 PLN;;\r\n'
    '2026-09-19;"PRZELEW PRZYCHODZĄCY";"Moje konto";"Wpływy";50,00 PLN;;\r\n'
    "\r\n"
).encode("utf-8")


def test_parse_mbank_handles_newline_in_quotes_and_skips_income():
    ops, skipped_income = parse_mbank_csv(MBANK_SAMPLE)
    assert skipped_income == 1
    assert [o.amount for o in ops] == [118.72, 14.00]
    assert ops[0].date == date(2026, 9, 18)
    assert ops[0].description == "LIDL ZAKUP PRZY UŻYCIU KARTY W KRAJU"
    assert ops[0].bank_category == "Żywność i chemia domowa"
    assert ops[1].description == "Skycash WWW.SKYCASH.COM BLIK ZAKUP E-COMMERCE"


def test_parse_mbank_cp1250_fallback():
    data = MBANK_SAMPLE.decode("utf-8-sig").encode("cp1250")
    ops, _ = parse_mbank_csv(data)
    assert ops[0].bank_category == "Żywność i chemia domowa"


def test_parse_mbank_without_table_raises():
    with pytest.raises(ValueError):
        parse_mbank_csv(b"nic tu nie ma;\r\n")


def _op(d, amount, desc="x"):
    return BankOperation(date=d, amount=amount, description=desc, bank_category="")


def _exp(id, d, amount, desc="y"):
    return SimpleNamespace(id=id, date=d, amount=amount, description=desc, category_name="Kat")


def test_match_statuses():
    d = date(2026, 9, 18)
    ops = [
        _op(d, 10.0),               # 1:1 → matched
        _op(d, 20.0),               # 2 w CSV, 1 w bazie → ambiguous
        _op(d, 20.0),
        _op(d, 21.37),              # brak → missing
        _op(d, 30.0),               # baza dzień później → matched (±1)
        _op(d, 40.0),               # baza 2 dni później → missing
    ]
    expenses = [
        _exp(1, d, 10.0),
        _exp(2, d, 20.0),
        _exp(3, d.replace(day=19), 30.0),
        _exp(4, d.replace(day=20), 40.0),
        _exp(5, d, 99.0),
    ]
    rows = match_operations(ops, expenses)
    assert [r.status for r in rows] == [
        "matched", "ambiguous", "ambiguous", "missing", "matched", "missing",
    ]
    assert [c.id for c in rows[1].candidates] == [2]
    assert rows[4].candidates[0].id == 3
    assert rows[3].candidates == []


def test_match_two_in_csv_two_in_db_is_matched():
    d = date(2026, 9, 18)
    rows = match_operations(
        [_op(d, 10.0), _op(d, 10.0)],
        [_exp(1, d, 10.0), _exp(2, d, 10.0)],
    )
    assert [r.status for r in rows] == ["matched", "matched"]


def test_match_float_rounding():
    d = date(2026, 9, 18)
    rows = match_operations([_op(d, 0.1 + 0.2)], [_exp(1, d, 0.3)])
    assert rows[0].status == "matched"


# ---------- endpoint ----------

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.v1.endpoints.auth import get_current_user
from app.db.session import get_db
from app.main import app


@pytest.fixture
def client():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [
        _exp(7, date(2026, 9, 18), 118.72, "Lidl")
    ]
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)


def test_endpoint_returns_rows_and_summary(client):
    r = client.post(
        "/api/v1/import/bank-csv",
        files={"file": ("ops.csv", MBANK_SAMPLE, "text/csv")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"] == {"matched": 1, "ambiguous": 0, "missing": 1, "skipped_income": 1}
    assert body["rows"][0]["candidates"][0]["id"] == 7


def test_endpoint_unknown_bank(client):
    r = client.post(
        "/api/v1/import/bank-csv",
        files={"file": ("ops.csv", MBANK_SAMPLE, "text/csv")},
        data={"bank": "pko"},
    )
    assert r.status_code == 400


def test_endpoint_bad_file(client):
    r = client.post("/api/v1/import/bank-csv", files={"file": ("x.csv", b"foo;bar", "text/csv")})
    assert r.status_code == 400
