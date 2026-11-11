"""CSRF protection: double-submit token plus an Origin check on state-changing requests."""

from __future__ import annotations

import hmac
import secrets
from collections.abc import Iterable

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
TOKEN_BYTES = 32


def new_csrf_token() -> str:
    """Return a fresh random token for the CSRF cookie."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def origin_allowed(origin: str | None, referer: str | None, allowed: Iterable[str]) -> bool:
    """Require an Origin (or, failing that, a Referer) from the allowed list."""
    allowed_set = {a.rstrip("/") for a in allowed}
    if origin:
        return origin.rstrip("/") in allowed_set
    if referer:
        return any(referer == a or referer.startswith(a + "/") for a in allowed_set)
    return False


def tokens_match(cookie_token: str | None, header_token: str | None) -> bool:
    """Constant-time comparison of the cookie and header tokens."""
    if not cookie_token or not header_token:
        return False
    return hmac.compare_digest(cookie_token.encode(), header_token.encode())
