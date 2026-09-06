# Port detekcji paragonu do backendu — plan implementacji

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backend sam wykrywa i prostuje paragon na wgranym zdjęciu, zamiast polegać na tym, że zrobiła to aplikacja androidowa.

**Architecture:** Nowy moduł czystych funkcji OpenCV (`app/services/receipt_detection.py`, numpy wchodzi → numpy wychodzi, zero I/O) jest wołany przez `image_service.py` jako krok **przed** skalowaniem i binaryzacją. Klient może pominąć detekcję flagą `already_cropped` w multiparcie. Cała praca OpenCV schodzi z pętli zdarzeń przez `asyncio.to_thread`.

**Tech Stack:** Python 3.12, FastAPI, `opencv-python-headless` 4.13, numpy 2.4, Pillow (nowa zależność), pytest (pierwsze testy w tym repo).

**Spec:** [`docs/superpowers/specs/2026-09-06-port-detekcji-paragonu-design.md`](../specs/2026-09-06-port-detekcji-paragonu-design.md)

**Dokument źródłowy** (opis algorytmu i szkic): [`docs/port-detekcji-paragonu-z-androida.md`](../../port-detekcji-paragonu-z-androida.md)

## Global Constraints

- **Gałąź:** `feature/port-detekcji-paragonu`. Nie mergować do `master` bez osobnej decyzji.
- **Identyfikatory angielskie, docstringi i komunikaty polskie** — konwencja całego repo. Szkic §9.6 dokumentu źródłowego używa nazw polskich; tabela mapowania jest w specu §3.2 i trzeba się jej trzymać co do litery.
- **Logowanie:** `logger = logging.getLogger(__name__)` na moduł, komunikaty po polsku (wzór: `app/worker/scheduler.py`, `app/services/ai_service.py`).
- **`pytest` NIE trafia do `requirements.txt`** — ten plik Dockerfile instaluje do obrazu produkcyjnego. Zależności deweloperskie idą do nowego `requirements-dev.txt`.
- **Progi detektora są stałymi modułu**, nie wchodzą do `data/config/config.yaml`.
- **Zestaw testowy jest poza gitem** — 18 zdjęć w `~/Projekty/wydatki2.0android/app/src/androidTest/assets/`. Brak zestawu = `pytest.skip`, nigdy błąd.
- **Wartości progów kopiowane dosłownie ze specu §3.3:** `WORKING_LONG_EDGE = 640.0`, `MIN_FRAME_RATIO = 0.06`, `MAX_FRAME_RATIO = 0.95`, `MIN_RECTANGULARITY = 0.70`, `MIN_ANGLE_REGULARITY = 0.45`, `MIN_CONTRAST = 0.02`, `WEIGHT_CHROMA = 3.0`.
- **Wyjątek z OpenCV nigdy nie przerywa uploadu** — degradacja do obrazu nieskadrowanego plus `logger.warning`.
- Środowisko: `source .venv/bin/activate` przed każdym uruchomieniem `pytest` i skryptów.

---

## File Structure

| Plik | Odpowiedzialność | Zadanie |
|---|---|---|
| `requirements-dev.txt` | **Create** — zależności deweloperskie (pytest), poza obrazem produkcyjnym | 1 |
| `pytest.ini` | **Create** — `pythonpath = .`, bez tego `import app.*` w testach nie zadziała | 1 |
| `tests/conftest.py` | **Create** — lokalizacja zestawu zdjęć, wspólne fixture, pomijanie bez zestawu | 1 |
| `tests/test_receipt_detection.py` | **Create** — regresja IoU na 18 zdjęciach + test powtórnego przebiegu | 1, 3 |
| `app/services/receipt_detection.py` | **Create** — algorytm: czyste funkcje numpy→numpy, zero I/O | 2 |
| `tests/test_image_service.py` | **Create** — EXIF, degradacja przy błędzie OpenCV, flaga | 4, 5 |
| `app/services/image_service.py` | **Modify** — EXIF, wpięcie detekcji, log metryk, `asyncio.to_thread` | 4, 5 |
| `app/api/v1/endpoints/ai.py` | **Modify:54** — flaga `already_cropped` w multiparcie | 6 |
| `app/api/v1/endpoints/receipts.py` | **Modify:66** — flaga `already_cropped` w multiparcie | 6 |
| `docs/api.json` | **Modify** — regeneracja przez `scripts/export_openapi.py` | 6 |
| `scripts/porownaj_binaryzacje.py` | **Create** — jednorazowy pomiar A/B `adaptiveThreshold` przez model vision | 7 |
| `requirements.txt` | **Modify** — dochodzi `Pillow` | 4 |
| `CLAUDE.md`, `VERSION`, dokument źródłowy | **Modify** — aktualizacja opisu, `0.5.4` → `0.5.5` | 8 |

Zadania 1–3 dotykają wyłącznie nowego modułu i testów — nie ruszają niczego, co dziś działa. Ryzyko dla produkcji zaczyna się dopiero w zadaniu 4.

---

### Task 1: Szkielet testowy i regresja IoU (RED)

Test powstaje **przed** detektorem i ma nie przejść — to jest jego zadanie w tym kroku.

**Files:**
- Create: `requirements-dev.txt`
- Create: `pytest.ini`
- Create: `tests/conftest.py`
- Create: `tests/test_receipt_detection.py`

**Interfaces:**
- Consumes: nic (pierwsze zadanie).
- Produces: fixture `receipt_set_dir` (zwraca `Path` do katalogu `assets/` repo androidowego albo pomija test), fixture `annotations` (`dict[str, dict]` z `oczekiwane_paragony.json`), helper `bounding_box(quad) -> tuple[float, float, float, float]` i `iou(a, b) -> float` używane też w zadaniu 3. Testy oczekują z zadania 2: `app.services.receipt_detection.find_receipt_quad(bgr) -> np.ndarray | None`.

**Format oznaczeń** (`oczekiwane_paragony.json`, 18 wpisów, sprawdzony w repo androidowym):

```json
{
  "01.jpg": { "tlo": "czarny blat", "box": [0.1, 0.25, 0.85, 0.93] },
  "02.jpg": { "tlo": "czarny blat, obrocony", "box": [...], "prog": 0.72 },
  "08.jpg": { "tlo": "...", "box": [...], "dopuszczalny_brak": true },
  "18.jpg": { "tlo": "...", "box": [...], "dopuszczalny_brak": true, "prog": 0.65 }
}
```

`box` to `[x0, y0, x1, y1]` we współrzędnych **względnych 0–1**. Domyślny próg `0.80`. Nadpisania istnieją tylko dla `02.jpg` (0.72), `09.jpg` (0.70), `18.jpg` (0.65); `dopuszczalny_brak` dla `08.jpg` i `18.jpg`. Te wartości muszą zostać identyczne jak po stronie Androida — inaczej test przestaje mierzyć rozjazd implementacji.

**KRYTYCZNE — nie korygować EXIF w tym teście.** Android dekoduje zdjęcia przez `BitmapFactory.decodeStream`, które ignoruje orientację EXIF, i oznaczenia `box` powstały względem tak zdekodowanego obrazu. Test w Pythonie musi więc czytać przez `cv2.imread` (też ignoruje EXIF). Korekta EXIF z zadania 4 dotyczy pipeline'u uploadu, **nie** tego testu — dołożenie jej tutaj obróci część zdjęć i oznaczenia przestaną pasować.

- [ ] **Step 1: Utwórz `requirements-dev.txt`**

```
# Zależności deweloperskie — NIE instalowane do obrazu (Dockerfile bierze requirements.txt)
-r requirements.txt
pytest==8.4.2
```

`pytest-asyncio` nie jest potrzebne: testy celują w funkcje synchroniczne
(`_decode_upright`, `_process_and_save`, detektor), a nie w `async def`. Spec §6.1 wymienia
je zapobiegawczo — nie dodawaj zależności, dla której nie ma testu.

- [ ] **Step 2: Utwórz `pytest.ini`**

```ini
[pytest]
pythonpath = .
testpaths = tests
```

Bez `pythonpath = .` testy nie zaimportują `app.*`: repo nie jest pakietem instalowalnym,
nie ma `pyproject.toml` ani `setup.cfg`, a pytest wkłada do `sys.path` katalog testu, nie
katalog repo. To jedyny powód istnienia tego pliku.

- [ ] **Step 3: Utwórz `tests/conftest.py`**

```python
"""Wspólne fixture dla testów. Zestaw zdjęć jest poza gitem — bez niego testy się pomijają."""
import json
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SET = REPO_ROOT.parent / "wydatki2.0android/app/src/androidTest/assets"


@pytest.fixture(scope="session")
def receipt_set_dir() -> Path:
    """Katalog `assets/` repo androidowego: zdjęcia w `receipts/`, oznaczenia obok."""
    candidate = Path(os.environ.get("RECEIPT_TEST_SET", DEFAULT_SET))
    if not (candidate / "receipts").is_dir():
        pytest.skip(
            f"Brak zestawu zdjęć w {candidate}/receipts — jest lokalny, poza gitem. "
            "Ścieżkę można wskazać zmienną RECEIPT_TEST_SET."
        )
    return candidate


@pytest.fixture(scope="session")
def annotations(receipt_set_dir: Path) -> dict:
    """Ręczne oznaczenia paragonów — ten sam plik, którego używa test androidowy."""
    return json.loads(
        (receipt_set_dir / "oczekiwane_paragony.json").read_text(encoding="utf-8")
    )
```

- [ ] **Step 4: Utwórz `tests/test_receipt_detection.py`**

```python
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
```

- [ ] **Step 5: Zainstaluj zależności i uruchom test — musi paść na imporcie**

```bash
source .venv/bin/activate && pip install -r requirements-dev.txt
python -m pytest tests/test_receipt_detection.py -v
```

Oczekiwane: **błąd zbierania** — `ModuleNotFoundError: No module named 'app.services.receipt_detection'`.

Dwie inne odpowiedzi znaczą kłopot, nie sukces:
- `ModuleNotFoundError: No module named 'app'` → `pytest.ini` nie działa; sprawdź, czy uruchamiasz z katalogu repo i czy plik ma sekcję `[pytest]`.
- „no tests ran" albo pusty zestaw parametrów → nie znaleziono zdjęć. Sprawdź `ls ~/Projekty/wydatki2.0android/app/src/androidTest/assets/receipts | wc -l` (ma być 18) i dopiero wtedy idź dalej. Test, który się pomija, niczego nie pilnuje.

- [ ] **Step 6: Commit**

```bash
git add requirements-dev.txt pytest.ini tests/conftest.py tests/test_receipt_detection.py
git commit -m "test: regresja detekcji paragonu na zestawie z repo androidowego

Pierwsze testy w tym repo. Zestaw 18 zdjęć jest poza gitem — bez niego
testy się pomijają. Progi i oznaczenia wspólne z testem androidowym.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Gts3LZVnfDTHq7d2fC3PAe"
```

---

### Task 2: Moduł detekcji (GREEN)

Wierne tłumaczenie `ReceiptQuadDetector.kt` według szkicu §9.6 dokumentu źródłowego, z nazwami przemapowanymi wg specu §3.2.

**Files:**
- Create: `app/services/receipt_detection.py`
- Test: `tests/test_receipt_detection.py` (napisany w zadaniu 1)

**Interfaces:**
- Consumes: testy z zadania 1.
- Produces:
  - `Detection(NamedTuple)` z polami `score: float`, `frame_ratio: float`, `out_size: tuple[int, int]`
  - `find_receipt_quad(bgr: np.ndarray) -> np.ndarray | None` — 4×2 `float32`, kolejność TL, TR, BR, BL
  - `deskew(bgr: np.ndarray, quad: np.ndarray) -> np.ndarray`
  - `crop_receipt(bgr: np.ndarray) -> tuple[np.ndarray, Detection | None]`

  Zadanie 5 woła wyłącznie `crop_receipt`. Zadanie 3 woła `find_receipt_quad` i `crop_receipt`.

**Dlaczego `_best_candidate` jest osobno:** `find_receipt_quad` zwraca sam czworokąt, ale `crop_receipt` musi oddać też metryki do logu (spec §3.1) — bez wspólnej funkcji wewnętrznej trzeba by liczyć wszystko dwa razy.

- [ ] **Step 1: Utwórz `app/services/receipt_detection.py`**

```python
"""
Wykrywanie i prostowanie paragonu na zdjęciu.

Port `ReceiptQuadDetector.kt` z aplikacji androidowej — opis algorytmu i uzasadnienie
progów: `docs/port-detekcji-paragonu-z-androida.md`. Progi i wagi muszą zostać zgodne
z tamtą implementacją, inaczej wspólny test regresyjny przestaje cokolwiek znaczyć.

Moduł jest czysty: numpy wchodzi, numpy wychodzi. Bez I/O, bez logowania, bez FastAPI.
"""
from typing import NamedTuple, Optional

import cv2
import numpy as np

# Stała rozdzielczość robocza to warunek poprawności, nie optymalizacja: progi Canny'ego
# i rozmiary jąder morfologicznych są wyrażone w pikselach.
WORKING_LONG_EDGE = 640.0
MIN_FRAME_RATIO = 0.06
MAX_FRAME_RATIO = 0.95
MIN_RECTANGULARITY = 0.70
MIN_ANGLE_REGULARITY = 0.45
MIN_CONTRAST = 0.02
WEIGHT_CHROMA = 3.0


class Detection(NamedTuple):
    """Metryki wybranego kandydata — jedyny ślad diagnostyczny, bo oryginał nie zostaje."""

    score: float
    frame_ratio: float
    out_size: tuple[int, int]


def _luma_and_chroma(bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Jasność i odległość od szarości. Paragon jest jasny ORAZ nienasycony."""
    y, u, v = cv2.split(cv2.cvtColor(bgr, cv2.COLOR_BGR2YUV))
    chroma = np.maximum(
        cv2.absdiff(u, np.full_like(u, 128)),
        cv2.absdiff(v, np.full_like(v, 128)),
    )
    return y, chroma


def _paper_map(luma: np.ndarray, chroma: np.ndarray) -> np.ndarray:
    """Mapa „papierowości". Waga 3.0 — przy 1.0 ciepłe drewno wchodziło w plamę paragonu."""
    matched = cv2.resize(chroma, (luma.shape[1], luma.shape[0]))
    return cv2.addWeighted(luma, 1.0, matched, -WEIGHT_CHROMA, 0.0)


def _collect_contours(working: np.ndarray, paper: np.ndarray) -> list:
    """Dwa niezależne źródła kandydatów — żadne samo nie wystarcza, więc konkurują punktacją."""
    blurred = cv2.GaussianBlur(working, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    edges = cv2.dilate(edges, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
    # RETR_LIST, nie RETR_EXTERNAL: paragon trzymany w dłoni leży wewnątrz obrysu ręki
    from_edges, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    _, mask = cv2.threshold(
        cv2.GaussianBlur(paper, (5, 5), 0), 0, 255,
        cv2.THRESH_BINARY | cv2.THRESH_OTSU,
    )
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    )
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    )
    from_blob, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return list(from_edges) + list(from_blob)


def _quad_from_contour(contour: np.ndarray) -> Optional[np.ndarray]:
    """Epsilon szukany bisekcją — sztywne 0.02 gubi pogięty paragon."""
    hull = cv2.convexHull(contour)
    if len(hull) < 4:
        return None
    perimeter = cv2.arcLength(hull, True)
    if perimeter <= 0:
        return None

    lo, hi = 0.005, 0.25
    for _ in range(24):
        middle = (lo + hi) / 2
        approx = cv2.approxPolyDP(hull, middle * perimeter, True)
        if len(approx) > 4:
            lo = middle
        elif len(approx) < 4:
            hi = middle
        else:
            return approx.reshape(4, 2).astype(np.float64)

    return cv2.boxPoints(cv2.minAreaRect(hull)).astype(np.float64)


def _angle_regularity(corners: np.ndarray) -> float:
    """1.0 gdy wszystkie kąty proste, 0.0 gdy czworokąt się zapada."""
    worst = 0.0
    for i in range(4):
        a = corners[(i + 3) % 4] - corners[i]
        b = corners[(i + 1) % 4] - corners[i]
        da, db = np.linalg.norm(a), np.linalg.norm(b)
        if da == 0 or db == 0:
            return 0.0
        worst = max(worst, abs(float(a @ b) / (da * db)))
    return max(0.0, 1.0 - worst)


def _surround_contrast(
    corners: np.ndarray, paper: np.ndarray, kernel: np.ndarray
) -> Optional[float]:
    """O ile „bardziej papierowe" jest wnętrze od pierścienia wokół niego."""
    mask = np.zeros(paper.shape, np.uint8)
    cv2.fillPoly(mask, [corners.astype(np.int32)], 255)
    if cv2.countNonZero(mask) == 0:
        return None
    inside = cv2.mean(paper, mask)[0]
    ring = cv2.subtract(cv2.dilate(mask, kernel), mask)
    outside = cv2.mean(paper, ring)[0] if cv2.countNonZero(ring) else 0.0
    return (inside - outside) / 255.0


def _score(rectangularity: float, angles: float, ratio: float, contrast: float) -> float:
    """Kąty decydują najmocniej, udział w kadrze ledwie przechyla szalę."""
    return rectangularity * angles**2 * ratio**0.25 * (contrast + 0.2) ** 0.5


def _order_corners(corners: np.ndarray) -> np.ndarray:
    """TL, TR, BR, BL — prostowanie perspektywy zakłada tę kolejność."""
    total, diff = corners[:, 0] + corners[:, 1], corners[:, 1] - corners[:, 0]
    return np.array([
        corners[np.argmin(total)], corners[np.argmin(diff)],
        corners[np.argmax(total)], corners[np.argmax(diff)],
    ], dtype=np.float32)


def _best_candidate(bgr: np.ndarray) -> Optional[tuple[np.ndarray, float, float]]:
    """Najlepiej oceniony czworokąt wraz z oceną i udziałem w kadrze."""
    luma, chroma = _luma_and_chroma(bgr)
    shrink = WORKING_LONG_EDGE / max(luma.shape[:2])
    working = (
        cv2.resize(luma, None, fx=shrink, fy=shrink, interpolation=cv2.INTER_AREA)
        if shrink < 1.0 else luma
    )
    scale = working.shape[1] / luma.shape[1]

    paper = _paper_map(working, chroma)
    frame_area = float(working.shape[0] * working.shape[1])
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31))

    best, best_score, best_ratio = None, 0.0, 0.0
    for contour in _collect_contours(working, paper):
        corners = _quad_from_contour(contour)
        if corners is None:
            continue

        area = abs(cv2.contourArea(corners.astype(np.float32)))
        ratio = area / frame_area
        if not (MIN_FRAME_RATIO <= ratio <= MAX_FRAME_RATIO):
            continue
        (_, (w, h), _) = cv2.minAreaRect(corners.astype(np.float32))
        if w * h <= 0:
            continue
        rectangularity = area / (w * h)
        if rectangularity < MIN_RECTANGULARITY:
            continue
        angles = _angle_regularity(corners)
        if angles < MIN_ANGLE_REGULARITY:
            continue
        # Kontrast na końcu — jako jedyny wymaga maski na cały kadr i dwóch przejść
        contrast = _surround_contrast(corners, paper, kernel)
        if contrast is None or contrast < MIN_CONTRAST:
            continue

        score = _score(rectangularity, angles, ratio, contrast)
        if score > best_score:
            best, best_score, best_ratio = corners, score, ratio

    if best is None:
        return None
    return _order_corners(best / scale), best_score, best_ratio


def find_receipt_quad(bgr: np.ndarray) -> Optional[np.ndarray]:
    """Rogi paragonu (TL, TR, BR, BL) we współrzędnych `bgr`, albo None."""
    found = _best_candidate(bgr)
    return None if found is None else found[0]


def deskew(bgr: np.ndarray, quad: np.ndarray) -> np.ndarray:
    """Prostuje czworokąt do prostokąta, na pełnej rozdzielczości oryginału."""
    tl, tr, br, bl = quad
    # Dłuższa z pary przeciwległych krawędzi: przy zdjęciu pod kątem bliższa krawędź
    # jest dłuższa i to ona wyznacza rozdzielczość, żeby nie tracić dalszej połowy.
    out_w = max(1, int(max(np.linalg.norm(tl - tr), np.linalg.norm(bl - br))))
    out_h = max(1, int(max(np.linalg.norm(tl - bl), np.linalg.norm(tr - br))))
    target = np.array(
        [[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]],
        dtype=np.float32,
    )
    return cv2.warpPerspective(bgr, cv2.getPerspectiveTransform(quad, target), (out_w, out_h))


def crop_receipt(bgr: np.ndarray) -> tuple[np.ndarray, Optional[Detection]]:
    """Wykadrowany paragon, albo oryginał gdy nic wiarygodnego nie widać."""
    found = _best_candidate(bgr)
    if found is None:
        return bgr, None
    quad, score, ratio = found
    cropped = deskew(bgr, quad)
    return cropped, Detection(
        score=score, frame_ratio=ratio, out_size=(cropped.shape[1], cropped.shape[0])
    )
```

- [ ] **Step 2: Uruchom testy z zadania 1**

```bash
source .venv/bin/activate && python -m pytest tests/test_receipt_detection.py -v
```

Oczekiwane: 18 testów, wszystkie PASS.

- [ ] **Step 3: Gdy któreś zdjęcie nie dobija do progu — porównaj z Androidem, nie obniżaj progu**

Spec §8 pkt 5 mówi to wprost: szkic §9.6 był uruchomiony wyłącznie na scenie syntetycznej, nigdy na prawdziwych zdjęciach. Rozjazd oznacza **błąd w tłumaczeniu**, a nie zbyt ostre kryterium.

Kolejność działania przy porażce:
1. Wypisz IoU dla zdjęcia (`pytest -v` już to pokazuje w komunikacie asercji).
2. Porównaj krok po kroku z `ReceiptQuadDetector.kt` w `~/Projekty/wydatki2.0android/app/src/main/java/com/bendyz/wydatki/ui/scan/` — najczęstsze źródła rozjazdu to kolejność argumentów w `addWeighted`, `findContours` zwracające w OpenCV 4.x dwie wartości zamiast trzech, i `float32` vs `float64` w `minAreaRect`.
3. Obniżenie progu wymaga osobnej decyzji człowieka i wpisu w dokumencie źródłowym. Nie rób tego samodzielnie — zatrzymaj się i zapytaj.

- [ ] **Step 4: Commit**

```bash
git add app/services/receipt_detection.py
git commit -m "feat: detekcja i prostowanie paragonu po stronie backendu

Port ReceiptQuadDetector.kt: mapa papierowości luma-3*chroma, dwa źródła
konturów, epsilon szukany bisekcją, cztery testy odsiewu i punktacja.
Czysty moduł numpy→numpy, bez I/O.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Gts3LZVnfDTHq7d2fC3PAe"
```

---

### Task 3: Test powtórnego przebiegu

Spec §6.3: dokument źródłowy §9.9 chce, żeby wykadrowany paragon podany ponownie zwrócił `None`, ale §9.2 mierzy coś przeciwnego (`udzial = 0.915`, poniżej progu 0.95 — kandydat przechodzi). Testujemy własność, która jest prawdziwa: **drugi przebieg jest praktycznie tożsamością**.

**Files:**
- Modify: `tests/test_receipt_detection.py` (dopisanie testu na końcu)

**Interfaces:**
- Consumes: `crop_receipt`, `find_receipt_quad` z zadania 2; `bounding_box`, `iou` z zadania 1.
- Produces: nic dla dalszych zadań.

- [ ] **Step 1: Dopisz test na końcu `tests/test_receipt_detection.py`**

```python
@pytest.mark.parametrize("photo", photo_names())
def test_powtorne_kadrowanie_niczego_nie_zjada(photo, receipt_set_dir, annotations):
    """
    Drugi przebieg na własnym wyjściu musi być praktycznie tożsamością.

    Dokument źródłowy §9.9 postuluje tu `None`, ale §9.2 mierzy, że kandydat przechodzi
    (udzial 0.915 < próg 0.95). Świadomie nie robimy strażnika z §9.2 — flaga
    `already_cropped` załatwia to po stronie API — więc test pilnuje tego, co faktycznie
    ma być prawdą: powtórka nie może obrazu zjadać ani skręcać.
    """
    meta = annotations.get(photo)
    if meta is None or meta.get("dopuszczalny_brak", False):
        pytest.skip(f"{photo}: brak oznaczenia albo dopuszczalny brak detekcji")

    image = cv2.imread(str(receipt_set_dir / "receipts" / photo), cv2.IMREAD_COLOR)
    first, detection = crop_receipt(image)
    if detection is None:
        pytest.skip(f"{photo}: pierwszy przebieg nic nie znalazł")

    second, _ = crop_receipt(first)

    height, width = first.shape[:2]
    shrink = iou(
        bounding_box_of_image(second), (0.0, 0.0, float(width), float(height))
    )
    assert shrink >= 0.98, (
        f"{photo}: powtórne kadrowanie zjadło obraz — pokrycie {shrink:.3f}, "
        f"{width}x{height} → {second.shape[1]}x{second.shape[0]}"
    )
```

- [ ] **Step 2: Dopisz brakujący helper obok `bounding_box` (góra pliku)**

```python
def bounding_box_of_image(image) -> tuple[float, float, float, float]:
    """Prostokąt całego obrazu — do porównania rozmiarów kolejnych przebiegów."""
    height, width = image.shape[:2]
    return 0.0, 0.0, float(width), float(height)
```

- [ ] **Step 3: Zaktualizuj import na górze pliku**

```python
from app.services.receipt_detection import crop_receipt, find_receipt_quad
```

- [ ] **Step 4: Uruchom**

```bash
source .venv/bin/activate && python -m pytest tests/test_receipt_detection.py -v
```

Oczekiwane: wszystkie PASS (część `test_powtorne_kadrowanie...` może być `skipped` dla `08.jpg` i `18.jpg`). Gdyby pokrycie wyszło poniżej 0.98, **nie obniżaj progu** — to znaczy, że powtórny przebieg realnie zjada obraz, czyli flaga `already_cropped` z zadania 6 przestaje być wygodą, a staje się koniecznością. Zatrzymaj się i zgłoś.

- [ ] **Step 5: Commit**

```bash
git add tests/test_receipt_detection.py
git commit -m "test: powtórne kadrowanie nie może zjadać obrazu

Dokument źródłowy postuluje idempotencję (None przy drugim przebiegu),
ale sam mierzy, że kandydat przechodzi. Test pilnuje własności prawdziwej:
drugi przebieg jest praktycznie tożsamością.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Gts3LZVnfDTHq7d2fC3PAe"
```

---

### Task 4: Korekta orientacji z EXIF

Pierwsze zadanie dotykające kodu produkcyjnego. `cv2.imdecode` ignoruje EXIF, więc zdjęcie z telefonu przychodzi w orientacji sensora — bez tego kadr poleciałby do modelu bokiem.

**Files:**
- Modify: `requirements.txt`
- Modify: `app/services/image_service.py`
- Create: `tests/test_image_service.py`

**Interfaces:**
- Consumes: nic z wcześniejszych zadań.
- Produces: `app.services.image_service._decode_upright(contents: bytes) -> np.ndarray` — dekoduje bajty do BGR z uwzględnieniem EXIF, rzuca `ValueError` z polskim komunikatem dla nieczytelnego pliku. Zadanie 5 woła to jako pierwszy krok pipeline'u.

- [ ] **Step 1: Napisz test**

Utwórz `tests/test_image_service.py`:

```python
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
```

- [ ] **Step 2: Uruchom — musi paść**

```bash
source .venv/bin/activate && python -m pytest tests/test_image_service.py -v
```

Oczekiwane: `ImportError: cannot import name '_decode_upright'`.

- [ ] **Step 3: Dodaj Pillow do `requirements.txt`**

Wstaw po linii `opencv-python-headless==4.13.0.92`:

```
pillow==11.3.0
```

Następnie: `source .venv/bin/activate && pip install -r requirements.txt`

- [ ] **Step 4: Dodaj `_decode_upright` w `app/services/image_service.py`**

Do importów na górze pliku dochodzi:

```python
import io
import logging

from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger(__name__)
```

Nowa funkcja, wstawiona po `generate_unique_filename`:

```python
def _decode_upright(contents: bytes) -> np.ndarray:
    """
    Dekoduje bajty do BGR, prostując orientację z EXIF.

    `cv2.imdecode` ignoruje EXIF, więc zdjęcie z telefonu przyszłoby w orientacji
    sensora i zapisany kadr poleciałby do modelu bokiem. Pillow czyta tag i obraca.
    """
    try:
        image = Image.open(io.BytesIO(contents))
        image = ImageOps.exif_transpose(image)
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(
            "Nie można odczytać obrazu. Upewnij się, że plik jest poprawnym zdjęciem."
        ) from exc
    return cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
```

- [ ] **Step 5: Uruchom testy**

```bash
source .venv/bin/activate && python -m pytest tests/test_image_service.py -v
```

Oczekiwane: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt app/services/image_service.py tests/test_image_service.py
git commit -m "fix: korekta orientacji zdjęcia z EXIF przed przetwarzaniem

cv2.imdecode ignoruje EXIF, więc zdjęcia z telefonu były przetwarzane
i zapisywane w orientacji sensora. Dochodzi zależność Pillow.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Gts3LZVnfDTHq7d2fC3PAe"
```

---

### Task 5: Wpięcie detekcji w pipeline

Detekcja wchodzi przed skalowaniem i binaryzacją, cała praca OpenCV schodzi z pętli zdarzeń, metryki lądują w logu.

**Files:**
- Modify: `app/services/image_service.py:31-102`
- Modify: `tests/test_image_service.py`

**Interfaces:**
- Consumes: `crop_receipt`, `Detection` z zadania 2; `_decode_upright` z zadania 4.
- Produces:
  - `_process_and_save(contents: bytes, save_path: str, already_cropped: bool) -> Detection | None` — cały blok CPU, wołany w wątku
  - `save_and_process_receipt_image(upload_file, expense_id, already_cropped: bool = False) -> str` — sygnatura rozszerzona o trzeci parametr z domyślną wartością, więc istniejące wywołania dalej działają. Zadanie 6 przekazuje tam flagę z endpointów.

Docelowa kolejność (spec §5): `_decode_upright` → `crop_receipt` (o ile nie `already_cropped`) → `resize` → `gray/blur/adaptiveThreshold` → `imwrite`.

- [ ] **Step 1: Dopisz testy do `tests/test_image_service.py`**

```python
from unittest.mock import patch

from app.services.image_service import _process_and_save
from app.services.receipt_detection import Detection


def test_flaga_already_cropped_pomija_detekcje(tmp_path):
    contents = _jpeg_with_orientation(120, 60, orientation=1)
    target = tmp_path / "wynik.jpg"

    with patch("app.services.image_service.crop_receipt") as detektor:
        result = _process_and_save(contents, str(target), already_cropped=True)

    detektor.assert_not_called()
    assert result is None
    assert target.exists()


def test_bez_flagi_detekcja_jest_wolana(tmp_path):
    contents = _jpeg_with_orientation(120, 60, orientation=1)
    target = tmp_path / "wynik.jpg"
    fake = Detection(score=0.42, frame_ratio=0.5, out_size=(80, 40))

    with patch("app.services.image_service.crop_receipt") as detektor:
        detektor.return_value = (np.zeros((40, 80, 3), np.uint8), fake)
        result = _process_and_save(contents, str(target), already_cropped=False)

    detektor.assert_called_once()
    assert result == fake
    assert target.exists()


def test_blad_opencv_nie_przerywa_zapisu(tmp_path):
    """Wyjątek z detekcji degraduje do obrazu nieskadrowanego — upload musi przejść."""
    import cv2

    contents = _jpeg_with_orientation(120, 60, orientation=1)
    target = tmp_path / "wynik.jpg"

    with patch("app.services.image_service.crop_receipt", side_effect=cv2.error("bum")):
        result = _process_and_save(contents, str(target), already_cropped=False)

    assert result is None
    assert target.exists(), "Plik musi powstać mimo błędu detekcji"
```

- [ ] **Step 2: Uruchom — muszą paść**

```bash
source .venv/bin/activate && python -m pytest tests/test_image_service.py -v
```

Oczekiwane: `ImportError: cannot import name '_process_and_save'`.

- [ ] **Step 3: Przepisz przetwarzanie w `app/services/image_service.py`**

Do importów dochodzi:

```python
import asyncio

from app.services.receipt_detection import Detection, crop_receipt
```

Nowa funkcja synchroniczna, wstawiona przed `save_and_process_receipt_image`:

```python
def _process_and_save(
    contents: bytes,
    save_path: str,
    already_cropped: bool,
) -> Optional[Detection]:
    """
    Cały blok CPU: dekodowanie, kadrowanie, skalowanie, binaryzacja, zapis.

    Wołane przez `asyncio.to_thread` — to setki milisekund czystej pracy procesora,
    która nie może blokować pętli zdarzeń.

    Zwraca metryki detekcji do zalogowania przez wołającego, albo None gdy detekcja
    nie znalazła paragonu, została pominięta flagą lub padła.
    """
    img = _decode_upright(contents)

    detection = None
    if not already_cropped:
        try:
            img, detection = crop_receipt(img)
        except cv2.error:
            logger.warning(
                "Detekcja paragonu nie powiodła się, zapisuję bez kadrowania",
                exc_info=True,
            )

    height, width = img.shape[:2]
    if max(height, width) > MAX_DIMENSION:
        scale = MAX_DIMENSION / max(height, width)
        img = cv2.resize(
            img, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA
        )

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    processed = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )

    cv2.imwrite(save_path, processed, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    return detection
```

Zastąp całe ciało `save_and_process_receipt_image` (linie 31–102 pliku sprzed zmiany):

```python
async def save_and_process_receipt_image(
    upload_file: UploadFile,
    expense_id: int,
    already_cropped: bool = False,
) -> str:
    """
    Zapisuje i przetwarza zdjęcie paragonu:
    1. Dekoduje z korektą orientacji EXIF
    2. Wykrywa i prostuje paragon (chyba że klient zgłosił `already_cropped`)
    3. Skaluje, jeśli obraz jest za duży
    4. Konwertuje do szarości i binaryzuje dla czytelności
    5. Zapisuje jako zoptymalizowany JPEG

    Args:
        upload_file: FastAPI UploadFile object
        expense_id: ID associated expense (used for subfolder)
        already_cropped: klient zgłasza, że paragon jest już wykadrowany

    Returns:
        Relative path to the saved image
    """
    expense_folder = UPLOAD_DIR / str(expense_id)
    expense_folder.mkdir(parents=True, exist_ok=True)

    filename = generate_unique_filename(upload_file.filename or "receipt.jpg")
    file_path = expense_folder / filename

    contents = await upload_file.read()
    detection = await asyncio.to_thread(
        _process_and_save, contents, str(file_path), already_cropped
    )

    if already_cropped:
        logger.info("Detekcja pominięta (already_cropped), wydatek %s", expense_id)
    elif detection is None:
        logger.info("Detekcja: brak kandydata, wydatek %s", expense_id)
    else:
        logger.info(
            "Detekcja: ocena=%.3f udzial=%.3f kadr=%dx%d, wydatek %s",
            detection.score,
            detection.frame_ratio,
            detection.out_size[0],
            detection.out_size[1],
            expense_id,
        )

    return str(file_path.relative_to(Path(".")))
```

- [ ] **Step 4: Uruchom cały zestaw**

```bash
source .venv/bin/activate && python -m pytest tests/ -v
```

Oczekiwane: wszystko PASS (testy detekcji z zadań 1–3 nadal zielone).

- [ ] **Step 5: Commit**

```bash
git add app/services/image_service.py tests/test_image_service.py
git commit -m "feat: kadrowanie paragonu w pipeline przetwarzania zdjęcia

Detekcja wchodzi przed skalowaniem i binaryzacją — musi widzieć kolor.
Praca OpenCV schodzi z pętli zdarzeń przez asyncio.to_thread (problem
istniał już przy samym resize). Metryki detekcji lecą do logu, bo
oryginał nie zostaje na dysku.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Gts3LZVnfDTHq7d2fC3PAe"
```

---

### Task 6: Flaga `already_cropped` w API

**Files:**
- Modify: `app/api/v1/endpoints/ai.py:35-54`
- Modify: `app/api/v1/endpoints/receipts.py:34-66`
- Modify: `docs/api.json` (regeneracja)

**Interfaces:**
- Consumes: `save_and_process_receipt_image(..., already_cropped=...)` z zadania 5.
- Produces: pole formularza `already_cropped` w obu endpointach — kontrakt dla klienta androidowego i www.

Apka androidowa przechodzi przez oba endpointy po kolei z tym samym plikiem, więc flaga musi być w obu — inaczej kadrowanie i tak wykona się przy zapisie.

- [ ] **Step 1: `app/api/v1/endpoints/ai.py` — dodaj parametr**

W sygnaturze `analyze_receipt`, po parametrze `file`:

```python
    already_cropped: bool = Form(
        False,
        description="Klient zgłasza, że paragon jest już wykadrowany — backend pominie detekcję",
    ),
```

Do importu z `fastapi` dochodzi `Form`:

```python
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
```

I przekazanie w wywołaniu (linia 54):

```python
        temp_path = await save_and_process_receipt_image(
            file, expense_id=0, already_cropped=already_cropped
        )
```

- [ ] **Step 2: `app/api/v1/endpoints/receipts.py` — to samo**

W sygnaturze `upload_receipt_image`, po parametrze `file`:

```python
    already_cropped: bool = Form(
        False,
        description="Klient zgłasza, że paragon jest już wykadrowany — backend pominie detekcję",
    ),
```

Import:

```python
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
```

Wywołanie (linia 66):

```python
        relative_path = await save_and_process_receipt_image(
            file, expense_id, already_cropped=already_cropped
        )
```

- [ ] **Step 3: Sprawdź, że aplikacja się podnosi i spec się generuje**

```bash
source .venv/bin/activate && python scripts/export_openapi.py
```

Oczekiwane: `Zapisano: .../docs/api.json`. Import `app.main` przy okazji weryfikuje, że nic się nie rozjechało w sygnaturach.

- [ ] **Step 4: Sprawdź, że flaga faktycznie jest w specu**

```bash
source .venv/bin/activate && python -c "
import json
spec = json.load(open('docs/api.json'))
for path in ['/api/v1/ai/receipt', '/api/v1/receipts/{expense_id}/receipt']:
    body = spec['paths'][path]['post']['requestBody']['content']
    schema = list(body.values())[0]['schema']
    ref = schema.get('\$ref', '').split('/')[-1]
    props = spec['components']['schemas'][ref]['properties'] if ref else schema['properties']
    print(path, '→', 'already_cropped' in props)
"
```

Oczekiwane: obie linie kończą się `True`.

- [ ] **Step 5: Commit**

```bash
git add app/api/v1/endpoints/ai.py app/api/v1/endpoints/receipts.py docs/api.json
git commit -m "feat: flaga already_cropped w endpointach przyjmujących zdjęcie

Klient, który sam wykadrował paragon (apka androidowa, www), zgłasza to
w multiparcie i backend pomija detekcję. Flaga jest w obu endpointach,
bo apka przechodzi przez oba z tym samym plikiem.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Gts3LZVnfDTHq7d2fC3PAe"
```

---

### Task 7: Skrypt pomiaru binaryzacji

Rozstrzyga los `adaptiveThreshold` (spec §6.4). Narzędzie, nie test — kosztuje wywołania OpenRouter i zależy od odpowiedzi modelu, więc nie może lecieć automatycznie.

**Files:**
- Create: `scripts/porownaj_binaryzacje.py`

**Interfaces:**
- Consumes: `crop_receipt` z zadania 2; `parse_receipt_image(db, user_id, image_path)` z `app/services/ai_service.py`; `SessionLocal` z `app/db/session.py`.
- Produces: nic dla dalszych zadań — decyzja o progu zapada poza tym planem.

- [ ] **Step 1: Utwórz `scripts/porownaj_binaryzacje.py`**

```python
"""
Porównuje odpowiedzi modelu vision dla paragonu z binaryzacją i bez niej.

Jednorazowe narzędzie do rozstrzygnięcia, czy `adaptiveThreshold` w pipeline
pomaga modelowi multimodalnemu, czy szkodzi (dokument źródłowy §9.4). Kosztuje
dwa wywołania OpenRouter na zdjęcie, więc nie jest testem.

Prawdy podstawowej nie ma — nikt nie oznaczył oczekiwanych kwot — więc werdykt
wydaje człowiek, patrząc na tabelę obok paragonów.

Użycie:
    source .venv/bin/activate
    python scripts/porownaj_binaryzacje.py --user-id 1
    python scripts/porownaj_binaryzacje.py --user-id 1 --zdjecia ~/inne/zdjecia
"""
import argparse
import asyncio
import sys
import tempfile
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.services.ai_service import parse_receipt_image  # noqa: E402
from app.services.image_service import JPEG_QUALITY, MAX_DIMENSION, _decode_upright  # noqa: E402
from app.services.receipt_detection import crop_receipt  # noqa: E402

DEFAULT_SET = (
    Path(__file__).parent.parent.parent
    / "wydatki2.0android/app/src/androidTest/assets/receipts"
)


def przygotuj(contents: bytes, save_path: Path, binaryzuj: bool) -> None:
    """Ten sam pipeline co w image_service, z binaryzacją albo bez."""
    img = _decode_upright(contents)
    img, _ = crop_receipt(img)

    height, width = img.shape[:2]
    if max(height, width) > MAX_DIMENSION:
        scale = MAX_DIMENSION / max(height, width)
        img = cv2.resize(
            img, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA
        )

    if binaryzuj:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        img = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )

    cv2.imwrite(str(save_path), img, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])


async def zmierz(db, user_id: int, contents: bytes, binaryzuj: bool, katalog: Path):
    sciezka = katalog / ("bin.jpg" if binaryzuj else "kolor.jpg")
    przygotuj(contents, sciezka, binaryzuj)
    start = time.time()
    try:
        draft = await parse_receipt_image(db=db, user_id=user_id, image_path=str(sciezka))
    except Exception as exc:  # noqa: BLE001 — narzędzie diagnostyczne, chcemy zobaczyć wszystko
        return f"BŁĄD: {exc}"[:38], 0, time.time() - start
    # ExpenseDraft: `amount` jest wymagane (gt=0), `items` ma default_factory=list —
    # obrony przed None nie potrzeba, tylko `description` bywa puste.
    opis = f"{draft.amount:>8.2f} {(draft.description or '—')[:24]:<24}"
    return opis, len(draft.items), time.time() - start


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", type=int, required=True, help="ID użytkownika z bazy")
    parser.add_argument("--zdjecia", type=Path, default=DEFAULT_SET)
    args = parser.parse_args()

    pliki = sorted(args.zdjecia.glob("*.jpg"))
    if not pliki:
        sys.exit(f"Brak zdjęć w {args.zdjecia}")

    db = SessionLocal()
    print(f"\n{'zdjęcie':<10} {'wariant':<8} {'kwota i opis':<34} {'poz.':>5} {'czas':>7}")
    print("-" * 68)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            katalog = Path(tmp)
            for plik in pliki:
                contents = plik.read_bytes()
                for binaryzuj, etykieta in ((True, "próg"), (False, "kolor")):
                    opis, pozycje, czas = await zmierz(
                        db, args.user_id, contents, binaryzuj, katalog
                    )
                    print(f"{plik.name:<10} {etykieta:<8} {opis:<34} {pozycje:>5} {czas:>6.1f}s")
                print()
    finally:
        db.close()

    print("Werdykt wydaje człowiek: porównaj kwoty i liczbę pozycji z paragonami.")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Sprawdź, że skrypt się uruchamia (bez palenia tokenów)**

```bash
source .venv/bin/activate && python scripts/porownaj_binaryzacje.py --help
```

Oczekiwane: pomoc argparse, bez błędu importu.

- [ ] **Step 3: Commit**

```bash
git add scripts/porownaj_binaryzacje.py
git commit -m "tools: skrypt porównania binaryzacji dla modelu vision

Przepuszcza zestaw zdjęć przez parse_receipt_image w wariancie z progiem
i bez, po kadrowaniu w obu. Decyzja o losie adaptiveThreshold zapada
po obejrzeniu tabeli — port wchodzi z progiem nietkniętym.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Gts3LZVnfDTHq7d2fC3PAe"
```

---

### Task 8: Dokumentacja i wersja

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/port-detekcji-paragonu-z-androida.md`
- Modify: `VERSION`

**Interfaces:**
- Consumes: wszystko z zadań 1–7.
- Produces: nic.

- [ ] **Step 1: `CLAUDE.md` — sekcja Commands, po bloku z uruchamianiem**

Zastąp linię `There are no tests in this project.` blokiem:

```markdown
# Run tests (detection regression needs the photo set from the Android repo)
pip install -r requirements-dev.txt
pytest tests/ -v
```

Testy pokrywają wyłącznie detekcję paragonu i pipeline obrazu. Zestaw 18 zdjęć jest
poza gitem (`~/Projekty/wydatki2.0android/app/src/androidTest/assets/`, ścieżka
nadpisywalna przez `RECEIPT_TEST_SET`) — bez niego testy detekcji się pomijają.

- [ ] **Step 2: `CLAUDE.md` — sekcja Stack, punkt Image processing**

Zastąp dzisiejsze dwie linie (`Receipt detection/cropping is not implemented here…`):

```markdown
- **Image processing**: OpenCV (`image_service.py`) — EXIF → detekcja i prostowanie
  paragonu (`receipt_detection.py`) → skalowanie → grayscale + adaptive threshold.
  Klient może pominąć detekcję flagą `already_cropped` w multiparcie.
  Opis algorytmu i progów: `docs/port-detekcji-paragonu-z-androida.md`.
```

- [ ] **Step 3: `CLAUDE.md` — sekcja Data model**

Popraw „Five SQLAlchemy models" na dziesięć i dopisz brakujące: `PaymentCard`, `Tag`,
`AssetKeyConfig`, `AssetAccount`, `AssetSnapshot`. W sekcji API structure dopisz
`/tags`, `/cards`, `/assets`, `/admin` — są w routerze, a nie ma ich w opisie.

- [ ] **Step 4: `docs/port-detekcji-paragonu-z-androida.md` — oznacz port jako wykonany**

Zastąp nagłówkowy akapit („Ten dokument opisuje kod, którego w tym repo jeszcze nie ma…"):

```markdown
**Port wykonany.** Detekcja działa po obu stronach: w aplikacji Android
(`ui/scan/ReceiptQuadDetector.kt`) i w backendzie (`app/services/receipt_detection.py`).
Sekcje 1–8 opisują implementację androidowa i pozostają kanoniczne dla algorytmu;
sekcja 9 jest zapisem tego, jak port przebiegł. Design portu:
`docs/superpowers/specs/2026-09-06-port-detekcji-paragonu-design.md`.

Przy zmianie detektora po którejkolwiek stronie trzeba przepuścić wspólny zestaw zdjęć
przez oba testy — to jedyne, co pilnuje, żeby implementacje się nie rozjechały.
```

W §9.9 popraw lokalizację oznaczeń: `oczekiwane_paragony.json` leży w `androidTest/assets/`,
a nie w `assets/receipts/`. W §9.9 zastąp też postulat idempotencji (`None` przy drugim
przebiegu) opisem tego, co faktycznie testujemy — pokrycie ≥ 0.98 przy powtórnym
kadrowaniu, z odsyłaczem do §9.2, które mierzy, dlaczego `None` nie nastąpi.

Dopisz w §9.6 tabelę mapowania nazw ze specu §3.2 (szkic polski → moduł angielski).

- [ ] **Step 5: `VERSION`**

```bash
echo "0.5.5" > VERSION
```

- [ ] **Step 6: Uruchom pełny zestaw ostatni raz**

```bash
source .venv/bin/activate && python -m pytest tests/ -v && python scripts/export_openapi.py
```

Oczekiwane: wszystkie testy PASS, spec zapisany.

- [ ] **Step 7: Commit**

```bash
git add CLAUDE.md docs/port-detekcji-paragonu-z-androida.md VERSION docs/api.json
git commit -m "docs: aktualizacja po porcie detekcji paragonu + wersja 0.5.5

CLAUDE.md: testy istnieją, pipeline obrazu opisany od nowa, uzupełnione
modele i endpointy, które rozjechały się z kodem. Dokument portu oznaczony
jako wykonany.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Gts3LZVnfDTHq7d2fC3PAe"
```

---

## Po planie — weryfikacja na żywo

Plan kończy się na zielonych testach, ale detekcja jest zmianą jakościową i warto ją zobaczyć na prawdziwym ruchu, zanim uzna się ją za dobrą:

```bash
podman build -t wydatki . && systemctl --user restart wydatki.service
journalctl --user -u wydatki.service -f | grep -i detekcja
```

Log z sekcji 5.3 specu (`ocena`, `udzial`, rozmiar kadru) jest jedynym źródłem danych do strojenia progów na produkcji — po kilkudziesięciu paragonach pokaże rozkład ocen i będzie wiadomo, czy zestaw negatywny (spec §7) jest pilny, czy może poczekać.

**Nie w tym planie, świadomie** (spec §7): strażnik podwójnego kadrowania, zestaw negatywny, progi w konfiguracji, sprzątanie `data/uploads/receipts/0/`, wysyłanie flagi przez apkę androidową.
