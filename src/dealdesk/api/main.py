"""ASGI entrypoint: `uvicorn dealdesk.api.main:app`."""

from dealdesk.api.app import create_app

app = create_app()
