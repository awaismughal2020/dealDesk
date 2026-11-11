"""Short-lived access tokens: EdDSA (Ed25519) JWTs with a key id, verified against an allowlist.

Keys live in a folder (`make init`): `<kid>.pem` private keys plus `active_kid` naming the signer.
Every key in the folder verifies, so rotating (`make rotate-keys`) keeps old tokens valid until
they expire; the JWKS endpoint publishes all current public keys.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from dealdesk.domain.models import UserRole

ALGORITHM = "EdDSA"
ACTIVE_KID_FILE = "active_kid"
REQUIRED_CLAIMS = ("iss", "aud", "sub", "exp", "iat", "jti", "role")


class InvalidTokenError(Exception):
    """The token is missing, malformed, expired, unsigned, mis-signed or for someone else."""


class KeyConfigurationError(RuntimeError):
    """Signing keys are missing or inconsistent."""


@dataclass(frozen=True, slots=True)
class AccessClaims:
    """Verified claims. The role here is informational; the database role is authoritative."""

    subject: str
    role: str
    token_id: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class KeyRing:
    """Signing key plus every verification key, by key id."""

    active_kid: str
    private_keys: Mapping[str, Ed25519PrivateKey]

    @classmethod
    def load(cls, directory: Path) -> KeyRing:
        """Read `*.pem` keys and `active_kid` from a directory."""
        active = directory / ACTIVE_KID_FILE
        if not active.exists():
            raise KeyConfigurationError(f"no {ACTIVE_KID_FILE} in {directory}; run `make init`")
        keys: dict[str, Ed25519PrivateKey] = {}
        for pem in sorted(directory.glob("*.pem")):
            key = serialization.load_pem_private_key(pem.read_bytes(), password=None)
            if not isinstance(key, Ed25519PrivateKey):
                raise KeyConfigurationError(f"{pem.name} is not an Ed25519 key")
            keys[pem.stem] = key
        kid = active.read_text(encoding="utf-8").strip()
        if kid not in keys:
            raise KeyConfigurationError(f"active key {kid!r} not found in {directory}")
        return cls(kid, keys)

    @classmethod
    def generate(cls) -> KeyRing:
        """An in-memory key ring (tests)."""
        kid = uuid.uuid4().hex[:16]
        return cls(kid, {kid: Ed25519PrivateKey.generate()})

    def public_key(self, kid: str) -> Ed25519PublicKey | None:
        """Verification key for `kid`, if known."""
        key = self.private_keys.get(kid)
        return key.public_key() if key else None


class TokenService:
    """Issues and verifies access tokens."""

    def __init__(
        self,
        keys: KeyRing,
        *,
        issuer: str,
        audience: str,
        ttl_seconds: int,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._keys = keys
        self._issuer = issuer
        self._audience = audience
        self._ttl = timedelta(seconds=ttl_seconds)
        self._clock = clock

    def issue(self, user_id: uuid.UUID, role: UserRole) -> tuple[str, datetime]:
        """Return a signed token and its expiry."""
        now = self._clock()
        expires = now + self._ttl
        claims = {
            "iss": self._issuer,
            "aud": self._audience,
            "sub": str(user_id),
            "iat": int(now.timestamp()),
            "exp": int(expires.timestamp()),
            "jti": uuid.uuid4().hex,
            "role": role.value,
        }
        key = self._keys.private_keys[self._keys.active_kid]
        token = jwt.encode(claims, key, algorithm=ALGORITHM, headers={"kid": self._keys.active_kid})
        return token, expires

    def verify(self, token: str) -> AccessClaims:
        """Verify signature, algorithm, issuer, audience, expiry and required claims."""
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise InvalidTokenError("malformed token") from exc
        if header.get("alg") != ALGORITHM:
            raise InvalidTokenError("unexpected algorithm")
        key = self._keys.public_key(str(header.get("kid", "")))
        if key is None:
            raise InvalidTokenError("unknown signing key")
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key,
                algorithms=[ALGORITHM],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": list(REQUIRED_CLAIMS)},
            )
        except jwt.PyJWTError as exc:
            raise InvalidTokenError(type(exc).__name__) from exc
        return AccessClaims(
            subject=str(claims["sub"]),
            role=str(claims["role"]),
            token_id=str(claims["jti"]),
            expires_at=datetime.fromtimestamp(int(claims["exp"]), tz=UTC),
        )

    def jwks(self) -> dict[str, list[dict[str, str]]]:
        """Public keys (current and previous) as a JWK set."""
        keys = []
        for kid, private in sorted(self._keys.private_keys.items()):
            jwk: dict[str, str] = jwt.algorithms.OKPAlgorithm.to_jwk(
                private.public_key(), as_dict=True
            )
            keys.append({**jwk, "kid": kid, "alg": ALGORITHM, "use": "sig"})
        return {"keys": keys}
