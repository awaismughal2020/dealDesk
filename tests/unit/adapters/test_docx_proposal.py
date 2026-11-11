"""The proposal .docx opens and its commercials table is exactly the code-computed quote."""

import io
import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime

import pytest
from docx import Document

from dealdesk.adapters.docx.proposal import DRAFT_MARKER, DocxProposalRenderer, money
from dealdesk.adapters.reference_memory import InMemoryReferenceData
from dealdesk.application.pipeline import DealPipeline
from dealdesk.application.proposal import TERMS, build_proposal_document
from dealdesk.domain.invoicing import build_invoice_schedule
from dealdesk.domain.models import InvoicePolicy
from dealdesk.ports.documents import ProposalDocument
from dealdesk.ports.repositories import RunRecord, RunStatus
from tests.unit.domain.factories import D

NOW = datetime(2026, 3, 2, 9, 30, tzinfo=UTC)


@pytest.fixture
def proposal(
    make_pipeline: Callable[..., DealPipeline],
    brief: Callable[[str], str],
    reference: InMemoryReferenceData,
) -> ProposalDocument:
    pipeline = make_pipeline()
    outcome = pipeline.quote_brief(brief("clean_brief"), reference.rate_card())
    draft = pipeline.draft(
        outcome.extraction, outcome.references, outcome.quote, weeks=12, reviewer_comment=None
    )
    schedule = build_invoice_schedule(
        outcome.quote.price,
        date(2026, 3, 16),
        InvoicePolicy((D(30), D(40), D(30)), (0, 42, 84), D("0.20")),
    )
    run = RunRecord(
        id=uuid.UUID(int=1),
        title="t",
        status=RunStatus.RUNNING,
        created_by=uuid.uuid4(),
        created_at=NOW,
        updated_at=NOW,
        brief_document_id=uuid.uuid4(),
        brief_filename="b.txt",
        start_date=date(2026, 3, 16),
    )
    return build_proposal_document(
        run,
        extraction=outcome.extraction,
        references=outcome.references,
        quote=outcome.quote,
        schedule=schedule,
        sections=draft.output,
        flags=["BELOW_TARGET_MARGIN"],
        weeks=12,
        generated_at=NOW,
    )


def open_docx(data: bytes):
    return Document(io.BytesIO(data))


def all_text(document) -> str:
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        parts.extend(cell.text for row in table.rows for cell in row.cells)
    return "\n".join(parts)


def test_draft_opens_with_marker_footer_and_sections(proposal: ProposalDocument) -> None:
    renderer = DocxProposalRenderer()
    assert renderer.content_type.endswith("wordprocessingml.document")
    document = open_docx(renderer.render(proposal))
    section = document.sections[0]
    assert DRAFT_MARKER in section.header.paragraphs[0].text
    assert "AI-assisted" in section.footer.paragraphs[0].text
    headings = [p.text for p in document.paragraphs if p.style.name.startswith("Heading")]
    assert headings == [
        "Review notes (internal, remove before sending)",
        "1. Executive summary",
        "2. Understanding of requirements",
        "3. Scope and deliverables",
        "4. Approach",
        "5. Team and timeline",
        "6. Commercials",
        "7. Assumptions and exclusions",
        "8. Relevant experience",
        "9. Terms",
    ]
    text = all_text(document)
    assert DRAFT_MARKER in text
    assert all(term in text for term in TERMS)
    assert "Flag: BELOW_TARGET_MARGIN" in text


def test_commercials_table_is_the_code_computed_quote(proposal: ProposalDocument) -> None:
    document = open_docx(DocxProposalRenderer().render(proposal))
    commercials = document.tables[1]
    rows = [[cell.text for cell in row.cells] for row in commercials.rows]
    assert rows[0] == ["Role", "Hours", "Hours incl. contingency", "Rate per hour", "Price"]
    for line, row in zip(proposal.quote.lines, rows[1:], strict=False):
        assert row[1:] == [
            str(line.hours),
            str(line.adjusted_hours),
            money(line.sell_rate),
            money(line.price),
        ]
    assert rows[-1] == ["Total price (excluding VAT)", "", "", "", money(proposal.quote.price)]
    assert money(proposal.quote.price) == "£137,830.00"
    milestones = [[cell.text for cell in row.cells] for row in document.tables[2].rows]
    assert milestones[-1][3:] == [
        money(proposal.schedule.net_total),
        money(proposal.schedule.vat_total),
        money(proposal.schedule.gross_total),
    ]
    text = all_text(document)  # internal figures (margin, cost) never reach the client document
    assert str(proposal.quote.margin) not in text
    assert money(proposal.quote.cost) not in text


def test_citations_and_sources(proposal: ProposalDocument) -> None:
    text = all_text(open_docx(DocxProposalRenderer().render(proposal)))
    first = proposal.relevant_experience[0]
    assert f"[{first.source_ids[0]}]" in text
    assert f"{proposal.sources[0][0]}: {proposal.sources[0][1]}" in text


def test_final_version_has_no_draft_marker(proposal: ProposalDocument) -> None:
    final = replace(
        proposal, is_final=True, approved_by="Demo Approver (SAMPLE)", approved_at=NOW, flags=()
    )
    document = open_docx(DocxProposalRenderer().render(final))
    text = all_text(document)
    assert DRAFT_MARKER not in text
    assert (
        "FINAL, approved by Demo Approver (SAMPLE)"
        in document.sections[0].header.paragraphs[0].text
    )
    assert "Review notes" not in text


def test_uncited_and_empty_experience(proposal: ProposalDocument) -> None:
    from dealdesk.ports.documents import CitedClaim

    uncited = replace(proposal, relevant_experience=(CitedClaim("claim", ()),), sources=())
    assert "claim [UNCITED]" in all_text(open_docx(DocxProposalRenderer().render(uncited)))
    empty = replace(proposal, relevant_experience=(), sources=())
    assert "No cited experience" in all_text(open_docx(DocxProposalRenderer().render(empty)))


def test_final_flag_requires_an_approval(proposal: ProposalDocument) -> None:
    assert proposal.is_final is False
