"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute

from dealdesk.api.container import Container, build_container
from dealdesk.api.errors import PROBLEM_JSON, install_error_handlers
from dealdesk.api.middleware import (
    BodySizeLimitMiddleware,
    CsrfMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from dealdesk.api.routers import admin, auth, health, impact, runs
from dealdesk.api.schemas import Problem
from dealdesk.auth.ratelimit import SlidingWindowLimiter
from dealdesk.config import Settings, load_settings
from dealdesk.observability import configure_logging, get_logger

#: The only routes reachable without signing in. Everything else requires a permission.
PUBLIC_ROUTES = frozenset(
    {
        ("GET", "/healthz"),
        ("GET", "/readyz"),
        ("GET", "/v1/auth/csrf"),
        ("POST", "/v1/auth/login"),
        ("POST", "/v1/auth/refresh"),
        ("GET", "/v1/auth/jwks.json"),
    }
)


def _problem(description: str) -> dict[str, Any]:
    return {"model": Problem, "description": description}


#: Every error is RFC 9457 problem+json; documented so the generated client knows its shape.
PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: _problem("Not signed in or session expired"),
    403: _problem("Forbidden (role, separation of duties or CSRF)"),
    404: _problem("Not found"),
    409: _problem("Conflict"),
    422: _problem("Invalid request"),
    429: _problem("Too many requests"),
}

#: Every router the app serves. Tests enumerate routes from here (and cross-check OpenAPI).
ROUTERS = (health.router, auth.router, runs.router, impact.router, admin.router)
log = get_logger("api")


def _document_problem_responses(app: FastAPI) -> None:
    """Declare 4xx bodies as application/problem+json (FastAPI defaults to application/json)."""
    original = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            schema = original()
            for operations in schema.get("paths", {}).values():
                for operation in operations.values():
                    for status, response in operation.get("responses", {}).items():
                        content = response.get("content", {})
                        if status.startswith("4") and "application/json" in content:
                            content[PROBLEM_JSON] = content.pop("application/json")
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]


def _operation_id(route: APIRoute) -> str:
    return route.operation_id or route.name


def create_app(
    settings: Settings | None = None,
    *,
    container_factory: Callable[[Settings], Container] | None = None,
    recover_on_start: bool = True,
) -> FastAPI:
    """Build the API. Settings are validated before anything starts (fail fast)."""
    settings = settings or load_settings()
    configure_logging(settings.log_level)
    factory = container_factory or build_container

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = factory(settings)
        app.state.container = container
        if recover_on_start:
            recovered = container.runner.recover()
            log.info("workflow.recovered", runs=len(recovered))
        try:
            yield
        finally:
            container.close()

    app = FastAPI(
        title="Deal Desk API",
        version="0.1.0",
        description="Brief to approved, costed proposal, human in the loop. SAMPLE DATA ONLY.",
        lifespan=lifespan,
        docs_url="/docs" if settings.is_local else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.is_local else None,
        generate_unique_id_function=_operation_id,
    )
    install_error_handlers(app)
    _document_problem_responses(app)
    for router in ROUTERS:
        app.include_router(router, responses=PROBLEM_RESPONSES)
    # Added inside-out: the last one added runs first.
    app.add_middleware(CsrfMiddleware, allowed_origins=settings.allowed_origins)
    app.add_middleware(
        RateLimitMiddleware, limiter=SlidingWindowLimiter(settings.api_rate_limit_per_minute)
    )
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.upload_max_bytes)
    app.add_middleware(SecurityHeadersMiddleware, hsts=not settings.is_local)
    app.add_middleware(RequestContextMiddleware)
    return app
