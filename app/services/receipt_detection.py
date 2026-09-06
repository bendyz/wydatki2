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
