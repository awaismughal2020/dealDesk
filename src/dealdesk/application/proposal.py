"""Assemble the proposal document from model prose and code-computed figures."""

from __future__ import annotations

from datetime import datetime

from dealdesk.application.pipeline import Extraction, References
from dealdesk.application.schemas import ProposalDraftOutput
from dealdesk.domain.models import InvoiceSchedule, Quote
from dealdesk.ports.documents import CitedClaim, ProposalDocument
from dealdesk.ports.repositories import RunRecord

#: Standard terms, written by people (not generated). SAMPLE wording for the demo.
TERMS = (
    "SAMPLE: generated for demonstration. This is not an offer from any real company.",
    "Prices are in GBP and exclude VAT; VAT is shown separately at the configured rate.",
    "Contingency is included in the hours shown and is not a separate charge.",
    "Invoices are raised per the milestone schedule and are payable within 30 days.",
    "This proposal is valid for 30 days from the date of issue.",
)


def role_label(role: str) -> str:
    """Human label for a rate-card role key."""
    return role.replace("_", " ").capitalize()


def build_proposal_document(
    run: RunRecord,
    *,
    extraction: Extraction,
    references: References,
    quote: Quote,
    schedule: InvoiceSchedule,
    sections: ProposalDraftOutput,
    flags: list[str],
    weeks: int,
    generated_at: datetime,
    approved_by: str | None = None,
    approved_at: datetime | None = None,
) -> ProposalDocument:
    """Combine prose and figures. `is_final` is true only when an approval is supplied."""
    cited = {cid for claim in sections.relevant_experience for cid in claim.source_ids}
    return ProposalDocument(
        title=extraction.title,
        run_reference=f"RUN-{run.id.hex[:8].upper()}",
        generated_at=generated_at,
        executive_summary=sections.executive_summary,
        understanding=sections.understanding,
        scope_and_deliverables=tuple(sections.scope_and_deliverables),
        approach=sections.approach,
        team_and_timeline=sections.team_and_timeline,
        team_roles=tuple((role_label(line.role), str(line.adjusted_hours)) for line in quote.lines),
        start_date=run.start_date,
        weeks=weeks,
        quote=quote,
        schedule=schedule,
        assumptions_and_exclusions=tuple(sections.assumptions_and_exclusions),
        relevant_experience=tuple(
            CitedClaim(claim.text, tuple(claim.source_ids))
            for claim in sections.relevant_experience
        ),
        sources=tuple(
            (s.item.case_study_id, s.item.title)
            for s in references.case_studies
            if s.item.case_study_id in cited
        ),
        terms=TERMS,
        flags=tuple(sorted(set(flags))),
        is_final=approved_by is not None and approved_at is not None,
        approved_by=approved_by,
        approved_at=approved_at,
    )
