"""Bid pipeline use cases. The model extracts, proposes hours and drafts prose; code does the rest.

Each method is a single, idempotent step over ports. The LangGraph workflow calls these methods
from its nodes, and the evals call them directly, so both exercise the same logic.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from dealdesk.application.guardrails import (
    data_block,
    injection_lines,
    prepare_brief,
    screen_requirements,
    states_figures,
    uncited_claims,
)
from dealdesk.application.prompts import load_prompt
from dealdesk.application.schemas import (
    EstimateOutput,
    ExtractedRequirement,
    ExtractionOutput,
    ProposalDraftOutput,
)
from dealdesk.domain.costing import needs_revision, price_estimate, validate_estimate
from dealdesk.domain.errors import EstimateIssue, EstimateValidationError
from dealdesk.domain.models import (
    CaseStudy,
    CostingPolicy,
    Estimate,
    Flag,
    PastProject,
    Quote,
    RateCard,
    ResourcePlan,
    TeamMember,
)
from dealdesk.domain.resourcing import plan_resources
from dealdesk.ports.embedder import EmbedderPort
from dealdesk.ports.llm import LLMPort, LLMUsage
from dealdesk.ports.repositories import ReferenceData, Scored


@dataclass(frozen=True, slots=True)
class ModelCall:
    """Accounting for one model call, for the audit log."""

    prompt_id: str
    prompt_version: str
    usage: LLMUsage


@dataclass(frozen=True, slots=True)
class Extraction:
    """Requirements after screening. Quarantined items never reach later prompts."""

    title: str
    summary: str
    requirements: tuple[ExtractedRequirement, ...]
    quarantined: tuple[ExtractedRequirement, ...]
    ambiguities: tuple[str, ...]
    flags: frozenset[Flag]
    calls: tuple[ModelCall, ...]


@dataclass(frozen=True, slots=True)
class References:
    """Retrieved SAMPLE past projects (for estimating) and case studies (for citing)."""

    projects: tuple[Scored[PastProject], ...]
    case_studies: tuple[Scored[CaseStudy], ...]


@dataclass(frozen=True, slots=True)
class EstimateProposal:
    """A model-proposed estimate that passed domain validation."""

    estimate: Estimate
    output: EstimateOutput
    calls: tuple[ModelCall, ...]


@dataclass(frozen=True, slots=True)
class Draft:
    """Proposal prose plus flags raised by checking it."""

    output: ProposalDraftOutput
    flags: frozenset[Flag]
    uncited_claim_indexes: tuple[int, ...]
    calls: tuple[ModelCall, ...]


@dataclass(frozen=True, slots=True)
class QuoteOutcome:
    """Everything computed from a brief up to an accepted (or escalated) quote."""

    extraction: Extraction
    references: References
    proposal: EstimateProposal
    quote: Quote
    revisions: int
    flags: frozenset[Flag]
    calls: tuple[ModelCall, ...] = field(default=())


class EstimateRejectedError(Exception):
    """The model could not produce a valid estimate within the revision budget."""

    def __init__(self, issues: tuple[EstimateIssue, ...]) -> None:
        super().__init__("; ".join(issue.message for issue in issues))
        self.issues = issues


def margin_ranking(roles: Sequence[str], rate_card: RateCard) -> list[str]:
    """Roles ordered from lowest to highest unit margin. Computed by code; only names are shared."""

    def unit_margin(role: str) -> tuple[Decimal, str]:
        rates = rate_card.rate_for(role)
        return (rates.sell_rate - rates.cost_rate) / rates.sell_rate, role

    return sorted((r for r in roles if rate_card.has(r)), key=unit_margin)


def _to_estimate(output: EstimateOutput) -> Estimate:
    hours: dict[str, Decimal] = {}
    for item in output.roles:
        hours[item.role] = hours.get(item.role, Decimal(0)) + item.hours_decimal
    return Estimate(hours, output.rationale)


class DealPipeline:
    """Use cases over the model, embedder and reference-data ports."""

    def __init__(
        self,
        *,
        llm: LLMPort,
        embedder: EmbedderPort,
        reference: ReferenceData,
        policy: CostingPolicy,
        top_k: int,
        max_revisions: int,
    ) -> None:
        self._llm = llm
        self._embedder = embedder
        self._reference = reference
        self._policy = policy
        self._top_k = top_k
        self._max_revisions = max_revisions

    # ------------------------------------------------------------ steps

    def extract(self, brief_text: str) -> Extraction:
        """Extract requirements, then quarantine anything that looks like an injection."""
        brief = prepare_brief(brief_text)
        prompt = load_prompt("extract_requirements").render(brief=brief)
        result = self._llm.generate(prompt, ExtractionOutput)
        screened = screen_requirements(result.output.requirements)
        suspicious = bool(screened.quarantined or injection_lines(brief))
        return Extraction(
            title=result.output.title,
            summary=result.output.summary,
            requirements=screened.kept,
            quarantined=screened.quarantined,
            ambiguities=tuple(result.output.ambiguities),
            flags=frozenset({Flag.POSSIBLE_PROMPT_INJECTION}) if suspicious else frozenset(),
            calls=(ModelCall(prompt.prompt_id, prompt.version, result.usage),),
        )

    def retrieve(self, extraction: Extraction) -> References:
        """Find similar SAMPLE projects and case studies from the screened requirements only."""
        query = extraction.title + "\n" + "\n".join(r.text for r in extraction.requirements)
        vector = self._embedder.embed([query])[0]
        return References(
            projects=tuple(self._reference.similar_projects(vector, self._top_k)),
            case_studies=tuple(self._reference.similar_case_studies(vector, self._top_k)),
        )

    def propose_estimate(
        self, extraction: Extraction, references: References, rate_card: RateCard
    ) -> EstimateProposal:
        """Ask for hours by role; on rule violations ask for a revision, never clamp."""
        context = {
            # Refs are left out so quarantining a line cannot change what the estimator sees.
            "requirements": [r.model_dump(exclude={"ref"}) for r in extraction.requirements],
            "allowed_roles": sorted(rate_card.entries),
            "reference_projects": [
                {
                    "id": scored.item.project_id,
                    "title": scored.item.title,
                    "similarity": scored.similarity,
                    "actual_hours_by_role": {
                        role: str(hours) for role, hours in scored.item.actual_hours_by_role.items()
                    },
                }
                for scored in references.projects
            ],
        }
        prompt = load_prompt("estimate").render(context=data_block(context))
        result = self._llm.generate(prompt, EstimateOutput)
        call = ModelCall(prompt.prompt_id, prompt.version, result.usage)
        return self._validated(result.output, (call,), rate_card, self._max_revisions)

    def price(self, proposal: EstimateProposal, rate_card: RateCard) -> Quote:
        """Compute the quote in code."""
        return price_estimate(proposal.estimate, rate_card, self._policy)

    def needs_revision(self, quote: Quote, revisions_done: int) -> bool:
        """Return True if the quote is below minimum margin and revisions remain."""
        return needs_revision(quote, revisions_done, self._max_revisions)

    def revise_for_margin(
        self, previous: EstimateProposal, quote: Quote, rate_card: RateCard
    ) -> EstimateProposal:
        """Ask the model to rebalance hours or scope (never rates) to lift the margin."""
        context: dict[str, object] = {
            "problem": "The quote is below the minimum margin set by policy.",
            "previous_estimate": [r.model_dump() for r in previous.output.roles],
            "roles_by_margin_lowest_first": margin_ranking(list(quote_roles(quote)), rate_card),
            "allowed_roles": sorted(rate_card.entries),
            "reference_project_ids": previous.output.reference_project_ids,
        }
        return self._revise(context, (), rate_card, self._max_revisions)

    def plan(
        self, quote: Quote, team: Sequence[TeamMember], start: date, weeks: int
    ) -> ResourcePlan:
        """Spread contingency-adjusted hours over the weeks and check availability."""
        return plan_resources(
            {line.role: line.adjusted_hours for line in quote.lines}, team, start, weeks
        )

    def draft(
        self,
        extraction: Extraction,
        references: References,
        quote: Quote,
        *,
        weeks: int,
        reviewer_comment: str | None,
    ) -> Draft:
        """Draft proposal prose; flag uncited claims and any figures the model wrote itself."""
        allowed_ids = {s.item.case_study_id for s in references.case_studies}
        context: dict[str, object] = {
            "title": extraction.title,
            "requirements": [r.model_dump() for r in extraction.requirements],
            "ambiguities": list(extraction.ambiguities),
            "case_studies": [
                {"id": s.item.case_study_id, "title": s.item.title, "summary": s.item.summary}
                for s in references.case_studies
            ],
            "team": [{"role": line.role} for line in quote.lines],
            "timeline_weeks": weeks,
        }
        if reviewer_comment:
            context["reviewer_comment"] = reviewer_comment
        prompt = load_prompt("draft_proposal").render(context=data_block(context))
        result = self._llm.generate(prompt, ProposalDraftOutput)
        output = result.output
        uncited = tuple(uncited_claims(output.relevant_experience, allowed_ids))
        flags: set[Flag] = set()
        if uncited:
            flags.add(Flag.UNCITED_CLAIM)
        prose = [
            output.executive_summary,
            output.understanding,
            output.approach,
            output.team_and_timeline,
        ]
        if states_figures(prose + list(output.scope_and_deliverables)):
            flags.add(Flag.MODEL_STATED_FIGURES)
        return Draft(
            output,
            frozenset(flags),
            uncited,
            (ModelCall(prompt.prompt_id, prompt.version, result.usage),),
        )

    # ---- composite use case (evals and tests)

    def quote_brief(self, brief_text: str, rate_card: RateCard) -> QuoteOutcome:
        """Run extraction through costing, including the bounded revision loop."""
        extraction = self.extract(brief_text)
        references = self.retrieve(extraction)
        proposal = self.propose_estimate(extraction, references, rate_card)
        quote = self.price(proposal, rate_card)
        revisions = 0
        calls = extraction.calls + proposal.calls
        while self.needs_revision(quote, revisions):
            proposal = self.revise_for_margin(proposal, quote, rate_card)
            quote = self.price(proposal, rate_card)
            calls += proposal.calls
            revisions += 1
        flags = set(extraction.flags | quote.flags)
        if Flag.BELOW_MINIMUM_MARGIN in quote.flags and revisions >= self._max_revisions:
            flags.add(Flag.REVISION_LIMIT_REACHED)
        return QuoteOutcome(
            extraction=extraction,
            references=references,
            proposal=proposal,
            quote=quote,
            revisions=revisions,
            flags=frozenset(flags),
            calls=calls,
        )

    # ------------------------------------------------------------ internals

    def _validated(
        self,
        output: EstimateOutput,
        calls: tuple[ModelCall, ...],
        rate_card: RateCard,
        retries_left: int,
    ) -> EstimateProposal:
        estimate = _to_estimate(output)
        try:
            validate_estimate(estimate, rate_card, self._policy)
        except EstimateValidationError as error:
            if retries_left <= 0:
                raise EstimateRejectedError(error.issues) from error
            context: dict[str, object] = {
                "problem": "The estimate broke validation rules.",
                "issues": [
                    {"code": i.code.value, "role": i.role, "message": i.message}
                    for i in error.issues
                ],
                "max_hours_per_role": str(self._policy.max_hours_per_role),
                "previous_estimate": [r.model_dump() for r in output.roles],
                "allowed_roles": sorted(rate_card.entries),
                "reference_project_ids": output.reference_project_ids,
            }
            return self._revise(context, calls, rate_card, retries_left - 1)
        return EstimateProposal(estimate, output, calls)

    def _revise(
        self,
        context: dict[str, object],
        calls: tuple[ModelCall, ...],
        rate_card: RateCard,
        retries_left: int,
    ) -> EstimateProposal:
        prompt = load_prompt("revise_estimate").render(context=data_block(context))
        result = self._llm.generate(prompt, EstimateOutput)
        call = ModelCall(prompt.prompt_id, prompt.version, result.usage)
        return self._validated(result.output, (*calls, call), rate_card, retries_left)


def quote_roles(quote: Quote) -> tuple[str, ...]:
    """Roles on a quote, in line order."""
    return tuple(line.role for line in quote.lines)
