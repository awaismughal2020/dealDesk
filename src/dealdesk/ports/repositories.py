"""Persistence ports. Adapters implement these; the application depends only on them.

Each method is one transaction. Methods that must be atomic across tables (token rotation,
recording a decision with its audit event) are single methods for that reason.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from dealdesk.domain.models import (
    Approval,
    AuditEvent,
    CaseStudy,
    InvoiceSchedule,
    PastProject,
    PipelineRecord,
    RateCard,
    TeamMember,
    UserRole,
)

JsonDict = dict[str, Any]


class DuplicateEmailError(Exception):
    """A user with this email already exists."""


class NotFoundError(Exception):
    """The requested record does not exist."""


# ---------------------------------------------------------------- users and sessions


@dataclass(frozen=True, slots=True)
class UserRecord:
    """A stored user. `password_hash` is None for OIDC users."""

    id: UUID
    email: str
    display_name: str
    role: UserRole
    is_active: bool
    password_hash: str | None
    failed_login_count: int
    locked_until: datetime | None
    external_subject: str | None
    created_at: datetime
    updated_at: datetime


class UserRepository(Protocol):
    """Users. Emails are unique case-insensitively."""

    def get(self, user_id: UUID) -> UserRecord | None:
        """Return the user or None."""

    def get_by_email(self, email: str) -> UserRecord | None:
        """Return the user with this email (case-insensitive) or None."""

    def get_by_subject(self, subject: str) -> UserRecord | None:
        """Return the user linked to an external identity-provider subject or None."""

    def list_all(self) -> list[UserRecord]:
        """Return all users ordered by email."""

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

    def record_login_failure(self, user_id: UUID, locked_until: datetime | None) -> UserRecord:
        """Increment the failure counter and set the lock expiry."""

    def reset_login_failures(self, user_id: UUID) -> None:
        """Clear the failure counter and lock."""


@dataclass(frozen=True, slots=True)
class RefreshTokenRecord:
    """A refresh token, stored only as a hash. Tokens in one family descend from one sign-in."""

    id: UUID
    family_id: UUID
    user_id: UUID
    token_hash: str
    expires_at: datetime
    created_at: datetime
    revoked_at: datetime | None = None
    replaced_by: UUID | None = None


class RefreshTokenRepository(Protocol):
    """Refresh tokens with rotation and family revocation."""

    def add(self, record: RefreshTokenRecord) -> None:
        """Store a new token."""

    def get_by_hash(self, token_hash: str) -> RefreshTokenRecord | None:
        """Look a token up by its hash."""

    def rotate(self, old_id: UUID, new: RefreshTokenRecord, now: datetime) -> bool:
        """Revoke `old_id` and store `new` atomically. False if `old_id` was already revoked."""

    def revoke(self, token_id: UUID, now: datetime) -> None:
        """Revoke one token."""

    def revoke_family(self, family_id: UUID, now: datetime) -> int:
        """Revoke every live token in a family. Returns how many were revoked."""

    def revoke_all_for_user(self, user_id: UUID, now: datetime) -> int:
        """Revoke every live token of a user (deactivation, role change)."""


# ---------------------------------------------------------------- audit


@dataclass(frozen=True, slots=True)
class AuditQuery:
    """Filters for reading the audit log."""

    action: str | None = None
    actor_id: UUID | None = None
    subject_id: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class StoredAuditEvent:
    """An audit event with its sequence number."""

    seq: int
    event: AuditEvent


class AuditLog(Protocol):
    """Append-only. There is deliberately no update or delete method."""

    def append(self, event: AuditEvent) -> None:
        """Record an event."""

    def query(self, query: AuditQuery) -> tuple[list[StoredAuditEvent], int]:
        """Return a page of events (newest first) and the total matching count."""


# ---------------------------------------------------------------- reference data


@dataclass(frozen=True, slots=True)
class Scored[T]:
    """A retrieved item and its cosine similarity (as a string, to keep floats out)."""

    item: T
    similarity: str


class ReferenceData(Protocol):
    """Rate card, team roster and retrieval over past projects and case studies."""

    def rate_card(self) -> RateCard:
        """Return the current rate card."""

    def team(self) -> list[TeamMember]:
        """Return the team roster."""

    def similar_projects(self, embedding: Sequence[float], k: int) -> list[Scored[PastProject]]:
        """Return the `k` past projects most similar to the embedding."""

    def similar_case_studies(self, embedding: Sequence[float], k: int) -> list[Scored[CaseStudy]]:
        """Return the `k` case studies most similar to the embedding."""


# ---------------------------------------------------------------- runs


class RunStatus(StrEnum):
    """Lifecycle of a run."""

    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    FAILED = "failed"


ACTIVE_STATUSES = frozenset({RunStatus.QUEUED, RunStatus.RUNNING})


@dataclass(frozen=True, slots=True)
class RunRecord:
    """A run and the latest output of each step (JSON documents written by the application)."""

    id: UUID
    title: str
    status: RunStatus
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    brief_document_id: UUID
    brief_filename: str
    start_date: date
    current_step: str | None = None
    revision_count: int = 0
    flags: list[str] = field(default_factory=list)
    requirements: JsonDict | None = None
    references: list[JsonDict] | None = None
    estimate: JsonDict | None = None
    quote: JsonDict | None = None
    resource_plan: JsonDict | None = None
    proposal: JsonDict | None = None
    proposal_document_id: UUID | None = None
    is_final: bool = False
    review_comment: str | None = None
    error: str | None = None


RUN_MUTABLE_FIELDS = frozenset(
    {
        "title",
        "status",
        "current_step",
        "revision_count",
        "flags",
        "requirements",
        "references",
        "estimate",
        "quote",
        "resource_plan",
        "proposal",
        "proposal_document_id",
        "is_final",
        "review_comment",
        "error",
    }
)


@dataclass(frozen=True, slots=True)
class StepRecord:
    """Timing and outcome of one execution of one workflow step."""

    run_id: UUID
    step: str
    attempt: int
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None
    detail: JsonDict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RunQuery:
    """Filters for listing runs."""

    status: RunStatus | None = None
    created_by: UUID | None = None
    limit: int = 50
    offset: int = 0


class RunRepository(Protocol):
    """Runs and their step history."""

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

    def get(self, run_id: UUID) -> RunRecord | None:
        """Return the run or None."""

    def brief_text(self, run_id: UUID) -> str:
        """Return the (untrusted) brief text of a run."""

    def list_runs(self, query: RunQuery) -> tuple[list[RunRecord], int]:
        """Return a page of runs (newest first) and the total count."""

    def update(self, run_id: UUID, changes: Mapping[str, object]) -> RunRecord:
        """Apply changes to fields in `RUN_MUTABLE_FIELDS`. Raises `NotFoundError`."""

    def transition_status(self, run_id: UUID, expected: RunStatus, new: RunStatus) -> bool:
        """Atomically move from `expected` to `new`. False if the run was not in `expected`."""

    def record_step(self, step: StepRecord) -> None:
        """Insert or replace the record for (run, step, attempt)."""

    def steps(self, run_id: UUID) -> list[StepRecord]:
        """Return step history in execution order."""

    def ids_with_status(self, statuses: frozenset[RunStatus]) -> list[UUID]:
        """Return ids of runs in any of the given statuses."""

    def mean_step_seconds(self) -> Mapping[str, str]:
        """Return mean measured duration per step name over successful steps (seconds)."""


class ApprovalRepository(Protocol):
    """Recorded human decisions."""

    def add(self, approval: Approval, audit: AuditEvent) -> None:
        """Store a decision and its audit event in one transaction."""

    def for_run(self, run_id: UUID) -> list[Approval]:
        """Return decisions for a run, oldest first."""


# ---------------------------------------------------------------- downstream systems


class CRMPort(Protocol):
    """Sales pipeline (a mock in this MVP)."""

    def upsert_pipeline_record(self, record: PipelineRecord) -> str:
        """Create the opportunity if it does not exist. Idempotent; returns its reference."""

    def get_pipeline_record(self, run_id: UUID) -> PipelineRecord | None:
        """Return the opportunity for a run, if any."""


class AccountingPort(Protocol):
    """Invoice schedules (a mock in this MVP)."""

    def upsert_invoice_schedule(self, run_id: UUID, schedule: InvoiceSchedule) -> None:
        """Store the milestones for a run. Idempotent."""

    def get_invoice_schedule(self, run_id: UUID) -> InvoiceSchedule | None:
        """Return the schedule for a run, if any."""


@dataclass(frozen=True, slots=True)
class StoredDocument:
    """A stored binary document."""

    id: UUID
    kind: str
    filename: str
    content_type: str
    content: bytes
    sha256: str
    created_at: datetime


class DocumentStorePort(Protocol):
    """Binary documents (uploaded briefs, generated proposals)."""

    def put(self, *, kind: str, filename: str, content_type: str, content: bytes) -> UUID:
        """Store a document and return its id."""

    def get(self, document_id: UUID) -> StoredDocument | None:
        """Return the document or None."""
