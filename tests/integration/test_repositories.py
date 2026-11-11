from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from dealdesk.adapters.accounting_mock import MockAccounting
from dealdesk.adapters.crm_mock import MockCRM
from dealdesk.adapters.db.audit import SqlAuditLog
from dealdesk.adapters.db.reference import SqlReferenceData
from dealdesk.adapters.db.runs import SqlApprovalRepository, SqlDocumentStore, SqlRunRepository
from dealdesk.adapters.db.session import SessionFactory
from dealdesk.adapters.db.users import SqlRefreshTokenRepository, SqlUserRepository
from dealdesk.adapters.embeddings.fake import FakeEmbedder
from dealdesk.domain.invoicing import build_invoice_schedule
from dealdesk.domain.models import (
    Approval,
    AuditEvent,
    Decision,
    InvoicePolicy,
    PipelineRecord,
    UserRole,
)
from dealdesk.ports.repositories import (
    AuditQuery,
    DuplicateEmailError,
    NotFoundError,
    RefreshTokenRecord,
    RunQuery,
    RunStatus,
    StepRecord,
)
from tests.integration.factories import make_run, make_user

pytestmark = pytest.mark.integration
NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
D = Decimal


# ---------------------------------------------------------------- users


def test_user_email_is_unique_case_insensitively(sessions: SessionFactory) -> None:
    users = SqlUserRepository(sessions)
    created = make_user(sessions, email="Alice@Test.example")
    assert users.get_by_email("alice@test.EXAMPLE") == created
    with pytest.raises(DuplicateEmailError):
        make_user(sessions, email="ALICE@test.example")


def test_user_update_and_listing(sessions: SessionFactory) -> None:
    users = SqlUserRepository(sessions)
    user = make_user(sessions)
    updated = users.update(
        user.id, role=UserRole.APPROVER, is_active=False, display_name="New", password_hash="h"
    )
    assert (updated.role, updated.is_active, updated.display_name, updated.password_hash) == (
        UserRole.APPROVER,
        False,
        "New",
        "h",
    )
    assert updated.updated_at >= user.updated_at
    assert [u.id for u in users.list_all()] == [user.id]
    assert users.get(uuid.uuid4()) is None
    with pytest.raises(NotFoundError):
        users.update(uuid.uuid4(), role=UserRole.ADMIN)


def test_login_failures_count_and_reset(sessions: SessionFactory) -> None:
    users = SqlUserRepository(sessions)
    user = make_user(sessions)
    users.record_login_failure(user.id, None)
    locked = users.record_login_failure(user.id, NOW)
    assert (locked.failed_login_count, locked.locked_until) == (2, NOW)
    users.reset_login_failures(user.id)
    fresh = users.get(user.id)
    assert fresh is not None
    assert (fresh.failed_login_count, fresh.locked_until) == (0, None)
    with pytest.raises(NotFoundError):
        users.record_login_failure(uuid.uuid4(), None)


def test_external_subject_lookup(sessions: SessionFactory) -> None:
    users = SqlUserRepository(sessions)
    created = users.create(
        email="oidc@test.example",
        display_name="OIDC",
        role=UserRole.VIEWER,
        password_hash=None,
        external_subject="sub-123",
    )
    assert users.get_by_subject("sub-123") == created
    assert users.get_by_subject("nobody") is None


# ---------------------------------------------------------------- refresh tokens


def _token(user_id: uuid.UUID, family: uuid.UUID, value: str) -> RefreshTokenRecord:
    return RefreshTokenRecord(
        id=uuid.uuid4(),
        family_id=family,
        user_id=user_id,
        token_hash=value,
        expires_at=NOW + timedelta(days=1),
        created_at=NOW,
    )


def test_refresh_token_rotation_is_single_use(sessions: SessionFactory) -> None:
    tokens = SqlRefreshTokenRepository(sessions)
    user = make_user(sessions)
    family = uuid.uuid4()
    first = _token(user.id, family, "a" * 64)
    tokens.add(first)
    second = _token(user.id, family, "b" * 64)
    assert tokens.rotate(first.id, second, NOW) is True
    assert tokens.rotate(first.id, _token(user.id, family, "c" * 64), NOW) is False
    stored = tokens.get_by_hash("a" * 64)
    assert stored is not None
    assert stored.replaced_by == second.id
    assert tokens.get_by_hash("c" * 64) is None
    assert tokens.revoke_family(family, NOW) == 1
    assert tokens.revoke_family(family, NOW) == 0


def test_revoke_one_and_all_for_user(sessions: SessionFactory) -> None:
    tokens = SqlRefreshTokenRepository(sessions)
    user = make_user(sessions)
    one, two = _token(user.id, uuid.uuid4(), "d" * 64), _token(user.id, uuid.uuid4(), "e" * 64)
    tokens.add(one)
    tokens.add(two)
    tokens.revoke(one.id, NOW)
    revoked = tokens.get_by_hash("d" * 64)
    assert revoked is not None
    assert revoked.revoked_at == NOW
    assert tokens.revoke_all_for_user(user.id, NOW) == 1


# ---------------------------------------------------------------- audit


def test_audit_log_appends_and_filters(sessions: SessionFactory) -> None:
    audit = SqlAuditLog(sessions)
    actor = uuid.uuid4()
    for i in range(3):
        audit.append(
            AuditEvent(
                "auth.login_failed" if i else "run.created",
                actor if i == 2 else None,
                "run",
                f"r{i}",
                NOW + timedelta(minutes=i),
                request_id=f"req-{i}",
                details={"i": str(i)},
            )
        )
    everything, total = audit.query(AuditQuery())
    assert total == 3
    assert [e.event.subject_id for e in everything] == ["r2", "r1", "r0"]
    assert audit.query(AuditQuery(action="auth.login_failed"))[1] == 2
    assert audit.query(AuditQuery(actor_id=actor))[1] == 1
    assert audit.query(AuditQuery(subject_id="r0"))[1] == 1
    since = audit.query(
        AuditQuery(since=NOW + timedelta(minutes=1), until=NOW + timedelta(minutes=2))
    )
    assert [e.event.subject_id for e in since[0]] == ["r1"]
    assert everything[0].event.details == {"i": "2"}
    page, _ = audit.query(AuditQuery(limit=1, offset=1))
    assert [e.event.subject_id for e in page] == ["r1"]


@pytest.mark.parametrize(
    "statement", ["UPDATE audit_events SET action = 'x'", "DELETE FROM audit_events"]
)
def test_audit_log_is_append_only_in_the_database(
    sessions: SessionFactory, engine: Engine, statement: str
) -> None:
    SqlAuditLog(sessions).append(AuditEvent("run.created", None, "run", "r", NOW))
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
        connection.execute(text(statement))


# ---------------------------------------------------------------- reference data


def test_reference_data_is_seeded(sessions: SessionFactory) -> None:
    reference = SqlReferenceData(sessions)
    card = reference.rate_card()
    assert len(card.entries) == 8
    assert card.rate_for("engineer").sell_rate == D("90.00")
    assert len(reference.team()) == 10


def test_similarity_search_ranks_the_closest_project_first(sessions: SessionFactory) -> None:
    reference = SqlReferenceData(sessions)
    query = FakeEmbedder().embed(["AI assistant to classify and summarise claim documents"])[0]
    projects = reference.similar_projects(query, k=3)
    assert projects[0].item.project_id == "PP-003"
    assert projects[0].item.actual_hours_by_role["ml_engineer"] == D(420)
    assert D(projects[0].similarity) >= D(projects[1].similarity)
    studies = reference.similar_case_studies(query, k=2)
    assert studies[0].item.case_study_id == "CS-003"


# ---------------------------------------------------------------- runs, steps, approvals


def test_run_lifecycle(sessions: SessionFactory) -> None:
    runs = SqlRunRepository(sessions)
    creator = make_user(sessions)
    run = make_run(sessions, creator)
    assert run.status is RunStatus.QUEUED
    assert runs.brief_text(run.id) == "SAMPLE brief"
    updated = runs.update(
        run.id, {"status": RunStatus.RUNNING, "flags": ["X"], "quote": {"p": "1"}}
    )
    assert (updated.status, updated.flags, updated.quote) == (RunStatus.RUNNING, ["X"], {"p": "1"})
    assert runs.ids_with_status(frozenset({RunStatus.RUNNING})) == [run.id]
    listed, total = runs.list_runs(RunQuery(status=RunStatus.RUNNING, created_by=creator.id))
    assert total == 1
    assert listed[0].id == run.id
    assert runs.list_runs(RunQuery(status=RunStatus.APPROVED))[1] == 0
    with pytest.raises(ValueError, match="created_by"):
        runs.update(run.id, {"created_by": uuid.uuid4()})
    with pytest.raises(NotFoundError):
        runs.update(uuid.uuid4(), {"status": RunStatus.FAILED})
    with pytest.raises(NotFoundError):
        runs.brief_text(uuid.uuid4())
    assert runs.get(uuid.uuid4()) is None


def test_steps_upsert_and_mean_durations(sessions: SessionFactory) -> None:
    runs = SqlRunRepository(sessions)
    run = make_run(sessions, make_user(sessions))
    runs.record_step(StepRecord(run.id, "intake", 1, "running", NOW))
    runs.record_step(
        StepRecord(run.id, "intake", 1, "completed", NOW, NOW, 1500, {"requirements": "8"})
    )
    runs.record_step(StepRecord(run.id, "intake", 2, "completed", NOW, NOW, 500))
    steps = runs.steps(run.id)
    assert [(s.attempt, s.status, s.duration_ms) for s in steps] == [
        (1, "completed", 1500),
        (2, "completed", 500),
    ]
    assert steps[0].detail == {"requirements": "8"}
    assert runs.mean_step_seconds() == {"intake": "1.000"}


def test_approval_is_stored_with_its_audit_event(sessions: SessionFactory) -> None:
    approvals = SqlApprovalRepository(sessions)
    creator, approver = make_user(sessions), make_user(sessions, UserRole.APPROVER)
    run = make_run(sessions, creator)
    approval = Approval(run.id, approver.id, Decision.APPROVED, "Looks right", NOW)
    approvals.add(approval, AuditEvent("run.approved", approver.id, "run", str(run.id), NOW))
    assert approvals.for_run(run.id) == [approval]
    assert SqlAuditLog(sessions).query(AuditQuery(action="run.approved"))[1] == 1


def test_documents_round_trip(sessions: SessionFactory) -> None:
    store = SqlDocumentStore(sessions)
    doc_id = store.put(kind="proposal", filename="p.docx", content_type="x/y", content=b"\x00\x01")
    stored = store.get(doc_id)
    assert stored is not None
    assert (stored.content, len(stored.sha256)) == (b"\x00\x01", 64)
    assert store.get(uuid.uuid4()) is None


# ---------------------------------------------------------------- downstream mocks


def test_crm_and_accounting_mocks_are_idempotent(sessions: SessionFactory) -> None:
    creator, approver = make_user(sessions), make_user(sessions, UserRole.APPROVER)
    run = make_run(sessions, creator)
    crm, accounting = MockCRM(sessions), MockAccounting(sessions)
    record = PipelineRecord(run.id, "Sample", D("12760.00"), D("0.4914"), "won", approver.id, NOW)
    first = crm.upsert_pipeline_record(record)
    assert crm.upsert_pipeline_record(record) == first
    assert first.startswith("OPP-SAMPLE-")
    assert crm.get_pipeline_record(run.id) == record
    assert crm.get_pipeline_record(uuid.uuid4()) is None

    schedule = build_invoice_schedule(
        D("12760.00"), date(2026, 2, 2), InvoicePolicy((D(30), D(40), D(30)), (0, 42, 84), D("0.2"))
    )
    accounting.upsert_invoice_schedule(run.id, schedule)
    accounting.upsert_invoice_schedule(run.id, schedule)
    assert accounting.get_invoice_schedule(run.id) == schedule
    assert accounting.get_invoice_schedule(uuid.uuid4()) is None
