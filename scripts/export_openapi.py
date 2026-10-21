import json
from pathlib import Path

from ashana.bootstrap.app import create_app

destination = Path(__file__).resolve().parents[1] / "backend" / "openapi.json"
destination.write_text(
    json.dumps(create_app().openapi(), ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print("Контракт OpenAPI обновлён.")
