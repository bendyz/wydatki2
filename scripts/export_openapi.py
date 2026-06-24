"""Eksportuje spec OpenAPI do docs/api.json. Uruchom po każdej zmianie API."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.main import app

output = Path(__file__).parent.parent / "docs" / "api.json"
output.parent.mkdir(exist_ok=True)
output.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False))
print(f"Zapisano: {output}")
