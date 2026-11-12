"""OIDC mode: validate access tokens issued by an external identity provider.

Checks signature (keys from the provider's JWKS, cached and refreshed on an unknown key id),
issuer, audience, expiry and not-before with a configured clock skew, and an algorithm
allowlist. The role comes from a configured claim (a string or a list of groups). Users are
provisioned on first sight; no passwords are stored.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

import httpx
import jwt

from dealdesk.auth.port import AuthenticationError, Principal
from dealdesk.domain.models import UserRole
from dealdesk.ports.repositories import DuplicateEmailError, UserRepository

ALLOWED_ALGORITHMS = ("RS256", "PS256", "ES256", "EdDSA")
JWKS_TTL_SECONDS = 300.0
JWKS_TIMEOUT_SECONDS = 5.0
#: If a token carries several role groups, the most privileged wins.
ROLE_PRIORITY = (UserRole.ADMIN, UserRole.APPROVER, UserRole.ESTIMATOR, UserRole.VIEWER)
ROLE_PREFIX = "dealdesk:"


def fetch_jwks(url: str) -> dict[str, Any]:
    """Download a JWK set."""
    response = httpx.get(url, timeout=JWKS_TIMEOUT_SECONDS)
    response.raise_for_status()
    data: dict[str, Any] = response.json()
    return data


class JwksCache:
    """Caches a JWK set; refetches when stale or when a token names an unknown key."""

    def __init__(
        self,
        fetch: Callable[[], dict[str, Any]],
        ttl: float = JWKS_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetch = fetch
        self._ttl = ttl
        self._clock = clock
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at = -ttl
        self._lock = threading.Lock()

    def key(self, kid: str) -> jwt.PyJWK:
        """Return the key for `kid`, refreshing at most once per lookup."""
        with self._lock:
            if self._clock() - self._fetched_at >= self._ttl or kid not in self._keys:
                self._keys = {
                    k.key_id: k for k in jwt.PyJWKSet.from_dict(self._fetch()).keys if k.key_id
                }
                self._fetched_at = self._clock()
            if kid not in self._keys:
                raise AuthenticationError("unknown signing key")
            return self._keys[kid]


def map_role(claim: object) -> UserRole | None:
    """Map a role claim (a role name, or a list of names or `dealdesk:<role>` groups)."""
    values = [claim] if isinstance(claim, str) else claim if isinstance(claim, list) else []
    names = {str(v).removeprefix(ROLE_PREFIX).lower() for v in values}
    return next((role for role in ROLE_PRIORITY if role.value in names), None)


class OidcAuthenticator:
    """`AuthPort` for OIDC mode."""

    def __init__(
        self,
        *,
        jwks: JwksCache,
        issuer: str,
        audience: str,
        role_claim: str,
        leeway_seconds: int,
        users: UserRepository,
    ) -> None:
        self._jwks = jwks
        self._issuer = issuer
        self._audience = audience
        self._role_claim = role_claim
        self._leeway = leeway_seconds
        self._users = users

    def authenticate(self, access_token: str) -> Principal:
        """Validate the provider token and return (and provision) the user."""
        claims = self._verify(access_token)
        role = map_role(claims.get(self._role_claim))
        if role is None:
            raise AuthenticationError("token carries no Deal Desk role")
        subject = str(claims["sub"])
        email = str(claims.get("email") or f"{subject}@oidc.invalid")
        name = str(claims.get("name") or email)
        user = self._users.get_by_subject(subject)
        if user is None:
            try:
                user = self._users.create(
                    email=email,
                    display_name=name,
                    role=role,
                    password_hash=None,
                    external_subject=subject,
                )
            except DuplicateEmailError as exc:
                raise AuthenticationError("email already belongs to a local account") from exc
        elif user.role is not role:
            user = self._users.update(user.id, role=role)
        if not user.is_active:
            raise AuthenticationError("account deactivated")
        return Principal(user.id, user.email, user.display_name, role)

    def _verify(self, token: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") not in ALLOWED_ALGORITHMS:
                raise AuthenticationError("unexpected algorithm")
            key = self._jwks.key(str(header.get("kid", "")))
            claims: dict[str, Any] = jwt.decode(
                token,
                key,
                algorithms=list(ALLOWED_ALGORITHMS),
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway,
                options={"require": ["iss", "aud", "sub", "exp", "iat"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError(type(exc).__name__) from exc
        return claims
