"""RFC 9457 problem+json responses for every error, with the request id attached."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from dealdesk.adapters.briefs import UploadRejectedError
from dealdesk.application.runs import (
    CommentRequiredError,
    ForbiddenActionError,
    InvalidRunStateError,
)
from dealdesk.auth.local import LoginRejectedError, TooManyAttemptsError
from dealdesk.auth.passwords import PasswordPolicyError
from dealdesk.domain.errors import DomainError, SeparationOfDutiesError
from dealdesk.observability import get_logger
from dealdesk.ports.repositories import DuplicateEmailError, NotFoundError

PROBLEM_JSON = "application/problem+json"
log = get_logger("api.errors")


class ApiError(Exception):
    """An error with an HTTP status, a short title and a user-safe detail."""

    def __init__(
        self,
        status: int,
        title: str,
        detail: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail or title)
        self.status = status
        self.title = title
        self.detail = detail
        self.headers = headers


def problem(
    request: Request,
    status: int,
    title: str,
    detail: str | None = None,
    *,
    errors: list[dict[str, str]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build a problem+json response."""
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
        "request_id": getattr(request.state, "request_id", None),
    }
    if errors is not None:
        body["errors"] = errors
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON, headers=headers)


_MAPPED: tuple[tuple[type[Exception], int, str], ...] = (
    (NotFoundError, 404, "Not found"),
    (SeparationOfDutiesError, 403, "Separation of duties"),
    (ForbiddenActionError, 403, "Forbidden"),
    (InvalidRunStateError, 409, "Conflict"),
    (DuplicateEmailError, 409, "Conflict"),
    (CommentRequiredError, 422, "Comment required"),
    (PasswordPolicyError, 422, "Password not accepted"),
    (LoginRejectedError, 401, "Sign-in failed"),
    (DomainError, 422, "Rule violated"),
)

_SAFE_DETAILS = {
    NotFoundError: "The requested item does not exist.",
    DuplicateEmailError: "A user with this email already exists.",
}


def install_error_handlers(app: FastAPI) -> None:
    """Register handlers so nothing leaks a stack trace or a non-problem body."""

    @app.exception_handler(ApiError)
    def _api(request: Request, exc: ApiError) -> JSONResponse:
        return problem(request, exc.status, exc.title, exc.detail, headers=exc.headers)

    @app.exception_handler(UploadRejectedError)
    def _upload(request: Request, exc: UploadRejectedError) -> JSONResponse:
        return problem(request, exc.status, "Upload rejected", str(exc))

    @app.exception_handler(TooManyAttemptsError)
    def _too_many(request: Request, exc: TooManyAttemptsError) -> JSONResponse:
        retry = str(max(1, int(exc.retry_after)))
        return problem(
            request, 429, "Too many attempts", "Try again later.", headers={"Retry-After": retry}
        )

    @app.exception_handler(RequestValidationError)
    def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": ".".join(str(part) for part in e.get("loc", ())), "msg": str(e.get("msg", ""))}
            for e in exc.errors()
        ]
        return problem(
            request, 422, "Invalid request", "Check the highlighted fields.", errors=errors
        )

    @app.exception_handler(StarletteHTTPException)
    def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return problem(
            request, exc.status_code, str(exc.detail), headers=getattr(exc, "headers", None)
        )

    for exc_type, status, title in _MAPPED:
        app.add_exception_handler(exc_type, _mapped(status, title))

    @app.exception_handler(Exception)
    def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled", error_type=type(exc).__name__, path=request.url.path)
        return problem(
            request, 500, "Internal error", "Something went wrong. Quote the request id."
        )


def _mapped(status: int, title: str) -> Any:  # noqa: ANN401 - Starlette handler signature
    def handler(request: Request, exc: Exception) -> JSONResponse:
        detail = _SAFE_DETAILS.get(type(exc), str(exc))
        return problem(request, status, title, detail)

    return handler
