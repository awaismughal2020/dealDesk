"""Run use cases: create a run from a brief, and record a human decision on it."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID

from dealdesk.application.runner import WorkflowRunner
from dealdesk.domain.approval import ensure_separation_of_duties
from dealdesk.domain.models import Approval, AuditEvent, Decision, UserRole
from dealdesk.ports.repositories import (
    ApprovalRepository,
    AuditLog,
    DocumentStorePort,
    NotFoundError,
    RunRecord,
    RunRepository,
    RunStatus,
)

MONDAY = 0
MAX_TITLE_CHARS = 200
MAX_COMMENT_CHARS = 2000


class InvalidRunStateError(Exception):
    """The run is not in a state that allows this action."""


class CommentRequiredError(ValueError):
    """A rejection must say why."""


class ForbiddenActionError(PermissionError):
    """The actor's role does not allow this action (checked again here, after the API)."""


@dataclass(frozen=True, slots=True)
class Actor:
    """Who is acting, as established by authentication."""

    id: UUID
    role: UserRole


@dataclass(frozen=True, slots=True)
class BriefUpload:
    """A validated upload: original bytes plus the extracted text."""

    filename: str
    content_type: str
    content: bytes
    text: str
    title: str


def next_start_date(today: date, lead_days: int) -> date:
    """First Monday at least `lead_days` from today (a date computed by code, not a model)."""
    candidate = today + timedelta(days=lead_days)
    return candidate + timedelta(days=(MONDAY - candidate.weekday()) % 7)


class RunService:
    """Creates runs and records decisions. Authorisation rules are re-checked here."""

    def __init__(
        self,
        *,
        runs: RunRepository,
        approvals: ApprovalRepository,
        documents: DocumentStorePort,
        audit: AuditLog,
        runner: WorkflowRunner,
        clock: Callable[[], datetime],
        start_lead_days: int,
    ) -> None:
        self._runs = runs
        self._approvals = approvals
        self._documents = documents
        self._audit = audit
        self._runner = runner
        self._clock = clock
        self._lead_days = start_lead_days

    def create(self, actor: Actor, upload: BriefUpload, request_id: str | None) -> RunRecord:
        """Store the brief, create a queued run and start the workflow."""
        if actor.role not in {UserRole.ESTIMATOR, UserRole.ADMIN}:
            raise ForbiddenActionError("only estimators and admins can create runs")
        now = self._clock()
        document_id = self._documents.put(
            kind="brief",
            filename=upload.filename,
            content_type=upload.content_type,
            content=upload.content,
        )
        run = self._runs.create(
            run_id=uuid.uuid4(),
            title=upload.title[:MAX_TITLE_CHARS] or "Untitled brief",
            created_by=actor.id,
            brief_document_id=document_id,
            brief_filename=upload.filename,
            brief_text=upload.text,
            start_date=next_start_date(now.date(), self._lead_days),
        )
        self._audit.append(
            AuditEvent(
                "run.created",
                actor.id,
                "run",
                str(run.id),
                now,
                request_id,
                {"filename": upload.filename, "bytes": str(len(upload.content))},
            )
        )
        self._runner.start(run.id, request_id)
        return run

    def decide(
        self,
        actor: Actor,
        run_id: UUID,
        decision: Decision,
        comment: str,
        request_id: str | None,
    ) -> RunRecord:
        """Record an approval or rejection, then resume the workflow."""
        if actor.role is not UserRole.APPROVER:
            raise ForbiddenActionError("only approvers can approve or reject runs")
        run = self._runs.get(run_id)
        if run is None:
            raise NotFoundError(str(run_id))
        ensure_separation_of_duties(actor.id, run.created_by)
        comment = comment.strip()[:MAX_COMMENT_CHARS]
        if decision is Decision.REJECTED and not comment:
            raise CommentRequiredError("a rejection needs a comment")
        if not self._runs.transition_status(run_id, RunStatus.AWAITING_APPROVAL, RunStatus.RUNNING):
            raise InvalidRunStateError("this run is not awaiting approval")
        now = self._clock()
        quote = run.quote or {}
        try:
            self._approvals.add(
                Approval(run_id, actor.id, decision, comment, now),
                AuditEvent(
                    f"run.{decision.value}",
                    actor.id,
                    "run",
                    str(run_id),
                    now,
                    request_id,
                    {
                        "price": str(quote.get("price")),
                        "margin": str(quote.get("margin")),
                        "flags": ",".join(run.flags),
                        "comment_chars": str(len(comment)),
                    },
                ),
            )
        except Exception:
            self._runs.transition_status(run_id, RunStatus.RUNNING, RunStatus.AWAITING_APPROVAL)
            raise
        self._runner.resume(run_id, {"decision": decision.value, "comment": comment})
        updated = self._runs.get(run_id)
        if updated is None:  # pragma: no cover - the run cannot disappear
            raise NotFoundError(str(run_id))
        return updated
