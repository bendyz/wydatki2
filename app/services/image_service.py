import asyncio
import io
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings
from app.services.receipt_detection import Detection, crop_receipt

logger = logging.getLogger(__name__)

# Base directory for uploads from config
UPLOAD_DIR = Path(settings.storage.uploads_path)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Max dimension for receipt images (to save space)
MAX_DIMENSION = 1920
JPEG_QUALITY = 85


def generate_unique_filename(original_filename: str) -> str:
    """
    Generates a unique filename based on UUID while preserving the extension.
    """
    ext = Path(original_filename).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
        ext = ".jpg"
    return f"{uuid.uuid4().hex}{ext}"


def _decode_upright(contents: bytes) -> np.ndarray:
    """
    Dekoduje bajty do BGR, prostując orientację z EXIF.

    `cv2.imdecode` ignoruje EXIF, więc zdjęcie z telefonu przyszłoby w orientacji
    sensora i zapisany kadr poleciałby do modelu bokiem. Pillow czyta tag i obraca.
    """
    try:
        image = Image.open(io.BytesIO(contents))
        image = ImageOps.exif_transpose(image)
        rgb = np.array(image.convert("RGB"))
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(
            "Nie można odczytać obrazu. Upewnij się, że plik jest poprawnym zdjęciem."
        ) from exc
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


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


def get_receipt_image_path(expense_id: int, filename: str) -> Optional[Path]:
    """
    Returns full path to a receipt image if it exists.

    Args:
        expense_id: ID of expense
        filename: Name of the image file

    Returns:
        Path object or None if file doesn't exist
    """
    file_path = UPLOAD_DIR / str(expense_id) / filename
    if file_path.exists():
        return file_path
    return None


def delete_receipt_images(expense_id: int) -> bool:
    """
    Deletes all receipt images associated with an expense.

    Args:
        expense_id: ID of expense

    Returns:
        True if folder was deleted or didn't exist
    """
    expense_folder = UPLOAD_DIR / str(expense_id)
    if expense_folder.exists():
        for file in expense_folder.iterdir():
            file.unlink()
        expense_folder.rmdir()
        return True
    return False
