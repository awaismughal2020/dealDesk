"""Liveness and readiness probes. Public by design (they reveal nothing)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from dealdesk.api.schemas import HealthStatus

router = APIRouter(tags=["health"])
SERVICE_UNAVAILABLE = 503


@router.get("/healthz", response_model=HealthStatus, operation_id="healthz")
def healthz() -> HealthStatus:
    """Liveness: the process is up."""
    return HealthStatus(status="ok")


@router.get(
    "/readyz",
    response_model=HealthStatus,
    operation_id="readyz",
    responses={503: {"model": HealthStatus}},
)
def readyz(request: Request) -> HealthStatus | JSONResponse:
    """Readiness: the database answers."""
    try:
        ready = request.app.state.container.ready()
    except SQLAlchemyError:
        ready = False
    if not ready:
        return JSONResponse({"status": "unavailable"}, status_code=SERVICE_UNAVAILABLE)
    return HealthStatus(status="ready")
