"""Authentication port: turn an access token into a principal, or refuse."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from dealdesk.domain.models import UserRole


class AuthenticationError(Exception):
    """No valid, active identity. Always reported to clients as a plain 401."""


@dataclass(frozen=True, slots=True)
class Principal:
    """The signed-in user. `role` comes from our database (local) or the IdP (OIDC)."""

    user_id: UUID
    email: str
    display_name: str
    role: UserRole


class AuthPort(Protocol):
    """Validates access tokens."""

    def authenticate(self, access_token: str) -> Principal:
        """Return the principal or raise `AuthenticationError`."""
