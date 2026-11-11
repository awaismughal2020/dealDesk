"""End-to-end workflow tests: real Postgres, real LangGraph checkpointer, FakeLLM."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from dealdesk.adapters.accounting_mock import MockAccounting
from dealdesk.adapters.crm_mock import MockCRM
from dealdesk.adapters.db.audit import SqlAuditLog
from dealdesk.adapters.db.checkpointer import open_checkpointer
from dealdesk.adapters.db.reference import SqlReferenceData
from dealdesk.adapters.db.runs import SqlApprovalRepository, SqlDocumentStore, SqlRunRepository
from dealdesk.adapters.db.session import SessionFactory
from dealdesk.adapters.db.users import SqlUserRepository
from dealdesk.adapters.embeddings.fake import FakeEmbedder
from dealdesk.adapters.llm.base import StructuredLLM
from dealdesk.adapters.llm.fake import FakeModelClient
from dealdesk.application.pipeline import DealPipeline
from dealdesk.application.runner import WorkflowRunner, thread_config
from dealdesk.application.runs import (
    Actor,
    BriefUpload,
    CommentRequiredError,
    ForbiddenActionError,
    InvalidRunStateError,
    RunService,
)
from dealdesk.application.workflow import ModelPricing, WorkflowDeps, WorkflowNodes, build_graph
from dealdesk.config import Settings
from dealdesk.domain.errors import SeparationOfDutiesError
from dealdesk.domain.models import Decision, Flag, UserRole
from dealdesk.ports.documents import ProposalDocument
from dealdesk.ports.repositories import AuditQuery, RunRecord, RunStatus
from tests.integration.factories import make_user

pytestmark = pytest.mark.integration
SAMPLES = Path(__file__).resolve().parents[2] / "data" / "samples"


class InlineExecutor:
    def submit(self, fn: Callable[[], None], /) -> None:
        fn()


class RecordingRenderer:
    content_type = "application/test"

    def __init__(self, fail_times: int = 0) -> None:
        self.documents: list[ProposalDocument] = []
        self.fail_times = fail_times

    def render(self, document: ProposalDocument) -> bytes:
        if self.fail_times:
            self.fail_times -= 1
            raise RuntimeError("simulated crash while rendering")
        self.documents.append(document)
        return f"{document.title}|final={document.is_final}".encode()


@dataclass
class Stack:
    sessions: SessionFactory
    runs: SqlRunRepository
    service: RunService
    runner: WorkflowRunner
    graph: Any
    renderer: RecordingRenderer
    audit: SqlAuditLog
    nodes: WorkflowNodes

    def upload(self, actor: Actor, sample: str = "clean_brief") -> RunRecord:
        text = (SAMPLES / f"{sample}.txt").read_text(encoding="utf-8")
        upload = BriefUpload(f"{sample}.txt", "text/plain", text.encode(), text, sample)
        return self.service.create(actor, upload, request_id="req-test")

    def run(self, run_id: UUID) -> RunRecord:
        record = self.runs.get(run_id)
        assert record is not None
        return record

    def llm_calls(self, run_id: UUID, prompt_id: str) -> int:
        events, _ = self.audit.query(
            AuditQuery(action="llm.call", subject_id=str(run_id), limit=500)
        )
        return sum(1 for e in events if e.event.details["prompt_id"] == prompt_id)


@pytest.fixture
def make_stack(sessions: SessionFactory, database_url: str) -> Iterator[Callable[..., Stack]]:
    pools = []

    def build(renderer: RecordingRenderer | None = None, max_revisions: int = 2) -> Stack:
        settings = Settings(cookie_secure=False, max_revisions=max_revisions)
        saver, pool = open_checkpointer(database_url, max_size=2)
        saver.setup()
        pools.append(pool)
        runs, approvals = SqlRunRepository(sessions), SqlApprovalRepository(sessions)
        audit, reference = SqlAuditLog(sessions), SqlReferenceData(sessions)
        renderer = renderer or RecordingRenderer()
        pipeline = DealPipeline(
            llm=StructuredLLM(FakeModelClient(), max_retries=0),
            embedder=FakeEmbedder(),
            reference=reference,
            policy=settings.costing_policy,
            top_k=3,
            max_revisions=max_revisions,
        )
        deps = WorkflowDeps(
            pipeline=pipeline,
            runs=runs,
            users=SqlUserRepository(sessions),
            reference=reference,
            audit=audit,
            approvals=approvals,
            documents=SqlDocumentStore(sessions),
            renderer=renderer,
            crm=MockCRM(sessions),
            accounting=MockAccounting(sessions),
            invoice_policy=settings.invoice_policy,
            weeks=12,
            pricing=ModelPricing(settings.llm_input_gbp_per_mtok, settings.llm_output_gbp_per_mtok),
            clock=lambda: datetime.now(UTC),
            timer=time.monotonic,
        )
        graph = build_graph(deps, saver)
        runner = WorkflowRunner(
            graph=graph,
            runs=runs,
            approvals=approvals,
            audit=audit,
            executor=InlineExecutor(),
            clock=lambda: datetime.now(UTC),
        )
        service = RunService(
            runs=runs,
            approvals=approvals,
            documents=SqlDocumentStore(sessions),
            audit=audit,
            runner=runner,
            clock=lambda: datetime.now(UTC),
            start_lead_days=14,
        )
        return Stack(sessions, runs, service, runner, graph, renderer, audit, WorkflowNodes(deps))

    yield build
    for pool in pools:
        pool.close()


def actors(sessions: SessionFactory) -> tuple[Actor, Actor]:
    estimator = make_user(sessions, UserRole.ESTIMATOR)
    approver = make_user(sessions, UserRole.APPROVER)
    return Actor(estimator.id, estimator.role), Actor(approver.id, approver.role)


def test_brief_to_approval_to_records(
    make_stack: Callable[..., Stack], sessions: SessionFactory
) -> None:
    stack = make_stack()
    estimator, approver = actors(sessions)
    run = stack.upload(estimator)
    paused = stack.run(run.id)
    assert paused.status is RunStatus.AWAITING_APPROVAL
    assert paused.quote is not None and paused.quote["price"] == "137830.00"
    assert paused.title == "Tenant self-service portal"
    assert {"BELOW_TARGET_MARGIN", "RESOURCE_CLASH"} <= set(paused.flags)
    assert paused.is_final is False
    assert stack.renderer.documents[-1].is_final is False
    assert MockCRM(sessions).get_pipeline_record(run.id) is None  # nothing before approval

    approved = stack.service.decide(approver, run.id, Decision.APPROVED, "Within policy", "req-2")
    assert approved.status is RunStatus.APPROVED
    assert approved.is_final is True
    record = MockCRM(sessions).get_pipeline_record(run.id)
    assert record is not None and str(record.value) == "137830.00"
    schedule = MockAccounting(sessions).get_invoice_schedule(run.id)
    assert schedule is not None and str(schedule.net_total) == "137830.00"
    final = stack.renderer.documents[-1]
    assert final.is_final and final.approved_at is not None

    steps = [s.step for s in stack.runs.steps(run.id)]
    assert steps == ["intake", "estimate", "cost", "resource_check", "draft_proposal", "finalize"]
    calls, _ = stack.audit.query(AuditQuery(action="llm.call", subject_id=str(run.id)))
    assert {e.event.details["prompt_version"] for e in calls} == {"1.1.0"}
    assert {"model", "input_tokens", "output_tokens", "latency_ms", "estimated_cost_gbp"} <= set(
        calls[0].event.details
    )
    approvals, _ = stack.audit.query(AuditQuery(action="run.approved"))
    assert approvals[0].event.actor_id == approver.id
    assert approvals[0].event.request_id == "req-2"


def test_separation_of_duties_and_role_rechecks(
    make_stack: Callable[..., Stack], sessions: SessionFactory
) -> None:
    stack = make_stack()
    estimator, approver = actors(sessions)
    run = stack.upload(estimator)
    promoted = Actor(estimator.id, UserRole.APPROVER)  # creator later promoted to approver
    with pytest.raises(SeparationOfDutiesError):
        stack.service.decide(promoted, run.id, Decision.APPROVED, "mine", None)
    with pytest.raises(ForbiddenActionError):
        stack.service.decide(estimator, run.id, Decision.APPROVED, "", None)
    with pytest.raises(ForbiddenActionError):
        stack.upload(approver)
    assert stack.run(run.id).status is RunStatus.AWAITING_APPROVAL


def test_rejection_requires_comment_and_returns_to_drafting(
    make_stack: Callable[..., Stack], sessions: SessionFactory
) -> None:
    stack = make_stack()
    estimator, approver = actors(sessions)
    run = stack.upload(estimator)
    with pytest.raises(CommentRequiredError):
        stack.service.decide(approver, run.id, Decision.REJECTED, "   ", None)
    stack.service.decide(approver, run.id, Decision.REJECTED, "Stress accessibility testing", None)
    redrafted = stack.run(run.id)
    assert redrafted.status is RunStatus.AWAITING_APPROVAL
    assert redrafted.review_comment == "Stress accessibility testing"
    assert redrafted.proposal is not None
    assert "Stress accessibility testing" in redrafted.proposal["sections"]["executive_summary"]
    drafts = [s for s in stack.runs.steps(run.id) if s.step == "draft_proposal"]
    assert [s.attempt for s in drafts] == [1, 2]
    stack.service.decide(approver, run.id, Decision.APPROVED, "ok", None)
    with pytest.raises(InvalidRunStateError):
        stack.service.decide(approver, run.id, Decision.APPROVED, "again", None)


def test_ambiguous_brief_goes_through_revision(
    make_stack: Callable[..., Stack], sessions: SessionFactory
) -> None:
    stack = make_stack()
    estimator, _ = actors(sessions)
    run = stack.run(stack.upload(estimator, "ambiguous_brief").id)
    assert run.revision_count == 1
    assert [s.step for s in stack.runs.steps(run.id)].count("cost") == 2
    assert Flag.BELOW_MINIMUM_MARGIN.value not in run.flags


def test_escalates_with_flags_when_revisions_are_exhausted(
    make_stack: Callable[..., Stack], sessions: SessionFactory
) -> None:
    stack = make_stack(max_revisions=0)
    estimator, _ = actors(sessions)
    run = stack.run(stack.upload(estimator, "ambiguous_brief").id)
    assert run.status is RunStatus.AWAITING_APPROVAL
    assert {"BELOW_MINIMUM_MARGIN", "REVISION_LIMIT_REACHED"} <= set(run.flags)


def test_restart_mid_run_resumes_from_checkpoint(
    make_stack: Callable[..., Stack], sessions: SessionFactory
) -> None:
    crashing = make_stack(RecordingRenderer(fail_times=1))
    estimator, _ = actors(sessions)
    run = crashing.runs.create(
        run_id=uuid.uuid4(),
        title="crash test",
        created_by=estimator.id,
        brief_document_id=SqlDocumentStore(sessions).put(
            kind="brief", filename="b.txt", content_type="text/plain", content=b"x"
        ),
        brief_filename="b.txt",
        brief_text=(SAMPLES / "clean_brief.txt").read_text(),
        start_date=datetime(2026, 1, 5, tzinfo=UTC).date(),
    )
    with pytest.raises(
        RuntimeError, match="simulated crash"
    ):  # the process "dies" in draft_proposal
        crashing.graph.invoke({"run_id": str(run.id), "revisions": 0}, thread_config(run.id))
    assert crashing.run(run.id).status is RunStatus.RUNNING

    restarted = make_stack()  # a new process: new pool, new graph, same database
    assert restarted.runner.recover() == [run.id]
    resumed = restarted.run(run.id)
    assert resumed.status is RunStatus.AWAITING_APPROVAL
    assert (
        restarted.llm_calls(run.id, "extract_requirements") == 1
    )  # completed steps did not re-run
    statuses = [
        (s.step, s.status) for s in restarted.runs.steps(run.id) if s.step == "draft_proposal"
    ]
    assert statuses == [("draft_proposal", "completed")]


def test_recover_applies_a_decision_recorded_before_a_crash(
    make_stack: Callable[..., Stack], sessions: SessionFactory
) -> None:
    stack = make_stack()
    estimator, approver = actors(sessions)
    run = stack.upload(estimator)

    class DropExecutor:
        def submit(self, fn: Callable[[], None], /) -> None:  # the resume is lost in a crash
            return None

    stack.runner._executor = DropExecutor()
    stack.service.decide(approver, run.id, Decision.APPROVED, "ok", None)
    assert stack.run(run.id).status is RunStatus.RUNNING
    stack.runner._executor = InlineExecutor()
    assert stack.runner.recover() == [run.id]
    assert stack.run(run.id).status is RunStatus.APPROVED


def test_failures_mark_the_run_failed(
    make_stack: Callable[..., Stack], sessions: SessionFactory
) -> None:
    stack = make_stack(RecordingRenderer(fail_times=5))
    estimator, _ = actors(sessions)
    run = stack.run(stack.upload(estimator).id)
    assert run.status is RunStatus.FAILED
    assert run.error is not None and "simulated crash" in run.error
    failed, _ = stack.audit.query(AuditQuery(action="run.failed", subject_id=str(run.id)))
    assert len(failed) == 1


def test_finalize_refuses_without_recorded_approval(
    make_stack: Callable[..., Stack], sessions: SessionFactory
) -> None:
    from dealdesk.application.workflow import ApprovalMissingError

    stack = make_stack()
    estimator, _ = actors(sessions)
    run = stack.upload(estimator)
    with pytest.raises(ApprovalMissingError):
        stack.nodes.finalize({"run_id": str(run.id)})
    assert MockCRM(sessions).get_pipeline_record(run.id) is None
