"""
Testy endpointowe flagi `already_cropped`.

Nic innego w `tests/` nie zauważyłoby, gdyby ktoś refaktorujący `ai.py` albo
`receipts.py` zgubił parametr `Form(...)` — a trybem awarii jest ciche
niszczenie zdjęć (patrz `tests/test_receipt_detection.py` i uzasadnienie xfail
tam). Testy tutaj mockują `save_and_process_receipt_image`, żeby nie dotykać
dysku ani OpenRouter, i sprawdzają tylko, że wartość flagi z multipart
faktycznie dociera do tej funkcji.
"""
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints.auth import get_current_user
from app.db.session import get_db
from app.main import app
from app.schemas.ai_draft import ExpenseDraft

FAKE_USER = SimpleNamespace(id=1, email="test@example.com")


@pytest.fixture
def client():
    def _fake_get_db():
        yield MagicMock()

    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    app.dependency_overrides[get_db] = _fake_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)


def _upload(client, already_cropped: bool | None):
    data = {}
    if already_cropped is not None:
        data["already_cropped"] = "true" if already_cropped else "false"
    files = {"file": ("paragon.jpg", b"tresc-nieistotna", "image/jpeg")}

    fake_draft = ExpenseDraft(amount=12.34, date=date(2026, 1, 1))
    with patch(
        "app.api.v1.endpoints.ai.save_and_process_receipt_image",
        new_callable=AsyncMock,
        return_value="uploads/receipts/0/x.jpg",
    ) as mocked_save, patch(
        "app.api.v1.endpoints.ai.parse_receipt_image",
        new_callable=AsyncMock,
        return_value=fake_draft,
    ):
        response = client.post("/api/v1/ai/receipt", data=data, files=files)
    return response, mocked_save


def test_ai_receipt_z_flaga_already_cropped_przekazuje_true(client):
    response, mocked_save = _upload(client, True)

    assert response.status_code == 200, response.text
    mocked_save.assert_awaited_once()
    _, kwargs = mocked_save.call_args
    assert kwargs["already_cropped"] is True


def test_ai_receipt_bez_flagi_przekazuje_false(client):
    response, mocked_save = _upload(client, None)

    assert response.status_code == 200, response.text
    mocked_save.assert_awaited_once()
    _, kwargs = mocked_save.call_args
    assert kwargs["already_cropped"] is False


def _upload_expense_receipt(client, already_cropped: bool | None):
    data = {}
    if already_cropped is not None:
        data["already_cropped"] = "true" if already_cropped else "false"
    files = {"file": ("paragon.jpg", b"tresc-nieistotna", "image/jpeg")}

    fake_expense = SimpleNamespace(id=1, receipt_image_path=None)
    with patch(
        "app.api.v1.endpoints.receipts.save_and_process_receipt_image",
        new_callable=AsyncMock,
        return_value="uploads/receipts/1/x.jpg",
    ) as mocked_save, patch(
        "app.api.v1.endpoints.receipts.get_expense",
        return_value=fake_expense,
    ):
        response = client.post(
            "/api/v1/receipts/1/receipt", data=data, files=files
        )
    return response, mocked_save


def test_receipts_upload_z_flaga_already_cropped_przekazuje_true(client):
    response, mocked_save = _upload_expense_receipt(client, True)

    assert response.status_code == 201, response.text
    mocked_save.assert_awaited_once()
    _, kwargs = mocked_save.call_args
    assert kwargs["already_cropped"] is True


def test_receipts_upload_bez_flagi_przekazuje_false(client):
    response, mocked_save = _upload_expense_receipt(client, None)

    assert response.status_code == 201, response.text
    mocked_save.assert_awaited_once()
    _, kwargs = mocked_save.call_args
    assert kwargs["already_cropped"] is False
