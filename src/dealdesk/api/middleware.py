"""HTTP middleware: request ids, access logs, security headers, body cap, rate limit, CSRF."""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from dealdesk.api.deps import CSRF_COOKIE, CSRF_HEADER
from dealdesk.api.errors import problem
from dealdesk.auth.csrf import SAFE_METHODS, origin_allowed, tokens_match
from dealdesk.auth.ratelimit import SlidingWindowLimiter
from dealdesk.observability import get_logger

Next = Callable[[Request], Awaitable[Response]]
REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
UNLIMITED_PATHS = frozenset({"/healthz", "/readyz"})
MULTIPART_OVERHEAD_BYTES = 64 * 1024
log = get_logger("api.access")

API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
DOCS_CSP = (
    "default-src 'none'; script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; img-src 'self' data: "
    "https://fastapi.tiangolo.com; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
)
DOCS_PATHS = frozenset({"/docs", "/docs/oauth2-redirect"})
HSTS = "max-age=63072000; includeSubDomains"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a request id, bind it to every log line, and write one access log entry."""

    async def dispatch(self, request: Request, call_next: Next) -> Response:
        """Handle one request."""
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        rid = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        request.state.request_id = rid
        structlog.contextvars.bind_contextvars(request_id=rid)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
        response.headers[REQUEST_ID_HEADER] = rid
        log.info(
            "http.request",
            request_id=rid,
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Strict headers on every response; HSTS outside local; no caching of API data."""

    def __init__(self, app: ASGIApp, *, hsts: bool) -> None:
        super().__init__(app)
        self._hsts = hsts

    async def dispatch(self, request: Request, call_next: Next) -> Response:
        """Add headers."""
        response = await call_next(request)
        headers = response.headers
        headers["Content-Security-Policy"] = DOCS_CSP if request.url.path in DOCS_PATHS else API_CSP
        headers["X-Content-Type-Options"] = "nosniff"
        headers["X-Frame-Options"] = "DENY"
        headers["Referrer-Policy"] = "no-referrer"
        headers["Cross-Origin-Opener-Policy"] = "same-origin"
        headers["Cross-Origin-Resource-Policy"] = "same-origin"
        headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        headers.setdefault("Cache-Control", "no-store")
        if self._hsts:
            headers["Strict-Transport-Security"] = HSTS
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-client request budget for the whole API (sign-in has its own, stricter limits)."""

    def __init__(self, app: ASGIApp, *, limiter: SlidingWindowLimiter) -> None:
        super().__init__(app)
        self._limiter = limiter

    async def dispatch(self, request: Request, call_next: Next) -> Response:
        """Reject with 429 when over budget."""
        if request.url.path not in UNLIMITED_PATHS:
            client = request.client.host if request.client else "unknown"
            retry_after = self._limiter.hit(client)
            if retry_after is not None:
                return problem(
                    request,
                    429,
                    "Too many requests",
                    "Slow down and try again.",
                    headers={"Retry-After": str(max(1, int(retry_after)))},
                )
        return await call_next(request)


class CsrfMiddleware(BaseHTTPMiddleware):
    """State-changing requests need an allowed Origin and a double-submit token."""

    def __init__(self, app: ASGIApp, *, allowed_origins: list[str]) -> None:
        super().__init__(app)
        self._allowed = allowed_origins

    async def dispatch(self, request: Request, call_next: Next) -> Response:
        """Reject cross-site or token-less writes with 403."""
        if request.method not in SAFE_METHODS:
            origin_ok = origin_allowed(
                request.headers.get("origin"), request.headers.get("referer"), self._allowed
            )
            token_ok = tokens_match(
                request.cookies.get(CSRF_COOKIE), request.headers.get(CSRF_HEADER)
            )
            if not (origin_ok and token_ok):
                log.warning(
                    "csrf.rejected", path=request.url.path, origin_ok=origin_ok, token_ok=token_ok
                )
                return problem(request, 403, "CSRF check failed", "Reload the page and try again.")
        return await call_next(request)


class BodySizeLimitMiddleware:
    """Reject request bodies above a byte limit, whether or not Content-Length is sent."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self._app = app
        self._max = max_bytes + MULTIPART_OVERHEAD_BYTES

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI entry point."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        declared = dict(scope.get("headers", [])).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > self._max:
            await self._too_large(scope, receive, send)
            return
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self._max:
                    raise BodyTooLargeError
            return message

        try:
            await self._app(scope, limited_receive, send)
        except BodyTooLargeError:
            await self._too_large(scope, receive, send)

    @staticmethod
    async def _too_large(scope: Scope, receive: Receive, send: Send) -> None:
        response = problem(
            Request(scope, receive), 413, "Too large", "The request body is too large."
        )
        await response(scope, receive, send)


class BodyTooLargeError(Exception):
    """Raised inside the receive wrapper when the cap is exceeded."""
