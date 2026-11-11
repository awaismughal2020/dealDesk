"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from dealdesk.api.routers import health
from dealdesk.config import Settings, load_settings
from dealdesk.observability import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API application. Settings are validated before anything else starts."""
    settings = settings or load_settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title="Deal Desk API",
        version="0.1.0",
        description="Brief to approved, costed proposal, human in the loop. SAMPLE DATA ONLY.",
    )
    app.state.settings = settings
    app.include_router(health.router)
    return app
