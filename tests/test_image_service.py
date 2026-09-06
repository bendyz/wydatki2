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


def test_zostawia_zdjecie_bez_exif_w_spokoju():
    contents = _jpeg_with_orientation(120, 60, orientation=1)

    result = _decode_upright(contents)

    assert result.shape[:2] == (60, 120)


def test_odrzuca_plik_ktory_nie_jest_obrazem():
    with pytest.raises(ValueError, match="Nie można odczytać obrazu"):
        _decode_upright(b"to nie jest obraz")
