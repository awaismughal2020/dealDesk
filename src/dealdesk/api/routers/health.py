"""Liveness and readiness probes. These are the only unauthenticated routes besides sign-in."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthStatus(BaseModel):
    """Probe response."""

    status: str


@router.get("/healthz", response_model=HealthStatus)
def healthz() -> HealthStatus:
    """Liveness: the process is up."""
    return HealthStatus(status="ok")


@router.get("/readyz", response_model=HealthStatus)
def readyz() -> HealthStatus:
    """Readiness: the process can serve traffic."""
    return HealthStatus(status="ready")
