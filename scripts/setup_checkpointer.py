"""Create or upgrade LangGraph's checkpoint tables. Safe to run repeatedly."""

from __future__ import annotations

from dealdesk.adapters.db.checkpointer import open_checkpointer
from dealdesk.config import load_settings


def main() -> None:
    settings = load_settings()
    saver, pool = open_checkpointer(settings.database_url.get_secret_value(), max_size=1)
    try:
        saver.setup()
    finally:
        pool.close()
    print("checkpointer: LangGraph checkpoint tables ready")


if __name__ == "__main__":
    main()
