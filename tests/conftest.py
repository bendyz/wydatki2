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
