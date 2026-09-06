"""
Regresja detekcji paragonu na prawdziwych zdjęciach.

Odpowiednik `ReceiptDetectionTest.kt` z repo androidowego — te same zdjęcia, te same
oznaczenia i te same progi. To jedyne, co pilnuje, żeby obie implementacje się nie
rozjechały.

Metryką jest IoU prostokąta opisanego na wykrytym czworokącie z ręcznym oznaczeniem.
To proxy: mierzy „czy wykadrujemy to, co trzeba", a nie dokładność co do piksela.

UWAGA: zdjęcia czytamy przez `cv2.imread`, które ignoruje EXIF — tak samo jak
`BitmapFactory` po stronie Androida, względem którego powstały oznaczenia. Korekta
orientacji z `image_service` NIE może tu wejść.
"""
import os
from pathlib import Path

import cv2
import pytest

from app.services.receipt_detection import find_receipt_quad
from tests.conftest import DEFAULT_SET

DEFAULT_THRESHOLD = 0.80


def bounding_box(quad) -> tuple[float, float, float, float]:
    """Prostokąt opisany na czworokącie: (x0, y0, x1, y1)."""
    xs, ys = quad[:, 0], quad[:, 1]
    return float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())


def iou(a, b) -> float:
    """Intersection over Union dwóch prostokątów (x0, y0, x1, y1)."""
    width = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    height = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    common = width * height
    total = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - common
    return common / total if total > 0 else 0.0


def photo_names() -> list[str]:
    """
    Nazwy zdjęć do parametryzacji.

    Czytane przy zbieraniu testów, a więc zanim zadziała jakikolwiek fixture — dlatego
    ścieżka jest tu rozwiązywana drugi raz, zamiast przez `receipt_set_dir`. Pusta lista
    znaczy „brak zestawu"; samo pominięcie robi wtedy fixture w każdym teście.
    """
    root = Path(os.environ.get("RECEIPT_TEST_SET", DEFAULT_SET)) / "receipts"
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.glob("*.jpg"))


@pytest.mark.parametrize("photo", photo_names())
def test_wykrywa_paragon_zgodnie_z_oznaczeniem(photo, receipt_set_dir, annotations):
    meta = annotations.get(photo)
    if meta is None:
        pytest.skip(f"{photo} nie ma oznaczenia w oczekiwane_paragony.json")

    image = cv2.imread(str(receipt_set_dir / "receipts" / photo), cv2.IMREAD_COLOR)
    assert image is not None, f"Nie dało się zdekodować {photo}"
    height, width = image.shape[:2]

    quad = find_receipt_quad(image)

    if quad is None:
        assert meta.get("dopuszczalny_brak", False), (
            f"{photo} [{meta['tlo']}]: nie znaleziono paragonu, "
            "a to zdjęcie nie jest oznaczone jako dopuszczalny brak"
        )
        return

    expected = (
        meta["box"][0] * width, meta["box"][1] * height,
        meta["box"][2] * width, meta["box"][3] * height,
    )
    threshold = meta.get("prog", DEFAULT_THRESHOLD)
    score = iou(bounding_box(quad), expected)
    assert score >= threshold, (
        f"{photo} [{meta['tlo']}]: IoU {score:.3f} poniżej progu {threshold:.2f}"
    )
