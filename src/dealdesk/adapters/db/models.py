"""SQLAlchemy 2 typed ORM models. Money columns are NUMERIC; nothing monetary is stored as float."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBEDDING_DIM = 256
MONEY = Numeric(14, 2)
RATE = Numeric(10, 2)
HOURS = Numeric(10, 2)
RATIO = Numeric(6, 4)


class Base(DeclarativeBase):
    """Declarative base with a naming convention so migrations are deterministic."""

    type_annotation_map: ClassVar[dict[Any, Any]] = {dict[str, Any]: JSONB, list[Any]: JSONB}


Base.metadata.naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UserRow(Base):
    """A person who can sign in."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('viewer','estimator','approver','admin')", name="role"),
        Index("uq_users_email_lower", func.lower(text("email")), unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_subject: Mapped[str | None] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()


class RefreshTokenRow(Base):
    """A refresh token hash. The token itself is never stored."""

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = _now()
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class AuditEventRow(Base):
    """Append-only audit trail. A database trigger also rejects UPDATE and DELETE."""

    __tablename__ = "audit_events"

    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    subject_type: Mapped[str] = mapped_column(String(40), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    request_id: Mapped[str | None] = mapped_column(String(80))
    details: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)


class RateCardRow(Base):
    """SAMPLE rate card."""

    __tablename__ = "rate_card"

    role: Mapped[str] = mapped_column(String(60), primary_key=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    cost_rate: Mapped[Decimal] = mapped_column(RATE, nullable=False)
    sell_rate: Mapped[Decimal] = mapped_column(RATE, nullable=False)
    is_sample: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class TeamMemberRow(Base):
    """SAMPLE team roster."""

    __tablename__ = "team_members"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(ForeignKey("rate_card.role"), nullable=False)
    weekly_hours: Mapped[Decimal] = mapped_column(HOURS, nullable=False)
    is_sample: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class PastProjectRow(Base):
    """SAMPLE completed project with actual hours by role."""

    __tablename__ = "past_projects"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    sector: Mapped[str] = mapped_column(String(80), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    actual_hours: Mapped[dict[str, Any]] = mapped_column(nullable=False)
    embedding: Mapped[list[float]] = mapped_column(VECTOR(EMBEDDING_DIM), nullable=False)
    is_sample: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CaseStudyRow(Base):
    """SAMPLE case study that proposals cite by id."""

    __tablename__ = "case_studies"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("past_projects.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(VECTOR(EMBEDDING_DIM), nullable=False)
    is_sample: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class DocumentRow(Base):
    """Binary documents. Kept in Postgres so containers can run with read-only filesystems."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = _now()


class RunRow(Base):
    """A brief's journey through the workflow."""

    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','awaiting_approval','approved','failed')", name="status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()
    brief_document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)
    brief_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    brief_text: Mapped[str] = mapped_column(Text, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    current_step: Mapped[str | None] = mapped_column(String(40))
    revision_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    flags: Mapped[list[Any]] = mapped_column(nullable=False, default=list)
    requirements: Mapped[list[Any] | None] = mapped_column()
    references: Mapped[list[Any] | None] = mapped_column()
    estimate: Mapped[dict[str, Any] | None] = mapped_column()
    quote: Mapped[dict[str, Any] | None] = mapped_column()
    resource_plan: Mapped[dict[str, Any] | None] = mapped_column()
    proposal: Mapped[dict[str, Any] | None] = mapped_column()
    proposal_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id"))
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_comment: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)


class RunStepRow(Base):
    """One execution of one step (timings feed the impact panel's measured machine time)."""

    __tablename__ = "run_steps"
    __table_args__ = (UniqueConstraint("run_id", "step", "attempt", name="uq_run_steps_attempt"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step: Mapped[str] = mapped_column(String(40), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)


class ApprovalRow(Base):
    """A recorded human decision: who, when, why."""

    __tablename__ = "approvals"
    __table_args__ = (CheckConstraint("decision IN ('approved','rejected')", name="decision"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id"), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    decided_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PipelineRecordRow(Base):
    """Mock CRM: one opportunity per approved run."""

    __tablename__ = "pipeline_records"

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id"), primary_key=True)
    reference: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    margin: Mapped[Decimal] = mapped_column(RATIO, nullable=False)
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    approved_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = _now()


class InvoiceMilestoneRow(Base):
    """Mock accounting system: invoice milestones per approved run."""

    __tablename__ = "invoice_milestones"
    __table_args__ = (UniqueConstraint("run_id", "sequence", name="uq_invoice_milestones_seq"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    percentage: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    net: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    vat: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    gross: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    vat_rate: Mapped[Decimal] = mapped_column(RATIO, nullable=False)
