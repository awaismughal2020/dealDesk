"""User and refresh-token repositories."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from dealdesk.adapters.db.models import RefreshTokenRow, UserRow
from dealdesk.adapters.db.session import SessionFactory
from dealdesk.domain.models import UserRole
from dealdesk.ports.repositories import (
    DuplicateEmailError,
    NotFoundError,
    RefreshTokenRecord,
    UserRecord,
)


def _user(row: UserRow) -> UserRecord:
    return UserRecord(
        id=row.id,
        email=row.email,
        display_name=row.display_name,
        role=UserRole(row.role),
        is_active=row.is_active,
        password_hash=row.password_hash,
        failed_login_count=row.failed_login_count,
        locked_until=row.locked_until,
        external_subject=row.external_subject,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlUserRepository:
    """Users in Postgres. Email uniqueness is enforced on lower(email)."""

    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    def get(self, user_id: UUID) -> UserRecord | None:
        """Return the user or None."""
        with self._sessions() as session:
            row = session.get(UserRow, user_id)
            return _user(row) if row else None

    def get_by_email(self, email: str) -> UserRecord | None:
        """Return the user with this email (case-insensitive) or None."""
        with self._sessions() as session:
            row = session.scalar(select(UserRow).where(func.lower(UserRow.email) == email.lower()))
            return _user(row) if row else None

    def get_by_subject(self, subject: str) -> UserRecord | None:
        """Return the user linked to an identity-provider subject or None."""
        with self._sessions() as session:
            row = session.scalar(select(UserRow).where(UserRow.external_subject == subject))
            return _user(row) if row else None

    def list_all(self) -> list[UserRecord]:
        """Return all users ordered by email."""
        with self._sessions() as session:
            return [_user(r) for r in session.scalars(select(UserRow).order_by(UserRow.email))]

    def create(
        self,
        *,
        email: str,
        display_name: str,
        role: UserRole,
        password_hash: str | None,
        external_subject: str | None = None,
    ) -> UserRecord:
        """Insert a user. Raises `DuplicateEmailError`."""
        row = UserRow(
            id=uuid.uuid4(),
            email=email,
            display_name=display_name,
            role=role.value,
            password_hash=password_hash,
            external_subject=external_subject,
            is_active=True,
            failed_login_count=0,
        )
        try:
            with self._sessions.begin() as session:
                session.add(row)
                session.flush()
                session.refresh(row)
                return _user(row)
        except IntegrityError as exc:
            raise DuplicateEmailError(email) from exc

    def update(
        self,
        user_id: UUID,
        *,
        role: UserRole | None = None,
        is_active: bool | None = None,
        display_name: str | None = None,
        password_hash: str | None = None,
    ) -> UserRecord:
        """Change the given fields. Raises `NotFoundError`."""
        with self._sessions.begin() as session:
            row = session.get(UserRow, user_id, with_for_update=True)
            if row is None:
                raise NotFoundError(str(user_id))
            if role is not None:
                row.role = role.value
            if is_active is not None:
                row.is_active = is_active
            if display_name is not None:
                row.display_name = display_name
            if password_hash is not None:
                row.password_hash = password_hash
            row.updated_at = datetime.now(UTC)
            session.flush()
            session.refresh(row)
            return _user(row)

    def record_login_failure(self, user_id: UUID, locked_until: datetime | None) -> UserRecord:
        """Increment the failure counter atomically and set the lock expiry."""
        with self._sessions.begin() as session:
            session.execute(
                update(UserRow)
                .where(UserRow.id == user_id)
                .values(
                    failed_login_count=UserRow.failed_login_count + 1, locked_until=locked_until
                )
            )
            row = session.get(UserRow, user_id, populate_existing=True)
            if row is None:
                raise NotFoundError(str(user_id))
            return _user(row)

    def reset_login_failures(self, user_id: UUID) -> None:
        """Clear the failure counter and lock."""
        with self._sessions.begin() as session:
            session.execute(
                update(UserRow)
                .where(UserRow.id == user_id)
                .values(failed_login_count=0, locked_until=None)
            )


def _token(row: RefreshTokenRow) -> RefreshTokenRecord:
    return RefreshTokenRecord(
        id=row.id,
        family_id=row.family_id,
        user_id=row.user_id,
        token_hash=row.token_hash,
        expires_at=row.expires_at,
        created_at=row.created_at,
        revoked_at=row.revoked_at,
        replaced_by=row.replaced_by,
    )


class SqlRefreshTokenRepository:
    """Refresh-token hashes with atomic rotation."""

    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    def add(self, record: RefreshTokenRecord) -> None:
        """Store a new token."""
        with self._sessions.begin() as session:
            session.add(self._row(record))

    def get_by_hash(self, token_hash: str) -> RefreshTokenRecord | None:
        """Look a token up by its hash."""
        with self._sessions() as session:
            row = session.scalar(
                select(RefreshTokenRow).where(RefreshTokenRow.token_hash == token_hash)
            )
            return _token(row) if row else None

    def rotate(self, old_id: UUID, new: RefreshTokenRecord, now: datetime) -> bool:
        """Revoke `old_id` and store `new` in one transaction; False if already revoked."""
        with self._sessions.begin() as session:
            result = session.execute(
                update(RefreshTokenRow)
                .where(RefreshTokenRow.id == old_id, RefreshTokenRow.revoked_at.is_(None))
                .values(revoked_at=now, replaced_by=new.id)
            )
            if result.rowcount != 1:  # type: ignore[attr-defined]
                return False
            session.add(self._row(new))
            return True

    def revoke(self, token_id: UUID, now: datetime) -> None:
        """Revoke one token."""
        with self._sessions.begin() as session:
            session.execute(
                update(RefreshTokenRow)
                .where(RefreshTokenRow.id == token_id, RefreshTokenRow.revoked_at.is_(None))
                .values(revoked_at=now)
            )

    def revoke_family(self, family_id: UUID, now: datetime) -> int:
        """Revoke every live token in a family."""
        return self._revoke_where(RefreshTokenRow.family_id == family_id, now)

    def revoke_all_for_user(self, user_id: UUID, now: datetime) -> int:
        """Revoke every live token of a user."""
        return self._revoke_where(RefreshTokenRow.user_id == user_id, now)

    def _revoke_where(self, condition: object, now: datetime) -> int:
        with self._sessions.begin() as session:
            result = session.execute(
                update(RefreshTokenRow)
                .where(condition, RefreshTokenRow.revoked_at.is_(None))  # type: ignore[arg-type]
                .values(revoked_at=now)
            )
            count: int = result.rowcount  # type: ignore[attr-defined]
            return count

    @staticmethod
    def _row(record: RefreshTokenRecord) -> RefreshTokenRow:
        return RefreshTokenRow(
            id=record.id,
            family_id=record.family_id,
            user_id=record.user_id,
            token_hash=record.token_hash,
            expires_at=record.expires_at,
            created_at=record.created_at,
            revoked_at=record.revoked_at,
            replaced_by=record.replaced_by,
        )
