"""Append-only audit log. No update or delete path exists here or anywhere in the app."""

from __future__ import annotations

from sqlalchemy import ColumnElement, func, select

from dealdesk.adapters.db.models import AuditEventRow
from dealdesk.adapters.db.session import SessionFactory
from dealdesk.domain.models import AuditEvent
from dealdesk.ports.repositories import AuditQuery, StoredAuditEvent


def _event(row: AuditEventRow) -> StoredAuditEvent:
    return StoredAuditEvent(
        seq=row.seq,
        event=AuditEvent(
            action=row.action,
            actor_id=row.actor_id,
            subject_type=row.subject_type,
            subject_id=row.subject_id,
            occurred_at=row.occurred_at,
            request_id=row.request_id,
            details={str(k): str(v) for k, v in row.details.items()},
        ),
    )


class SqlAuditLog:
    """Writes and pages through audit events."""

    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    def append(self, event: AuditEvent) -> None:
        """Record an event in its own transaction."""
        with self._sessions.begin() as session:
            session.add(to_row(event))

    def query(self, query: AuditQuery) -> tuple[list[StoredAuditEvent], int]:
        """Return a page of events (newest first) and the total matching count."""
        conditions: list[ColumnElement[bool]] = []
        if query.action:
            conditions.append(AuditEventRow.action == query.action)
        if query.actor_id:
            conditions.append(AuditEventRow.actor_id == query.actor_id)
        if query.subject_id:
            conditions.append(AuditEventRow.subject_id == query.subject_id)
        if query.since:
            conditions.append(AuditEventRow.occurred_at >= query.since)
        if query.until:
            conditions.append(AuditEventRow.occurred_at < query.until)
        with self._sessions() as session:
            total = session.scalar(
                select(func.count()).select_from(AuditEventRow).where(*conditions)
            )
            rows = session.scalars(
                select(AuditEventRow)
                .where(*conditions)
                .order_by(AuditEventRow.seq.desc())
                .limit(query.limit)
                .offset(query.offset)
            )
            return [_event(r) for r in rows], int(total or 0)


def to_row(event: AuditEvent) -> AuditEventRow:
    """Map a domain audit event to a row (also used inside multi-table transactions)."""
    return AuditEventRow(
        occurred_at=event.occurred_at,
        action=event.action,
        actor_id=event.actor_id,
        subject_type=event.subject_type,
        subject_id=event.subject_id,
        request_id=event.request_id,
        details=dict(event.details),
    )
