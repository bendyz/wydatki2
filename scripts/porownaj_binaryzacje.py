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
