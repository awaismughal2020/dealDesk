"""Local authentication: passwords, our own access tokens, rotating refresh tokens."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from dealdesk.auth.passwords import PasswordHasher
from dealdesk.auth.port import AuthenticationError, Principal
from dealdesk.auth.ratelimit import SlidingWindowLimiter
from dealdesk.auth.tokens import InvalidTokenError, TokenService
from dealdesk.domain.models import AuditEvent
from dealdesk.ports.repositories import (
    AuditLog,
    RefreshTokenRecord,
    RefreshTokenRepository,
    UserRecord,
    UserRepository,
)

REFRESH_TOKEN_BYTES = 32
MAX_LOCKOUT = timedelta(hours=24)
BASE_DELAY_SECONDS = 0.1
MAX_DELAY_SECONDS = 2.0
GENERIC_LOGIN_ERROR = "Incorrect email or password, or the account is temporarily locked."


class LoginRejectedError(AuthenticationError):
    """Sign-in failed. The message never says which part was wrong."""


class TooManyAttemptsError(Exception):
    """Rate limit hit; `retry_after` seconds until the next attempt."""

    def __init__(self, retry_after: float) -> None:
        super().__init__("too many sign-in attempts")
        self.retry_after = retry_after


def hash_refresh_token(token: str) -> str:
    """Refresh tokens are stored only as SHA-256 hashes (they are high-entropy random values)."""
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Session:
    """What a successful sign-in or refresh hands back to the HTTP layer."""

    principal: Principal
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime


@dataclass(frozen=True, slots=True)
class LockoutPolicy:
    """Brute-force controls."""

    threshold: int
    lockout_seconds: int


def principal_of(user: UserRecord) -> Principal:
    """Build a principal from a stored user."""
    return Principal(user.id, user.email, user.display_name, user.role)


class LocalTokenAuthenticator:
    """`AuthPort` for local mode: verify our JWT, then load the user (DB role is authoritative)."""

    def __init__(self, tokens: TokenService, users: UserRepository) -> None:
        self._tokens = tokens
        self._users = users

    def authenticate(self, access_token: str) -> Principal:
        """Return the active user behind a valid token."""
        try:
            claims = self._tokens.verify(access_token)
            user = self._users.get(UUID(claims.subject))
        except (InvalidTokenError, ValueError) as exc:
            raise AuthenticationError(str(exc)) from exc
        if user is None or not user.is_active:
            raise AuthenticationError("unknown or inactive user")
        return principal_of(user)


class LocalSessionService:
    """Sign-in, refresh with rotation and reuse detection, and sign-out."""

    def __init__(
        self,
        *,
        users: UserRepository,
        refresh_tokens: RefreshTokenRepository,
        hasher: PasswordHasher,
        tokens: TokenService,
        audit: AuditLog,
        lockout: LockoutPolicy,
        ip_limiter: SlidingWindowLimiter,
        account_limiter: SlidingWindowLimiter,
        refresh_ttl_seconds: int,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._users = users
        self._refresh = refresh_tokens
        self._hasher = hasher
        self._tokens = tokens
        self._audit = audit
        self._lockout = lockout
        self._ip_limiter = ip_limiter
        self._account_limiter = account_limiter
        self._refresh_ttl = timedelta(seconds=refresh_ttl_seconds)
        self._clock = clock
        self._sleep = sleep

    # ------------------------------------------------------------ sign-in

    def login(self, email: str, password: str, *, ip: str, request_id: str | None) -> Session:
        """Authenticate with email and password. Every failure looks the same to the caller."""
        normalized = email.strip().lower()
        for limiter, key in (
            (self._ip_limiter, f"ip:{ip}"),
            (self._account_limiter, f"acct:{normalized}"),
        ):
            retry_after = limiter.hit(key)
            if retry_after is not None:
                self._log("auth.login_rate_limited", None, normalized, request_id, {"ip": ip})
                raise TooManyAttemptsError(retry_after)
        user = self._users.get_by_email(normalized)
        now = self._clock()
        valid = self._hasher.verify(user.password_hash if user else None, password)
        if user is None or not valid or not user.is_active or _locked(user, now):
            self._fail(user, normalized, ip, request_id, now, password_ok=valid)
            raise LoginRejectedError(GENERIC_LOGIN_ERROR)
        self._users.reset_login_failures(user.id)
        if user.password_hash and self._hasher.needs_rehash(user.password_hash):
            self._users.update(user.id, password_hash=self._hasher.hash(password))
        session = self._issue(user, family_id=uuid.uuid4(), now=now)
        self._log("auth.login_succeeded", user.id, str(user.id), request_id, {"ip": ip})
        return session

    def _fail(
        self,
        user: UserRecord | None,
        normalized: str,
        ip: str,
        request_id: str | None,
        now: datetime,
        *,
        password_ok: bool,
    ) -> None:
        reason = "unknown_user"
        delay = BASE_DELAY_SECONDS
        if user is not None:
            reason = (
                "locked"
                if _locked(user, now)
                else "inactive"
                if not user.is_active
                else "bad_password"
            )
            if not password_ok or reason == "locked":
                failures = user.failed_login_count + 1
                locked_until = user.locked_until
                if failures >= self._lockout.threshold:
                    multiplier = 2 ** (failures - self._lockout.threshold)
                    locked_until = now + min(
                        timedelta(seconds=self._lockout.lockout_seconds * multiplier), MAX_LOCKOUT
                    )
                self._users.record_login_failure(user.id, locked_until)
                delay = min(MAX_DELAY_SECONDS, BASE_DELAY_SECONDS * 2 ** (failures - 1))
        subject = str(user.id) if user else hashlib.sha256(normalized.encode()).hexdigest()[:16]
        self._log(
            "auth.login_failed",
            user.id if user else None,
            subject,
            request_id,
            {"ip": ip, "reason": reason},
        )
        if self._sleep is not None:
            self._sleep(delay)  # progressive delay slows online guessing

    # ------------------------------------------------------------ refresh and sign-out

    def refresh(self, refresh_token: str, *, request_id: str | None) -> Session:
        """Rotate a refresh token. Presenting a used token revokes the whole family."""
        now = self._clock()
        record = self._refresh.get_by_hash(hash_refresh_token(refresh_token))
        if record is None or record.expires_at <= now:
            raise AuthenticationError("invalid refresh token")
        if record.revoked_at is not None:
            revoked = self._refresh.revoke_family(record.family_id, now)
            self._log(
                "auth.refresh_token_reuse",
                record.user_id,
                str(record.user_id),
                request_id,
                {"family": str(record.family_id), "revoked": str(revoked)},
            )
            raise AuthenticationError("refresh token reuse detected")
        user = self._users.get(record.user_id)
        if user is None or not user.is_active:
            self._refresh.revoke_family(record.family_id, now)
            raise AuthenticationError("inactive user")
        new_token = secrets.token_urlsafe(REFRESH_TOKEN_BYTES)
        new_record = self._record(user.id, record.family_id, new_token, now)
        if not self._refresh.rotate(record.id, new_record, now):
            self._refresh.revoke_family(record.family_id, now)
            self._log(
                "auth.refresh_token_reuse", user.id, str(user.id), request_id, {"race": "true"}
            )
            raise AuthenticationError("refresh token reuse detected")
        access, access_expires = self._tokens.issue(user.id, user.role)
        return Session(principal_of(user), access, access_expires, new_token, new_record.expires_at)

    def logout(
        self, refresh_token: str | None, principal: Principal, *, request_id: str | None
    ) -> None:
        """Revoke the presented refresh token's family on the server."""
        if refresh_token:
            record = self._refresh.get_by_hash(hash_refresh_token(refresh_token))
            if record is not None and record.user_id == principal.user_id:
                self._refresh.revoke_family(record.family_id, self._clock())
        self._log("auth.logout", principal.user_id, str(principal.user_id), request_id, {})

    def revoke_all(self, user_id: UUID) -> None:
        """Revoke every session of a user (deactivation, role change)."""
        self._refresh.revoke_all_for_user(user_id, self._clock())

    # ------------------------------------------------------------ helpers

    def _issue(self, user: UserRecord, *, family_id: UUID, now: datetime) -> Session:
        refresh_token = secrets.token_urlsafe(REFRESH_TOKEN_BYTES)
        record = self._record(user.id, family_id, refresh_token, now)
        self._refresh.add(record)
        access, access_expires = self._tokens.issue(user.id, user.role)
        return Session(principal_of(user), access, access_expires, refresh_token, record.expires_at)

    def _record(
        self, user_id: UUID, family_id: UUID, token: str, now: datetime
    ) -> RefreshTokenRecord:
        return RefreshTokenRecord(
            id=uuid.uuid4(),
            family_id=family_id,
            user_id=user_id,
            token_hash=hash_refresh_token(token),
            expires_at=now + self._refresh_ttl,
            created_at=now,
        )

    def _log(
        self,
        action: str,
        actor: UUID | None,
        subject: str,
        request_id: str | None,
        details: dict[str, str],
    ) -> None:
        self._audit.append(
            AuditEvent(action, actor, "user", subject, self._clock(), request_id, details)
        )


def _locked(user: UserRecord, now: datetime) -> bool:
    return user.locked_until is not None and user.locked_until > now
