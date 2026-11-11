"""Runs, step history, approvals and documents."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from dealdesk.adapters.db.audit import to_row
from dealdesk.adapters.db.models import ApprovalRow, DocumentRow, RunRow, RunStepRow
from dealdesk.adapters.db.session import SessionFactory
from dealdesk.domain.models import Approval, AuditEvent, Decision
from dealdesk.ports.repositories import (
    RUN_MUTABLE_FIELDS,
    NotFoundError,
    RunQuery,
    RunRecord,
    RunStatus,
    StepRecord,
    StoredDocument,
)

MS_PER_SECOND = Decimal(1000)
SECONDS_PLACES = Decimal("0.001")


def _run(row: RunRow) -> RunRecord:
    return RunRecord(
        id=row.id,
        title=row.title,
        status=RunStatus(row.status),
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        brief_document_id=row.brief_document_id,
        brief_filename=row.brief_filename,
        start_date=row.start_date,
        current_step=row.current_step,
        revision_count=row.revision_count,
        flags=list(row.flags),
        requirements=row.requirements,
        references=row.references,
        estimate=row.estimate,
        quote=row.quote,
        resource_plan=row.resource_plan,
        proposal=row.proposal,
        proposal_document_id=row.proposal_document_id,
        is_final=row.is_final,
        review_comment=row.review_comment,
        error=row.error,
    )


def _step(row: RunStepRow) -> StepRecord:
    return StepRecord(
        run_id=row.run_id,
        step=row.step,
        attempt=row.attempt,
        status=row.status,
        started_at=row.started_at,
        finished_at=row.finished_at,
        duration_ms=row.duration_ms,
        detail=row.detail,
    )


class SqlRunRepository:
    """Runs in Postgres."""

    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    def create(
        self,
        *,
        run_id: UUID,
        title: str,
        created_by: UUID,
        brief_document_id: UUID,
        brief_filename: str,
        brief_text: str,
        start_date: date,
    ) -> RunRecord:
        """Insert a queued run."""
        row = RunRow(
            id=run_id,
            title=title,
            status=RunStatus.QUEUED.value,
            created_by=created_by,
            brief_document_id=brief_document_id,
            brief_filename=brief_filename,
            brief_text=brief_text,
            start_date=start_date,
            revision_count=0,
            flags=[],
            is_final=False,
        )
        with self._sessions.begin() as session:
            session.add(row)
            session.flush()
            session.refresh(row)
            return _run(row)

    def get(self, run_id: UUID) -> RunRecord | None:
        """Return the run or None."""
        with self._sessions() as session:
            row = session.get(RunRow, run_id)
            return _run(row) if row else None

    def brief_text(self, run_id: UUID) -> str:
        """Return the untrusted brief text."""
        with self._sessions() as session:
            text = session.scalar(select(RunRow.brief_text).where(RunRow.id == run_id))
            if text is None:
                raise NotFoundError(str(run_id))
            return text

    def list_runs(self, query: RunQuery) -> tuple[list[RunRecord], int]:
        """Return a page of runs, newest first, and the total count."""
        conditions = []
        if query.status:
            conditions.append(RunRow.status == query.status.value)
        if query.created_by:
            conditions.append(RunRow.created_by == query.created_by)
        with self._sessions() as session:
            total = session.scalar(select(func.count()).select_from(RunRow).where(*conditions))
            rows = session.scalars(
                select(RunRow)
                .where(*conditions)
                .order_by(RunRow.created_at.desc(), RunRow.id)
                .limit(query.limit)
                .offset(query.offset)
            )
            return [_run(r) for r in rows], int(total or 0)

    def update(self, run_id: UUID, changes: Mapping[str, object]) -> RunRecord:
        """Apply whitelisted changes."""
        unknown = set(changes) - RUN_MUTABLE_FIELDS
        if unknown:
            raise ValueError(f"cannot update run fields: {sorted(unknown)}")
        with self._sessions.begin() as session:
            row = session.get(RunRow, run_id, with_for_update=True)
            if row is None:
                raise NotFoundError(str(run_id))
            for key, value in changes.items():
                setattr(row, key, value.value if isinstance(value, RunStatus) else value)
            row.updated_at = datetime.now(UTC)
            session.flush()
            session.refresh(row)
            return _run(row)

    def record_step(self, step: StepRecord) -> None:
        """Upsert the record for (run, step, attempt)."""
        values = {
            "run_id": step.run_id,
            "step": step.step,
            "attempt": step.attempt,
            "status": step.status,
            "started_at": step.started_at,
            "finished_at": step.finished_at,
            "duration_ms": step.duration_ms,
            "detail": step.detail,
        }
        statement = insert(RunStepRow).values(**values)
        statement = statement.on_conflict_do_update(
            constraint="uq_run_steps_attempt",
            set_={
                k: statement.excluded[k] for k in ("status", "finished_at", "duration_ms", "detail")
            },
        )
        with self._sessions.begin() as session:
            session.execute(statement)

    def steps(self, run_id: UUID) -> list[StepRecord]:
        """Return step history in execution order."""
        with self._sessions() as session:
            rows = session.scalars(
                select(RunStepRow).where(RunStepRow.run_id == run_id).order_by(RunStepRow.id)
            )
            return [_step(r) for r in rows]

    def ids_with_status(self, statuses: frozenset[RunStatus]) -> list[UUID]:
        """Return ids of runs in any of the statuses."""
        with self._sessions() as session:
            return list(
                session.scalars(
                    select(RunRow.id).where(RunRow.status.in_([s.value for s in statuses]))
                )
            )

    def mean_step_seconds(self) -> Mapping[str, str]:
        """Mean duration per step over completed step executions, in seconds (string)."""
        with self._sessions() as session:
            rows = session.execute(
                select(RunStepRow.step, func.avg(RunStepRow.duration_ms))
                .where(RunStepRow.status == "completed", RunStepRow.duration_ms.is_not(None))
                .group_by(RunStepRow.step)
            ).all()
            return {
                step: str((Decimal(str(avg)) / MS_PER_SECOND).quantize(SECONDS_PLACES))
                for step, avg in rows
            }


class SqlApprovalRepository:
    """Approvals, written atomically with their audit event."""

    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    def add(self, approval: Approval, audit: AuditEvent) -> None:
        """Store the decision and its audit event in one transaction."""
        with self._sessions.begin() as session:
            session.add(
                ApprovalRow(
                    run_id=approval.run_id,
                    decision=approval.decision.value,
                    decided_by=approval.decided_by,
                    comment=approval.comment,
                    decided_at=approval.decided_at,
                )
            )
            session.add(to_row(audit))

    def for_run(self, run_id: UUID) -> list[Approval]:
        """Return decisions for a run, oldest first."""
        with self._sessions() as session:
            rows = session.scalars(
                select(ApprovalRow).where(ApprovalRow.run_id == run_id).order_by(ApprovalRow.id)
            )
            return [
                Approval(r.run_id, r.decided_by, Decision(r.decision), r.comment, r.decided_at)
                for r in rows
            ]


class SqlDocumentStore:
    """Documents stored as bytea with a SHA-256 for integrity."""

    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    def put(self, *, kind: str, filename: str, content_type: str, content: bytes) -> UUID:
        """Store a document and return its id."""
        document_id = uuid.uuid4()
        with self._sessions.begin() as session:
            session.add(
                DocumentRow(
                    id=document_id,
                    kind=kind,
                    filename=filename,
                    content_type=content_type,
                    content=content,
                    sha256=hashlib.sha256(content).hexdigest(),
                )
            )
        return document_id

    def get(self, document_id: UUID) -> StoredDocument | None:
        """Return the document or None."""
        with self._sessions() as session:
            row = session.get(DocumentRow, document_id)
            if row is None:
                return None
            return StoredDocument(
                id=row.id,
                kind=row.kind,
                filename=row.filename,
                content_type=row.content_type,
                content=row.content,
                sha256=row.sha256,
                created_at=row.created_at,
            )
