"""JSON forms of step outputs, stored on the run record. Decimals and dates become strings."""

from __future__ import annotations

from decimal import Decimal

from dealdesk.application.pipeline import Draft, EstimateProposal, Extraction, References
from dealdesk.application.schemas import (
    EstimateOutput,
    ExtractedRequirement,
    ProposalDraftOutput,
)
from dealdesk.domain.models import (
    CaseStudy,
    Estimate,
    Flag,
    InvoiceSchedule,
    PastProject,
    Quote,
    QuoteLine,
    ResourcePlan,
    TeamMember,
)
from dealdesk.domain.money import round_ratio
from dealdesk.ports.repositories import JsonDict, Scored


def _s(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def extraction_to_json(extraction: Extraction) -> JsonDict:
    """Serialise requirements (kept and quarantined), title, summary and ambiguities."""
    return {
        "title": extraction.title,
        "summary": extraction.summary,
        "requirements": [r.model_dump() for r in extraction.requirements],
        "quarantined": [r.model_dump() for r in extraction.quarantined],
        "ambiguities": list(extraction.ambiguities),
        "flags": sorted(f.value for f in extraction.flags),
    }


def extraction_from_json(data: JsonDict) -> Extraction:
    """Inverse of `extraction_to_json` (model-call accounting is not restored)."""
    return Extraction(
        title=data["title"],
        summary=data["summary"],
        requirements=tuple(ExtractedRequirement.model_validate(r) for r in data["requirements"]),
        quarantined=tuple(ExtractedRequirement.model_validate(r) for r in data["quarantined"]),
        ambiguities=tuple(data["ambiguities"]),
        flags=frozenset(Flag(f) for f in data["flags"]),
        calls=(),
    )


def references_to_json(references: References) -> list[JsonDict]:
    """Serialise retrieved projects and case studies with similarity scores."""
    projects = [
        {
            "kind": "project",
            "id": s.item.project_id,
            "title": s.item.title,
            "sector": s.item.sector,
            "summary": s.item.summary,
            "similarity": s.similarity,
            "actual_hours_by_role": {k: str(v) for k, v in s.item.actual_hours_by_role.items()},
        }
        for s in references.projects
    ]
    studies = [
        {
            "kind": "case_study",
            "id": s.item.case_study_id,
            "project_id": s.item.project_id,
            "title": s.item.title,
            "summary": s.item.summary,
            "similarity": s.similarity,
        }
        for s in references.case_studies
    ]
    return projects + studies


def references_from_json(data: list[JsonDict]) -> References:
    """Inverse of `references_to_json`."""
    projects = tuple(
        Scored(
            PastProject(
                d["id"],
                d["title"],
                d["sector"],
                d["summary"],
                {k: Decimal(v) for k, v in d["actual_hours_by_role"].items()},
            ),
            d["similarity"],
        )
        for d in data
        if d["kind"] == "project"
    )
    studies = tuple(
        Scored(CaseStudy(d["id"], d["project_id"], d["title"], d["summary"]), d["similarity"])
        for d in data
        if d["kind"] == "case_study"
    )
    return References(projects, studies)


def proposal_to_json(proposal: EstimateProposal) -> JsonDict:
    """Serialise the validated estimate and the model output it came from."""
    return {
        "hours_by_role": {k: str(v) for k, v in sorted(proposal.estimate.hours_by_role.items())},
        "total_hours": str(proposal.estimate.total_hours),
        "model_output": proposal.output.model_dump(),
    }


def proposal_from_json(data: JsonDict) -> EstimateProposal:
    """Inverse of `proposal_to_json`."""
    output = EstimateOutput.model_validate(data["model_output"])
    estimate = Estimate({k: Decimal(v) for k, v in data["hours_by_role"].items()}, output.rationale)
    return EstimateProposal(estimate, output, ())


def quote_to_json(quote: Quote) -> JsonDict:
    """Serialise a quote with every amount as a string."""
    return {
        "lines": [
            {
                "role": line.role,
                "hours": str(line.hours),
                "adjusted_hours": str(line.adjusted_hours),
                "cost_rate": str(line.cost_rate),
                "sell_rate": str(line.sell_rate),
                "subtotal": str(line.subtotal),
                "cost": str(line.cost),
                "price": str(line.price),
            }
            for line in quote.lines
        ],
        "subtotal": str(quote.subtotal),
        "contingency": str(quote.contingency),
        "price": str(quote.price),
        "cost": str(quote.cost),
        "margin": str(quote.margin),
        "flags": sorted(f.value for f in quote.flags),
        "target_price": _s(quote.target_price),
        "price_gap_to_target": _s(quote.price_gap_to_target),
    }


def quote_from_json(data: JsonDict) -> Quote:
    """Inverse of `quote_to_json`."""
    return Quote(
        lines=tuple(
            QuoteLine(
                role=line["role"],
                hours=Decimal(line["hours"]),
                adjusted_hours=Decimal(line["adjusted_hours"]),
                cost_rate=Decimal(line["cost_rate"]),
                sell_rate=Decimal(line["sell_rate"]),
                subtotal=Decimal(line["subtotal"]),
                cost=Decimal(line["cost"]),
                price=Decimal(line["price"]),
            )
            for line in data["lines"]
        ),
        subtotal=Decimal(data["subtotal"]),
        contingency=Decimal(data["contingency"]),
        price=Decimal(data["price"]),
        cost=Decimal(data["cost"]),
        margin=Decimal(data["margin"]),
        flags=frozenset(Flag(f) for f in data["flags"]),
        target_price=Decimal(data["target_price"]) if data["target_price"] else None,
        price_gap_to_target=(
            Decimal(data["price_gap_to_target"]) if data["price_gap_to_target"] else None
        ),
    )


def plan_to_json(plan: ResourcePlan, team: list[TeamMember]) -> JsonDict:
    """Serialise a resource plan for display: people, weeks, hours, clashes."""
    names = {m.member_id: (m.name, m.role) for m in team}
    used = sorted({a.member_id for a in plan.assignments})
    return {
        "week_starts": [d.isoformat() for d in plan.week_starts],
        "people": [
            {"member_id": m, "name": names[m][0], "role": names[m][1]} for m in used if m in names
        ],
        "assignments": [
            {
                "member_id": a.member_id,
                "week_index": a.week_index,
                "hours": str(a.hours),
                "capacity": str(a.capacity),
                "utilisation": str(round_ratio(a.hours / a.capacity)),
            }
            for a in plan.assignments
        ],
        "clashes": [
            {
                "member_id": c.member_id,
                "week_index": c.week_index,
                "week_start": c.week_start.isoformat(),
                "hours": str(c.hours),
                "capacity": str(c.capacity),
                "utilisation": str(c.utilisation),
            }
            for c in plan.clashes
        ],
        "unstaffed_hours": {k: str(v) for k, v in plan.unstaffed_hours.items()},
        "flags": sorted(f.value for f in plan.flags),
    }


def schedule_to_json(schedule: InvoiceSchedule) -> JsonDict:
    """Serialise invoice milestones with net, VAT and gross."""
    return {
        "milestones": [
            {
                "sequence": m.sequence,
                "percentage": str(m.percentage),
                "due_date": m.due_date.isoformat(),
                "net": str(m.net),
                "vat": str(m.vat),
                "gross": str(m.gross),
            }
            for m in schedule.milestones
        ],
        "net_total": str(schedule.net_total),
        "vat_total": str(schedule.vat_total),
        "gross_total": str(schedule.gross_total),
        "vat_rate": str(schedule.vat_rate),
    }


def draft_to_json(draft: Draft, schedule: InvoiceSchedule) -> JsonDict:
    """Serialise proposal prose, its flags and the code-computed payment schedule."""
    return {
        "sections": draft.output.model_dump(),
        "flags": sorted(f.value for f in draft.flags),
        "uncited_claim_indexes": list(draft.uncited_claim_indexes),
        "schedule": schedule_to_json(schedule),
    }


def draft_sections(data: JsonDict) -> ProposalDraftOutput:
    """Return proposal prose from a stored draft."""
    return ProposalDraftOutput.model_validate(data["sections"])
