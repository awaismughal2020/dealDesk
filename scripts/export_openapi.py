"""Write the API's OpenAPI document (the front-end client is generated from it).

Usage: python scripts/export_openapi.py web/openapi.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from dealdesk.api.app import create_app
from dealdesk.config import Settings


def openapi_document(app: FastAPI) -> dict[str, Any]:
    """The OpenAPI schema as plain JSON data."""
    document: dict[str, Any] = json.loads(json.dumps(app.openapi()))
    return document


def main() -> None:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "web/openapi.json")
    app = create_app(Settings(cookie_secure=False, log_level="WARNING"))
    target.write_text(
        json.dumps(openapi_document(app), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
