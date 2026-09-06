"""Testy pipeline'u przetwarzania zdjęcia paragonu."""
import io

import numpy as np
import pytest
from PIL import Image

from app.services.image_service import _decode_upright


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
