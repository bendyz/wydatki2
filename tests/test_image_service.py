"""Testy pipeline'u przetwarzania zdjęcia paragonu."""
import io
from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image

from app.services.image_service import _decode_upright, _process_and_save
from app.services.receipt_detection import Detection


def _jpeg_with_orientation(width: int, height: int, orientation: int) -> bytes:
    """Zdjęcie z tagiem EXIF Orientation — tak jak przychodzi z telefonu."""
    image = Image.new("RGB", (width, height), (200, 200, 200))
    exif = image.getexif()
    exif[274] = orientation  # 274 = Orientation
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def test_prostuje_orientacje_z_exif():
    """Orientation=6 znaczy „obróć o 90°" — po dekodowaniu boki muszą się zamienić."""
    contents = _jpeg_with_orientation(120, 60, orientation=6)

    result = _decode_upright(contents)

    assert result.shape[:2] == (120, 60), (
        f"Oczekiwano obrotu do 120x60, dostałem {result.shape[1]}x{result.shape[0]}"
    )


def test_zostawia_zdjecie_z_orientacja_neutralna_w_spokoju():
    """Orientation=1 to orientacja neutralna (nie brak EXIF) — obraz nie powinien się obrócić."""
    contents = _jpeg_with_orientation(120, 60, orientation=1)

    result = _decode_upright(contents)

    assert result.shape[:2] == (60, 120)


def test_odrzuca_plik_ktory_nie_jest_obrazem():
    with pytest.raises(ValueError, match="Nie można odczytać obrazu"):
        _decode_upright(b"to nie jest obraz")


def test_odrzuca_obciety_plik_z_poprawnym_naglowkiem():
    """Nagłówek JPEG poprawny, ale ciało ucięte — dekodowanie pikseli musi rzucić ValueError, a nie 500."""
    contents = _jpeg_with_orientation(120, 60, orientation=1)
    truncated = contents[: len(contents) // 2]

    with pytest.raises(ValueError, match="Nie można odczytać obrazu"):
        _decode_upright(truncated)


def test_odrzuca_gdy_konwersja_do_rgb_rzuca_oserror(monkeypatch):
    """
    `image.convert("RGB")` musi być chronione tym samym try/except co reszta dekodowania.

    `ImageOps.exif_transpose` w dzisiejszym Pillow wymusza pełne dekodowanie pikseli
    (`image.load()`) zanim w ogóle wróci, więc obcięty plik z tagiem EXIF zawsze
    wybucha wcześniej i ten konkretny defekt nie ujawnia się empirycznie na
    obciętych plikach. Ten test nie zależy od tego szczegółu implementacyjnego:
    podstawia obiekt, którego `convert()` rzuca `OSError` dopiero na końcowym
    kroku, i sprawdza, że mimo to wychodzi `ValueError`, a nie nieprzechwycony
    wyjątek.
    """

    class _ObrazZeZlymiPikselami:
        def convert(self, mode):
            raise OSError("uszkodzone dane pikseli")

    monkeypatch.setattr(
        "app.services.image_service.Image.open",
        lambda _buffer: _ObrazZeZlymiPikselami(),
    )
    monkeypatch.setattr(
        "app.services.image_service.ImageOps.exif_transpose",
        lambda image: image,
    )

    with pytest.raises(ValueError, match="Nie można odczytać obrazu"):
        _decode_upright(b"tresc bez znaczenia, Image.open jest podstawiony")


def test_flaga_already_cropped_pomija_detekcje(tmp_path):
    contents = _jpeg_with_orientation(120, 60, orientation=1)
    target = tmp_path / "wynik.jpg"

    with patch("app.services.image_service.crop_receipt") as detektor:
        result = _process_and_save(contents, str(target), already_cropped=True, expense_id=1)

    detektor.assert_not_called()
    assert result is None
    assert target.exists()


def test_bez_flagi_detekcja_jest_wolana(tmp_path):
    contents = _jpeg_with_orientation(120, 60, orientation=1)
    target = tmp_path / "wynik.jpg"
    fake = Detection(score=0.42, frame_ratio=0.5, out_size=(80, 40))

    with patch("app.services.image_service.crop_receipt") as detektor:
        detektor.return_value = (np.zeros((40, 80, 3), np.uint8), fake)
        result = _process_and_save(contents, str(target), already_cropped=False, expense_id=1)

    detektor.assert_called_once()
    assert result == fake
    assert target.exists()


def test_blad_opencv_nie_przerywa_zapisu(tmp_path):
    """Wyjątek z detekcji degraduje do obrazu nieskadrowanego — upload musi przejść."""
    import cv2

    contents = _jpeg_with_orientation(120, 60, orientation=1)
    target = tmp_path / "wynik.jpg"

    with patch("app.services.image_service.crop_receipt", side_effect=cv2.error("bum")):
        result = _process_and_save(contents, str(target), already_cropped=False, expense_id=1)

    assert result is None
    assert target.exists(), "Plik musi powstać mimo błędu detekcji"


def test_loguje_rozne_komunikaty_dla_braku_kandydata_i_bledu_detekcji(tmp_path, caplog):
    """
    Log INFO musi rozróżniać „nie znalazłem" od „detekcja padła" — to jedyne
    źródło danych przy strojeniu progów (spec §5.3), więc nie mogą dzielić
    jednego komunikatu.
    """
    import cv2

    contents = _jpeg_with_orientation(120, 60, orientation=1)

    with caplog.at_level("INFO", logger="app.services.image_service"):
        with patch("app.services.image_service.crop_receipt", return_value=(np.zeros((40, 80, 3), np.uint8), None)):
            _process_and_save(
                contents, str(tmp_path / "brak.jpg"), already_cropped=False, expense_id=1
            )
        brak_kandydata_logi = [r.message for r in caplog.records]
        caplog.clear()

        with patch("app.services.image_service.crop_receipt", side_effect=cv2.error("bum")):
            _process_and_save(
                contents, str(tmp_path / "blad.jpg"), already_cropped=False, expense_id=2
            )
        blad_logi = [r.message for r in caplog.records if r.levelname == "INFO"]

    assert any("brak kandydata" in m for m in brak_kandydata_logi)
    assert not any("brak kandydata" in m for m in blad_logi)
    assert any("błąd" in m for m in blad_logi)
