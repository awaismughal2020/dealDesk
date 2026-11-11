"""The bid workflow as a LangGraph state graph with a Postgres checkpointer.

    intake -> estimate -> cost --(below minimum margin, max 2)--> revise -> cost
                          cost --(otherwise)--> resource_check -> draft_proposal -> await_approval
    await_approval --(approved)--> finalize
    await_approval --(rejected, with comment)--> draft_proposal

Graph state holds only small primitives. Step outputs are written to the run record, so the API
reads them without touching checkpoints. Every node is safe to re-run: outputs are overwritten,
downstream writes are idempotent upserts, and `finalize` refuses to run without a recorded
approval.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, TypedDict
from uuid import UUID

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from dealdesk.application.pipeline import DealPipeline, EstimateRejectedError, ModelCall
from dealdesk.application.proposal import build_proposal_document
from dealdesk.application.serialization import (
    draft_sections,
    draft_to_json,
    extraction_from_json,
    extraction_to_json,
    plan_to_json,
    proposal_from_json,
    proposal_to_json,
    quote_from_json,
    quote_to_json,
    references_from_json,
    references_to_json,
)
from dealdesk.domain.invoicing import build_invoice_schedule
from dealdesk.domain.models import (
    AuditEvent,
    Decision,
    Flag,
    InvoicePolicy,
    PipelineRecord,
    RateCard,
)
from dealdesk.ports.documents import ProposalRendererPort
from dealdesk.ports.repositories import (
    AccountingPort,
    ApprovalRepository,
    AuditLog,
    CRMPort,
    DocumentStorePort,
    ReferenceData,
    RunRecord,
    RunRepository,
    RunStatus,
    StepRecord,
    UserRepository,
)

MILLION = Decimal(1_000_000)
MS_PER_SECOND = 1000
PIPELINE_STAGE = "won (SAMPLE)"


class Step:
    """Node names."""

    INTAKE = "intake"
    ESTIMATE = "estimate"
    COST = "cost"
    REVISE = "revise"
    RESOURCE_CHECK = "resource_check"
    DRAFT_PROPOSAL = "draft_proposal"
    AWAIT_APPROVAL = "await_approval"
    FINALIZE = "finalize"


class RunState(TypedDict, total=False):
    """Checkpointed graph state. Deliberately small and JSON-friendly."""

    run_id: str
    request_id: str | None
    revisions: int
    decision: str | None
    reviewer_comment: str | None


@dataclass(frozen=True, slots=True)
class _Attempt:
    run_id: UUID
    step: str
    number: int
    started_at: datetime
    started: float


class ApprovalMissingError(Exception):
    """`finalize` was reached without a recorded approval (defence in depth)."""


class EstimateEscalationError(Exception):
    """The model could not produce a valid estimate; a human must take over."""


@dataclass(frozen=True, slots=True)
class ModelPricing:
    """Assumed GBP per million tokens, used only for the audit log's spend estimate."""

    input_gbp_per_mtok: Decimal
    output_gbp_per_mtok: Decimal

    def cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        """Estimated spend for one call, in GBP to 6 dp."""
        spend = (
            Decimal(input_tokens) * self.input_gbp_per_mtok
            + Decimal(output_tokens) * self.output_gbp_per_mtok
        ) / MILLION
        return spend.quantize(Decimal("0.000001"))


@dataclass(frozen=True, slots=True)
class WorkflowDeps:
    """Everything the nodes need, injected through ports."""

    pipeline: DealPipeline
    runs: RunRepository
    users: UserRepository
    reference: ReferenceData
    audit: AuditLog
    approvals: ApprovalRepository
    documents: DocumentStorePort
    renderer: ProposalRendererPort
    crm: CRMPort
    accounting: AccountingPort
    invoice_policy: InvoicePolicy
    weeks: int
    pricing: ModelPricing
    clock: Callable[[], datetime]
    timer: Callable[[], float]


def collect_flags(run: RunRecord) -> list[str]:
    """Union of the flags raised by every stored step output."""
    flags: set[str] = set()
    for part in (run.requirements, run.quote, run.resource_plan, run.proposal):
        if part:
            flags.update(part.get("flags", []))
    return sorted(flags)


class WorkflowNodes:
    """Node implementations. Each one records timing, model usage and an audit event."""

    def __init__(self, deps: WorkflowDeps) -> None:
        self._d = deps

    # ------------------------------------------------------------ nodes

    def intake(self, state: RunState) -> RunState:
        """Extract and screen requirements from the untrusted brief."""

        def work(run: RunRecord) -> dict[str, Any]:
            extraction = self._d.pipeline.extract(self._d.runs.brief_text(run.id))
            changes = {"requirements": extraction_to_json(extraction), "title": extraction.title}
            self._save(run.id, changes, extraction.calls, state)
            return {
                "requirements": str(len(extraction.requirements)),
                "quarantined": str(len(extraction.quarantined)),
            }

        self._step(Step.INTAKE, state, work)
        return {}

    def estimate(self, state: RunState) -> RunState:
        """Retrieve similar SAMPLE projects and ask the model for hours by role."""

        def work(run: RunRecord) -> dict[str, Any]:
            extraction = extraction_from_json(_require(run.requirements))
            references = self._d.pipeline.retrieve(extraction)
            try:
                proposal = self._d.pipeline.propose_estimate(
                    extraction, references, self._d.reference.rate_card()
                )
            except EstimateRejectedError as error:
                raise EstimateEscalationError(str(error)) from error
            changes = {
                "references": references_to_json(references),
                "estimate": proposal_to_json(proposal),
            }
            self._save(run.id, changes, proposal.calls, state)
            return {"total_hours": str(proposal.estimate.total_hours)}

        self._step(Step.ESTIMATE, state, work)
        return {}

    def cost(self, state: RunState) -> RunState:
        """Price the estimate in code and apply the margin policy."""

        def work(run: RunRecord) -> dict[str, Any]:
            quote = self._d.pipeline.price(
                proposal_from_json(_require(run.estimate)), self._rates()
            )
            data = quote_to_json(quote)
            revisions = state.get("revisions", 0)
            if Flag.BELOW_MINIMUM_MARGIN in quote.flags and not self._d.pipeline.needs_revision(
                quote, revisions
            ):
                data["flags"] = sorted({*data["flags"], Flag.REVISION_LIMIT_REACHED.value})
            self._save(run.id, {"quote": data, "revision_count": revisions}, (), state)
            return {"price": data["price"], "margin": data["margin"]}

        self._step(Step.COST, state, work)
        return {}

    def revise(self, state: RunState) -> RunState:
        """Ask the model to rebalance hours or scope (never rates)."""

        def work(run: RunRecord) -> dict[str, Any]:
            proposal = self._d.pipeline.revise_for_margin(
                proposal_from_json(_require(run.estimate)),
                quote_from_json(_require(run.quote)),
                self._rates(),
            )
            self._save(run.id, {"estimate": proposal_to_json(proposal)}, proposal.calls, state)
            return {"total_hours": str(proposal.estimate.total_hours)}

        self._step(Step.REVISE, state, work)
        return {"revisions": state.get("revisions", 0) + 1}

    def resource_check(self, state: RunState) -> RunState:
        """Spread the hours over the weeks and check people's availability."""

        def work(run: RunRecord) -> dict[str, Any]:
            team = self._d.reference.team()
            plan = self._d.pipeline.plan(
                quote_from_json(_require(run.quote)), team, run.start_date, self._d.weeks
            )
            self._save(run.id, {"resource_plan": plan_to_json(plan, team)}, (), state)
            return {"clashes": str(len(plan.clashes))}

        self._step(Step.RESOURCE_CHECK, state, work)
        return {}

    def draft_proposal(self, state: RunState) -> RunState:
        """Draft prose, check citations and figures, render the DRAFT document."""

        def work(run: RunRecord) -> dict[str, Any]:
            extraction = extraction_from_json(_require(run.requirements))
            references = references_from_json(_require(run.references))
            quote = quote_from_json(_require(run.quote))
            draft = self._d.pipeline.draft(
                extraction,
                references,
                quote,
                weeks=self._d.weeks,
                reviewer_comment=state.get("reviewer_comment"),
            )
            schedule = build_invoice_schedule(quote.price, run.start_date, self._d.invoice_policy)
            proposal_json = draft_to_json(draft, schedule)
            document = build_proposal_document(
                run,
                extraction=extraction,
                references=references,
                quote=quote,
                schedule=schedule,
                sections=draft.output,
                flags=collect_flags(run) + proposal_json["flags"],
                weeks=self._d.weeks,
                generated_at=self._d.clock(),
            )
            document_id = self._d.documents.put(
                kind="proposal_draft",
                filename=f"proposal-{run.id.hex[:8]}-DRAFT.docx",
                content_type=self._d.renderer.content_type,
                content=self._d.renderer.render(document),
            )
            changes = {
                "proposal": proposal_json,
                "proposal_document_id": document_id,
                "is_final": False,
                "review_comment": state.get("reviewer_comment"),
            }
            self._save(run.id, changes, draft.calls, state)
            return {"flags": ",".join(proposal_json["flags"])}

        self._step(Step.DRAFT_PROPOSAL, state, work)
        self._d.runs.update(
            UUID(state["run_id"]),
            {"status": RunStatus.AWAITING_APPROVAL, "current_step": Step.AWAIT_APPROVAL},
        )
        return {}

    @staticmethod
    def await_approval(state: RunState) -> RunState:
        """Pause until a human decides. The decision itself is validated by `ApprovalService`."""
        decision: Mapping[str, str] = interrupt({"run_id": state["run_id"], "awaiting": "approval"})
        return {
            "decision": decision["decision"],
            "reviewer_comment": decision.get("comment") or None,
        }

    def finalize(self, state: RunState) -> RunState:
        """Create the pipeline record and invoice schedule, and mark the proposal final."""

        def work(run: RunRecord) -> dict[str, Any]:
            decisions = self._d.approvals.for_run(run.id)
            if not decisions or decisions[-1].decision is not Decision.APPROVED:
                raise ApprovalMissingError(f"run {run.id} has no recorded approval")
            approval = decisions[-1]
            approver = self._d.users.get(approval.decided_by)
            quote = quote_from_json(_require(run.quote))
            reference = self._d.crm.upsert_pipeline_record(
                PipelineRecord(
                    run_id=run.id,
                    title=run.title,
                    value=quote.price,
                    margin=quote.margin,
                    stage=PIPELINE_STAGE,
                    approved_by=approval.decided_by,
                    approved_at=approval.decided_at,
                )
            )
            schedule = build_invoice_schedule(quote.price, run.start_date, self._d.invoice_policy)
            self._d.accounting.upsert_invoice_schedule(run.id, schedule)
            document = build_proposal_document(
                run,
                extraction=extraction_from_json(_require(run.requirements)),
                references=references_from_json(_require(run.references)),
                quote=quote,
                schedule=schedule,
                sections=draft_sections(_require(run.proposal)),
                flags=collect_flags(run),
                weeks=self._d.weeks,
                generated_at=self._d.clock(),
                approved_by=approver.display_name if approver else str(approval.decided_by),
                approved_at=approval.decided_at,
            )
            document_id = self._d.documents.put(
                kind="proposal_final",
                filename=f"proposal-{run.id.hex[:8]}-FINAL.docx",
                content_type=self._d.renderer.content_type,
                content=self._d.renderer.render(document),
            )
            self._save(
                run.id,
                {
                    "proposal_document_id": document_id,
                    "is_final": True,
                    "status": RunStatus.APPROVED,
                },
                (),
                state,
            )
            return {"pipeline_reference": reference, "milestones": str(len(schedule.milestones))}

        self._step(Step.FINALIZE, state, work)
        return {}

    # ------------------------------------------------------------ routing

    def after_cost(self, state: RunState) -> Literal["revise", "resource_check"]:
        """Revise while below minimum margin and the budget allows, else continue."""
        run = self._d.runs.get(UUID(state["run_id"]))
        quote = quote_from_json(_require(run.quote if run else None))
        if self._d.pipeline.needs_revision(quote, state.get("revisions", 0)):
            return "revise"
        return "resource_check"

    @staticmethod
    def after_decision(state: RunState) -> Literal["finalize", "draft_proposal"]:
        """Approved goes to finalize; rejected goes back to drafting with the comment."""
        return "finalize" if state.get("decision") == Decision.APPROVED.value else "draft_proposal"

    # ------------------------------------------------------------ helpers

    def _rates(self) -> RateCard:
        return self._d.reference.rate_card()

    def _step(
        self, name: str, state: RunState, work: Callable[[RunRecord], dict[str, Any]]
    ) -> None:
        run_id = UUID(state["run_id"])
        run = self._d.runs.get(run_id)
        if run is None:
            raise LookupError(f"run {run_id} not found")
        attempt = _Attempt(
            run_id=run_id,
            step=name,
            number=1
            + sum(
                1 for s in self._d.runs.steps(run_id) if s.step == name and s.status == "completed"
            ),
            started_at=self._d.clock(),
            started=self._d.timer(),
        )
        self._d.runs.record_step(
            StepRecord(run_id, name, attempt.number, "running", attempt.started_at)
        )
        if run.status is not RunStatus.RUNNING or run.current_step != name:
            run = self._d.runs.update(run_id, {"status": RunStatus.RUNNING, "current_step": name})
        try:
            detail = work(run)
        except Exception as exc:
            self._finish(attempt, "failed", {"error": type(exc).__name__}, state)
            raise
        self._finish(attempt, "completed", detail, state)

    def _finish(
        self, attempt: _Attempt, status: str, detail: dict[str, Any], state: RunState
    ) -> None:
        duration_ms = int((self._d.timer() - attempt.started) * MS_PER_SECOND)
        self._d.runs.record_step(
            StepRecord(
                attempt.run_id,
                attempt.step,
                attempt.number,
                status,
                attempt.started_at,
                self._d.clock(),
                duration_ms,
                detail,
            )
        )
        self._d.audit.append(
            AuditEvent(
                action=f"step.{status}",
                actor_id=None,
                subject_type="run",
                subject_id=str(attempt.run_id),
                occurred_at=self._d.clock(),
                request_id=state.get("request_id"),
                details={
                    "step": attempt.step,
                    "attempt": str(attempt.number),
                    "duration_ms": str(duration_ms),
                },
            )
        )

    def _save(
        self, run_id: UUID, changes: dict[str, Any], calls: tuple[ModelCall, ...], state: RunState
    ) -> None:
        run = self._d.runs.update(run_id, changes)
        self._d.runs.update(run_id, {"flags": collect_flags(run)})
        for call in calls:
            usage = call.usage
            self._d.audit.append(
                AuditEvent(
                    action="llm.call",
                    actor_id=None,
                    subject_type="run",
                    subject_id=str(run_id),
                    occurred_at=self._d.clock(),
                    request_id=state.get("request_id"),
                    details={
                        "prompt_id": call.prompt_id,
                        "prompt_version": call.prompt_version,
                        "provider": usage.provider,
                        "model": usage.model,
                        "input_tokens": str(usage.input_tokens),
                        "output_tokens": str(usage.output_tokens),
                        "latency_ms": str(usage.latency_ms),
                        "attempts": str(usage.attempts),
                        "estimated_cost_gbp": str(
                            self._d.pricing.cost(usage.input_tokens, usage.output_tokens)
                        ),
                    },
                )
            )


def _require[T](value: T | None) -> T:
    if value is None:
        raise LookupError("a previous step's output is missing")
    return value


def build_graph(
    deps: WorkflowDeps, checkpointer: BaseCheckpointSaver[Any]
) -> CompiledStateGraph[RunState, None, RunState, RunState]:
    """Assemble and compile the workflow with a durable checkpointer."""
    nodes = WorkflowNodes(deps)
    graph = StateGraph(RunState)
    graph.add_node(Step.INTAKE, nodes.intake)
    graph.add_node(Step.ESTIMATE, nodes.estimate)
    graph.add_node(Step.COST, nodes.cost)
    graph.add_node(Step.REVISE, nodes.revise)
    graph.add_node(Step.RESOURCE_CHECK, nodes.resource_check)
    graph.add_node(Step.DRAFT_PROPOSAL, nodes.draft_proposal)
    graph.add_node(Step.AWAIT_APPROVAL, nodes.await_approval)
    graph.add_node(Step.FINALIZE, nodes.finalize)
    graph.add_edge(START, Step.INTAKE)
    graph.add_edge(Step.INTAKE, Step.ESTIMATE)
    graph.add_edge(Step.ESTIMATE, Step.COST)
    graph.add_conditional_edges(Step.COST, nodes.after_cost)
    graph.add_edge(Step.REVISE, Step.COST)
    graph.add_edge(Step.RESOURCE_CHECK, Step.DRAFT_PROPOSAL)
    graph.add_edge(Step.DRAFT_PROPOSAL, Step.AWAIT_APPROVAL)
    graph.add_conditional_edges(Step.AWAIT_APPROVAL, nodes.after_decision)
    graph.add_edge(Step.FINALIZE, END)
    return graph.compile(checkpointer=checkpointer)
