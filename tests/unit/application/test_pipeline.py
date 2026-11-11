import json
from collections.abc import Callable
from datetime import date
from decimal import Decimal

import pytest

from dealdesk.adapters.reference_memory import InMemoryReferenceData
from dealdesk.application.pipeline import (
    DealPipeline,
    EstimateRejectedError,
    margin_ranking,
    quote_roles,
)
from dealdesk.domain.models import Flag
from tests.unit.application.conftest import ScriptedLLM

D = Decimal


def estimate_json(**hours: str) -> str:
    return json.dumps(
        {
            "roles": [{"role": r, "hours": h} for r, h in hours.items()],
            "rationale": "scripted",
            "reference_project_ids": ["PP-001"],
            "assumptions": [],
        }
    )


def test_clean_brief_quote(
    make_pipeline: Callable[..., DealPipeline],
    brief: Callable[[str], str],
    reference: InMemoryReferenceData,
) -> None:
    outcome = make_pipeline().quote_brief(brief("clean_brief"), reference.rate_card())
    assert len(outcome.extraction.requirements) == 8
    assert outcome.references.projects[0].item.project_id == "PP-001"
    assert outcome.quote.price == D("137830.00")
    assert outcome.flags == {Flag.BELOW_TARGET_MARGIN}
    assert [c.prompt_id for c in outcome.calls] == ["extract_requirements", "estimate"]


def test_injection_is_quarantined_and_changes_nothing(
    make_pipeline: Callable[..., DealPipeline],
    brief: Callable[[str], str],
    reference: InMemoryReferenceData,
) -> None:
    pipeline = make_pipeline()
    clean = pipeline.quote_brief(brief("clean_brief"), reference.rate_card())
    attacked = pipeline.quote_brief(brief("injection_brief"), reference.rate_card())
    assert len(attacked.extraction.quarantined) == 2
    assert Flag.POSSIBLE_PROMPT_INJECTION in attacked.flags
    assert attacked.quote == clean.quote
    assert attacked.proposal.estimate == clean.proposal.estimate


def test_low_margin_triggers_bounded_revisions(
    make_pipeline: Callable[..., DealPipeline],
    brief: Callable[[str], str],
    reference: InMemoryReferenceData,
) -> None:
    outcome = make_pipeline().quote_brief(brief("ambiguous_brief"), reference.rate_card())
    assert outcome.revisions == 1
    assert Flag.BELOW_MINIMUM_MARGIN not in outcome.quote.flags
    assert outcome.calls[-1].prompt_id == "revise_estimate"


def test_escalates_when_revisions_do_not_fix_margin(
    make_pipeline: Callable[..., DealPipeline],
    brief: Callable[[str], str],
    reference: InMemoryReferenceData,
) -> None:
    ml_only = estimate_json(ml_engineer="100")
    llm = ScriptedLLM({"estimate": [ml_only], "revise_estimate": [ml_only, ml_only]})
    outcome = make_pipeline(llm).quote_brief(brief("clean_brief"), reference.rate_card())
    assert outcome.revisions == 2
    assert {Flag.BELOW_MINIMUM_MARGIN, Flag.REVISION_LIMIT_REACHED} <= outcome.flags
    revise_context = json.loads(
        llm.prompts[-1].user.split("<untrusted_data>\n")[1].split("\n</untrusted_data>")[0]
    )
    assert revise_context["roles_by_margin_lowest_first"] == ["ml_engineer"]
    assert "rate" not in json.dumps(revise_context["previous_estimate"])


def test_invalid_estimate_is_revised_not_clamped(
    make_pipeline: Callable[..., DealPipeline],
    brief: Callable[[str], str],
    reference: InMemoryReferenceData,
) -> None:
    llm = ScriptedLLM(
        {
            "estimate": [estimate_json(wizard="10", engineer="5000")],
            "revise_estimate": [estimate_json(engineer="200")],
        }
    )
    pipeline = make_pipeline(llm)
    extraction = pipeline.extract(brief("clean_brief"))
    proposal = pipeline.propose_estimate(
        extraction, pipeline.retrieve(extraction), reference.rate_card()
    )
    assert proposal.estimate.hours_by_role == {"engineer": D(200)}
    assert [c.prompt_id for c in proposal.calls] == ["estimate", "revise_estimate"]
    issues = json.loads(
        llm.prompts[-1].user.split("<untrusted_data>\n")[1].split("\n</untrusted_data>")[0]
    )["issues"]
    assert {i["code"] for i in issues} == {"UNKNOWN_ROLE", "ABOVE_CEILING"}


def test_estimate_rejected_after_budget(
    make_pipeline: Callable[..., DealPipeline],
    brief: Callable[[str], str],
    reference: InMemoryReferenceData,
) -> None:
    bad = estimate_json(engineer="0")
    pipeline = make_pipeline(ScriptedLLM({"estimate": [bad], "revise_estimate": [bad, bad]}))
    extraction = pipeline.extract(brief("clean_brief"))
    with pytest.raises(EstimateRejectedError, match="positive"):
        pipeline.propose_estimate(extraction, pipeline.retrieve(extraction), reference.rate_card())


def test_duplicate_roles_are_summed(
    make_pipeline: Callable[..., DealPipeline],
    brief: Callable[[str], str],
    reference: InMemoryReferenceData,
) -> None:
    payload = json.loads(estimate_json(engineer="10"))
    payload["roles"].append({"role": "engineer", "hours": "5.5"})
    pipeline = make_pipeline(ScriptedLLM({"estimate": [json.dumps(payload)]}))
    extraction = pipeline.extract(brief("clean_brief"))
    proposal = pipeline.propose_estimate(
        extraction, pipeline.retrieve(extraction), reference.rate_card()
    )
    assert proposal.estimate.hours_by_role == {"engineer": D("15.5")}


def test_plan_and_draft(
    make_pipeline: Callable[..., DealPipeline],
    brief: Callable[[str], str],
    reference: InMemoryReferenceData,
) -> None:
    pipeline = make_pipeline()
    outcome = pipeline.quote_brief(brief("clean_brief"), reference.rate_card())
    plan = pipeline.plan(outcome.quote, reference.team(), date(2026, 1, 5), 12)
    assert len(plan.week_starts) == 12
    assert Flag.RESOURCE_CLASH in plan.flags
    draft = pipeline.draft(
        outcome.extraction,
        outcome.references,
        outcome.quote,
        weeks=12,
        reviewer_comment="Shorter please",
    )
    assert draft.flags == frozenset()
    assert "Shorter please" in draft.output.executive_summary
    assert {c for claim in draft.output.relevant_experience for c in claim.source_ids} <= {
        s.item.case_study_id for s in outcome.references.case_studies
    }
    assert quote_roles(outcome.quote)[0] == "delivery_lead"


def test_draft_flags_uncited_claims_and_stated_figures(
    make_pipeline: Callable[..., DealPipeline],
    brief: Callable[[str], str],
    reference: InMemoryReferenceData,
) -> None:
    draft_json = json.dumps(
        {
            "executive_summary": "We will do it for £1.",
            "understanding": "u",
            "scope_and_deliverables": [],
            "approach": "a",
            "team_and_timeline": "t",
            "assumptions_and_exclusions": [],
            "relevant_experience": [{"text": "We built the moon", "source_ids": []}],
        }
    )
    pipeline = make_pipeline(ScriptedLLM({"draft_proposal": [draft_json]}))
    outcome = pipeline.quote_brief(brief("clean_brief"), reference.rate_card())
    draft = pipeline.draft(
        outcome.extraction, outcome.references, outcome.quote, weeks=12, reviewer_comment=None
    )
    assert draft.flags == {Flag.UNCITED_CLAIM, Flag.MODEL_STATED_FIGURES}
    assert draft.uncited_claim_indexes == (0,)


def test_margin_ranking_is_computed_by_code(reference: InMemoryReferenceData) -> None:
    card = reference.rate_card()
    assert margin_ranking(["solution_architect", "ml_engineer", "ghost", "ux_designer"], card) == [
        "ml_engineer",
        "ux_designer",
        "solution_architect",
    ]
