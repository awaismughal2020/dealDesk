"""Sign-in, refresh, sign-out and identity. Tokens travel only in HttpOnly cookies."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response

from dealdesk.api.deps import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    REFRESH_COOKIE,
    REFRESH_COOKIE_PATH,
    ContainerDep,
    client_ip,
    request_id,
    require_permission,
)
from dealdesk.api.errors import ApiError
from dealdesk.api.schemas import CsrfOut, LoginIn, MeOut, SessionOut
from dealdesk.auth.csrf import new_csrf_token
from dealdesk.auth.local import Session
from dealdesk.auth.policy import Permission, permissions_for
from dealdesk.auth.port import AuthenticationError, Principal
from dealdesk.config import AuthMode, Settings

router = APIRouter(prefix="/v1/auth", tags=["auth"])
SessionUser = Annotated[Principal, Depends(require_permission(Permission.SESSION))]
CSRF_MAX_AGE_SECONDS = 12 * 60 * 60


def me_out(principal: Principal, settings: Settings) -> MeOut:
    """The identity payload (permissions are UI hints only)."""
    return MeOut(
        id=principal.user_id,
        email=principal.email,
        display_name=principal.display_name,
        role=principal.role,
        permissions=permissions_for(principal.role),
        auth_mode=settings.auth_mode.value,
    )


def _cookie_options(settings: Settings) -> dict[str, Any]:
    return {"secure": settings.cookie_secure, "samesite": "lax"}


def set_session_cookies(response: Response, session: Session, settings: Settings) -> None:
    """Access token for every path (pages need it), refresh token only for /v1/auth."""
    options = _cookie_options(settings)
    response.set_cookie(
        ACCESS_COOKIE,
        session.access_token,
        max_age=settings.access_token_ttl_seconds,
        path="/",
        httponly=True,
        **options,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        session.refresh_token,
        max_age=settings.refresh_token_ttl_seconds,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        **options,
    )


def clear_session_cookies(response: Response, settings: Settings) -> None:
    """Expire both session cookies."""
    options = _cookie_options(settings)
    response.delete_cookie(ACCESS_COOKIE, path="/", httponly=True, **options)
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, httponly=True, **options)


def _session_out(session: Session, settings: Settings) -> SessionOut:
    return SessionOut(
        user=me_out(session.principal, settings), access_expires_at=session.access_expires_at
    )


def _local_only(settings: Settings) -> None:
    if settings.auth_mode is not AuthMode.LOCAL:
        raise ApiError(404, "Not available", "Sign-in is handled by the identity provider.")


@router.get("/csrf", response_model=CsrfOut, operation_id="getCsrfToken")
def csrf(response: Response, container: ContainerDep) -> CsrfOut:
    """Issue a CSRF token (double-submit cookie). Public: it grants nothing on its own."""
    token = new_csrf_token()
    response.set_cookie(
        CSRF_COOKIE,
        token,
        max_age=CSRF_MAX_AGE_SECONDS,
        path="/",
        httponly=False,
        **_cookie_options(container.settings),
    )
    return CsrfOut(csrf_token=token)


@router.post(
    "/login",
    response_model=SessionOut,
    operation_id="login",
    responses={401: {"description": "Sign-in failed"}, 429: {"description": "Too many attempts"}},
)
def login(
    body: LoginIn, request: Request, response: Response, container: ContainerDep
) -> SessionOut:
    """Sign in with email and password (local mode). Sets HttpOnly session cookies."""
    _local_only(container.settings)
    session = container.sessions.login(
        body.email, body.password, ip=client_ip(request), request_id=request_id(request)
    )
    set_session_cookies(response, session, container.settings)
    return _session_out(session, container.settings)


@router.post(
    "/refresh",
    response_model=SessionOut,
    operation_id="refreshSession",
    responses={401: {"description": "Refresh token invalid, expired or reused"}},
)
def refresh(request: Request, response: Response, container: ContainerDep) -> SessionOut:
    """Rotate the refresh token and issue a new access token. Reuse revokes the session family."""
    _local_only(container.settings)
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise ApiError(401, "Not signed in", "Your session has ended. Sign in again.")
    try:
        session = container.sessions.refresh(token, request_id=request_id(request))
    except AuthenticationError as exc:
        failure = ApiError(401, "Not signed in", "Your session has ended. Sign in again.")
        raise failure from exc
    set_session_cookies(response, session, container.settings)
    return _session_out(session, container.settings)


@router.post("/logout", status_code=204, operation_id="logout")
def logout(request: Request, user: SessionUser, container: ContainerDep) -> Response:
    """Revoke the session on the server and clear the cookies."""
    container.sessions.logout(
        request.cookies.get(REFRESH_COOKIE), user, request_id=request_id(request)
    )
    response = Response(status_code=204)
    clear_session_cookies(response, container.settings)
    return response


@router.get("/me", response_model=MeOut, operation_id="getMe")
def me(user: SessionUser, container: ContainerDep) -> MeOut:
    """Who is signed in."""
    return me_out(user, container.settings)


@router.get("/jwks.json", operation_id="getJwks")
def jwks(container: ContainerDep) -> dict[str, list[dict[str, str]]]:
    """Public signing keys (current and previous) so other services can verify our tokens."""
    return container.tokens.jwks()
