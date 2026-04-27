import os
import uuid
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from fastapi import UploadFile

from app.core.config import settings

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


async def save_and_process_receipt_image(
    upload_file: UploadFile,
    expense_id: int,
) -> str:
    """
    Saves and processes a receipt image:
    1. Reads uploaded image
    2. Converts to grayscale
    3. Applies adaptive thresholding for better OCR readability
    4. Resizes if too large
    5. Saves as optimized JPEG

    Args:
        upload_file: FastAPI UploadFile object
        expense_id: ID of associated expense (used for subfolder)

    Returns:
        Relative path to the saved image
    """
    # Create subfolder per expense for organization
    expense_folder = UPLOAD_DIR / str(expense_id)
    expense_folder.mkdir(parents=True, exist_ok=True)

    filename = generate_unique_filename(upload_file.filename or "receipt.jpg")
    file_path = expense_folder / filename

    # Read uploaded file into memory
    contents = await upload_file.read()

    # Convert bytes to numpy array for OpenCV
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        raise ValueError(
            "Nie można odczytać obrazu. Upewnij się, że plik jest poprawnym zdjęciem."
        )

    # Resize if image is too large (saves space)
    height, width = img.shape[:2]
    if max(height, width) > MAX_DIMENSION:
        scale = MAX_DIMENSION / max(height, width)
        new_width = int(width * scale)
        new_height = int(height * scale)
        img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)

    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Apply Gaussian blur to reduce noise
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Adaptive thresholding for better text contrast (black & white effect)
    processed = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11,
        2,
    )

    # Save as optimized JPEG
    save_path = str(file_path)
    cv2.imwrite(
        save_path,
        processed,
        [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY],
    )

    # Return relative path from project root
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
