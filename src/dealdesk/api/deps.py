"""Request dependencies: the container, the signed-in user, and permission checks.

Every route except the explicit public allowlist in `dealdesk.api.app.PUBLIC_ROUTES` depends on
`require_permission(...)`. A test walks the route table and fails if one does not.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request

from dealdesk.api.container import Container
from dealdesk.api.errors import ApiError
from dealdesk.auth.policy import Permission, has_permission
from dealdesk.auth.port import AuthenticationError, Principal

ACCESS_COOKIE = "dd_access"
REFRESH_COOKIE = "dd_refresh"
CSRF_COOKIE = "dd_csrf"
CSRF_HEADER = "X-CSRF-Token"
REFRESH_COOKIE_PATH = "/v1/auth"
PERMISSION_ATTR = "__dealdesk_permission__"


def get_container(request: Request) -> Container:
    """The process-wide container."""
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


def request_id(request: Request) -> str | None:
    """The correlation id set by the request-context middleware."""
    value = getattr(request.state, "request_id", None)
    return str(value) if value else None


def client_ip(request: Request) -> str:
    """Client address (uvicorn applies trusted X-Forwarded-For)."""
    return request.client.host if request.client else "unknown"


def current_user(request: Request, container: ContainerDep) -> Principal:
    """The authenticated, active user, or 401."""
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise ApiError(401, "Not signed in", "Sign in to continue.")
    try:
        return container.authenticator.authenticate(token)
    except AuthenticationError as exc:
        raise ApiError(401, "Not signed in", "Your session has expired. Sign in again.") from exc


def require_permission(permission: Permission) -> Callable[[Principal], Principal]:
    """A dependency that authenticates and then checks one permission (deny by default)."""

    def dependency(principal: Annotated[Principal, Depends(current_user)]) -> Principal:
        if not has_permission(principal.role, permission):
            raise ApiError(403, "Forbidden", "Your role does not allow this action.")
        return principal

    setattr(dependency, PERMISSION_ATTR, permission)
    dependency.__name__ = f"require_{permission.name.lower()}"
    return dependency
