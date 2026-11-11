"""Argon2id password hashing and an NIST SP 800-63B style password policy.

Policy: at least 12 characters, at most 128, no composition rules, no forced rotation, and a
bundled denylist of common passwords plus a few context checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

from argon2 import PasswordHasher as Argon2Hasher
from argon2 import Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MIN_LENGTH = 12
MAX_LENGTH = 128
MIN_DISTINCT_CHARACTERS = 4


class PasswordPolicyError(ValueError):
    """The password does not meet the policy. The message is safe to show the user."""


@lru_cache(maxsize=1)
def _denylist() -> frozenset[str]:
    text = resources.files("dealdesk.auth").joinpath("common_passwords.txt").read_text("utf-8")
    return frozenset(
        line.strip().lower()
        for line in text.splitlines()
        if line.strip() and not line.startswith("#")
    )


def check_password_policy(password: str, *, email: str = "") -> None:
    """Raise `PasswordPolicyError` if the password is too short, too long or too guessable."""
    if len(password) < MIN_LENGTH:
        raise PasswordPolicyError(f"Use at least {MIN_LENGTH} characters.")
    if len(password) > MAX_LENGTH:
        raise PasswordPolicyError(f"Use at most {MAX_LENGTH} characters.")
    lowered = password.lower()
    if lowered in _denylist():
        raise PasswordPolicyError("This password is too common. Choose another.")
    if len(set(password)) < MIN_DISTINCT_CHARACTERS:
        raise PasswordPolicyError("This password is too repetitive. Choose another.")
    local_part = email.split("@", 1)[0].lower()
    if local_part and len(local_part) >= MIN_DISTINCT_CHARACTERS and local_part in lowered:
        raise PasswordPolicyError("Do not include your email address in the password.")


@dataclass(frozen=True, slots=True)
class Argon2Params:
    """Argon2id cost parameters (from configuration)."""

    time_cost: int
    memory_cost_kib: int
    parallelism: int


class PasswordHasher:
    """Hashes and verifies passwords with Argon2id. Verification is constant-time in argon2."""

    def __init__(self, params: Argon2Params) -> None:
        self._hasher = Argon2Hasher(
            time_cost=params.time_cost,
            memory_cost=params.memory_cost_kib,
            parallelism=params.parallelism,
            type=Type.ID,
        )
        # Verified against when the user does not exist, so timing matches a real check.
        self._dummy_hash = self._hasher.hash("dummy-password-for-timing-equalisation")

    def hash(self, password: str) -> str:
        """Return an encoded Argon2id hash (salt and parameters included)."""
        return self._hasher.hash(password)

    def verify(self, password_hash: str | None, password: str) -> bool:
        """Return True if `password` matches. With no hash, burn equivalent time and fail."""
        try:
            return self._hasher.verify(password_hash or self._dummy_hash, password) and (
                password_hash is not None
            )
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        """Return True if the hash was made with weaker parameters than configured."""
        return self._hasher.check_needs_rehash(password_hash)
