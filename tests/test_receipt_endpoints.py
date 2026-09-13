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


# --- podgląd przetworzonego zdjęcia w drafcie (include_preview) ---------------
#
# Draft powstaje, zanim wydatek istnieje, więc nie ma czego pytać przez
# GET /receipts/{id}/receipt. Obraz wraca w tej samej odpowiedzi, ale tylko
# na żądanie — Android nie ma po co ściągać pół megabajta na każdy skan.


def _upload_with_preview(client, image_path: str, include_preview: bool | None):
    data = {}
    if include_preview is not None:
        data["include_preview"] = "true" if include_preview else "false"
    files = {"file": ("paragon.jpg", b"tresc-nieistotna", "image/jpeg")}

    fake_draft = ExpenseDraft(amount=12.34, date=date(2026, 1, 1))
    with patch(
        "app.api.v1.endpoints.ai.save_and_process_receipt_image",
        new_callable=AsyncMock,
        return_value=image_path,
    ), patch(
        "app.api.v1.endpoints.ai.parse_receipt_image",
        new_callable=AsyncMock,
        return_value=fake_draft,
    ):
        return client.post("/api/v1/ai/receipt", data=data, files=files)


def test_include_preview_zwraca_przetworzony_obraz_jako_data_url(client, tmp_path):
    """Front ma dostać dokładnie te bajty, które backend zapisał po przetworzeniu."""
    import base64

    processed = tmp_path / "przetworzony.jpg"
    processed.write_bytes(b"udawane-bajty-jpeg")

    response = _upload_with_preview(client, str(processed), include_preview=True)

    assert response.status_code == 200, response.text
    preview = response.json()["receipt_preview"]
    assert preview.startswith("data:image/jpeg;base64,")
    odkodowane = base64.b64decode(preview.split(",", 1)[1])
    assert odkodowane == b"udawane-bajty-jpeg"


def test_bez_include_preview_obraz_nie_wraca(client, tmp_path):
    processed = tmp_path / "przetworzony.jpg"
    processed.write_bytes(b"udawane-bajty-jpeg")

    response = _upload_with_preview(client, str(processed), include_preview=None)

    assert response.status_code == 200, response.text
    assert response.json()["receipt_preview"] is None


def test_brak_pliku_nie_wywala_odpowiedzi(client, tmp_path):
    """Zniknięty plik tymczasowy degraduje do braku podglądu, nie do 500."""
    response = _upload_with_preview(
        client, str(tmp_path / "nie-ma-mnie.jpg"), include_preview=True
    )

    assert response.status_code == 200, response.text
    assert response.json()["receipt_preview"] is None


def test_draft_z_tekstu_nigdy_nie_ma_podgladu(client):
    """/ai/text nie ma żadnego zdjęcia — pole musi zostać puste."""
    fake_draft = ExpenseDraft(amount=9.99, date=date(2026, 1, 1))
    with patch(
        "app.api.v1.endpoints.ai.parse_text_expense",
        new_callable=AsyncMock,
        return_value=fake_draft,
    ):
        response = client.post("/api/v1/ai/text", json={"text": "kawa za 9.99"})

    assert response.status_code == 200, response.text
    assert response.json()["receipt_preview"] is None
