"""Render a proposal as a Word document with python-docx.

Layout only: every figure comes from the code-computed quote and invoice schedule in the
`ProposalDocument`. Drafts carry a visible "DRAFT, requires approval" marker in the header and on
the title page; every version carries an AI-assisted footer.
"""

from __future__ import annotations

import io
from collections.abc import Iterable, Sequence
from decimal import Decimal

from docx import Document
from docx.document import Document as DocumentObject
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

from dealdesk.ports.documents import ProposalDocument

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DRAFT_MARKER = "DRAFT, requires approval"
AI_FOOTER = (
    "AI-assisted document. Prose drafted by a language model; every figure computed by code. "
    "SAMPLE DATA, not real client or company data."
)
RED = RGBColor(0xB0, 0x00, 0x20)
GREEN = RGBColor(0x1B, 0x5E, 0x20)
MARKER_SIZE = Pt(14)
TABLE_STYLE = "Table Grid"


def money(value: Decimal) -> str:
    """Format GBP for display (presentation only; no arithmetic)."""
    return f"£{value:,.2f}"


def percent(value: Decimal) -> str:
    """Format a percentage figure for display."""
    return f"{value.normalize():f}%"


class DocxProposalRenderer:
    """Implements `ProposalRendererPort`."""

    @property
    def content_type(self) -> str:
        """MIME type of the output."""
        return DOCX_CONTENT_TYPE

    def render(self, document: ProposalDocument) -> bytes:
        """Build the .docx and return its bytes."""
        doc = Document()
        doc.core_properties.title = document.title
        doc.core_properties.author = "Deal Desk (SAMPLE)"
        doc.core_properties.comments = AI_FOOTER
        self._header_footer(doc, document)
        self._title_page(doc, document)
        if not document.is_final and document.flags:
            self._heading(doc, "Review notes (internal, remove before sending)")
            self._bullets(doc, (f"Flag: {flag}" for flag in document.flags))
        self._section(doc, "1. Executive summary", document.executive_summary)
        self._section(doc, "2. Understanding of requirements", document.understanding)
        self._heading(doc, "3. Scope and deliverables")
        self._bullets(doc, document.scope_and_deliverables)
        self._section(doc, "4. Approach", document.approach)
        self._team(doc, document)
        self._commercials(doc, document)
        self._heading(doc, "7. Assumptions and exclusions")
        self._bullets(doc, document.assumptions_and_exclusions)
        self._experience(doc, document)
        self._heading(doc, "9. Terms")
        for number, term in enumerate(document.terms, start=1):
            doc.add_paragraph(f"{number}. {term}")
        buffer = io.BytesIO()
        doc.save(buffer)
        return buffer.getvalue()

    # ------------------------------------------------------------ parts

    @staticmethod
    def _header_footer(doc: DocumentObject, document: ProposalDocument) -> None:
        section = doc.sections[0]
        header = section.header.paragraphs[0]
        if document.is_final:
            header.text = (
                f"FINAL, approved by {document.approved_by} on {document.approved_at:%d %B %Y}"
            )
        else:
            run = header.add_run(DRAFT_MARKER)
            run.bold = True
            run.font.color.rgb = RED
        footer = section.footer.paragraphs[0]
        footer.text = f"{AI_FOOTER} Ref {document.run_reference}."
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER

    @staticmethod
    def _title_page(doc: DocumentObject, document: ProposalDocument) -> None:
        doc.add_heading(f"Proposal: {document.title}", level=0)
        marker = doc.add_paragraph()
        text = (
            f"FINAL, approved by {document.approved_by} "
            f"on {document.approved_at:%d %B %Y %H:%M} UTC"
            if document.is_final
            else DRAFT_MARKER
        )
        run = marker.add_run(text)
        run.bold = True
        run.font.size = MARKER_SIZE
        run.font.color.rgb = GREEN if document.is_final else RED
        doc.add_paragraph(
            f"Reference {document.run_reference} · generated {document.generated_at:%d %B %Y} · "
            "AI-assisted draft prepared from SAMPLE data"
        )

    @staticmethod
    def _heading(doc: DocumentObject, text: str) -> None:
        doc.add_heading(text, level=1)

    def _section(self, doc: DocumentObject, title: str, body: str) -> None:
        self._heading(doc, title)
        doc.add_paragraph(body)

    @staticmethod
    def _bullets(doc: DocumentObject, items: Iterable[str]) -> None:
        for item in items:
            doc.add_paragraph(item, style="List Bullet")

    @staticmethod
    def _table(doc: DocumentObject, header: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
        table = doc.add_table(rows=1, cols=len(header))
        table.style = TABLE_STYLE
        for cell, text in zip(table.rows[0].cells, header, strict=True):
            cell.text = text
            cell.paragraphs[0].runs[0].bold = True
        for row in rows:
            cells = table.add_row().cells
            for cell, text in zip(cells, row, strict=True):
                cell.text = text

    def _team(self, doc: DocumentObject, document: ProposalDocument) -> None:
        self._section(doc, "5. Team and timeline", document.team_and_timeline)
        doc.add_paragraph(
            f"Planned start {document.start_date:%d %B %Y}, over {document.weeks} weeks."
        )
        self._table(doc, ("Role", "Hours (incl. contingency)"), document.team_roles)

    def _commercials(self, doc: DocumentObject, document: ProposalDocument) -> None:
        quote, schedule = document.quote, document.schedule
        self._heading(doc, "6. Commercials")
        doc.add_paragraph(
            "All figures are computed by code from the estimate and the rate card. "
            "Prices exclude VAT."
        )
        rows = [
            (
                line.role.replace("_", " ").capitalize(),
                str(line.hours),
                str(line.adjusted_hours),
                money(line.sell_rate),
                money(line.price),
            )
            for line in quote.lines
        ]
        rows += [
            ("Subtotal before contingency", "", "", "", money(quote.subtotal)),
            ("Contingency", "", "", "", money(quote.contingency)),
            ("Total price (excluding VAT)", "", "", "", money(quote.price)),
        ]
        self._table(
            doc, ("Role", "Hours", "Hours incl. contingency", "Rate per hour", "Price"), rows
        )
        doc.add_paragraph(f"Payment milestones (VAT at {percent(schedule.vat_rate * 100)}):")
        milestones = [
            (
                str(m.sequence),
                percent(m.percentage),
                f"{m.due_date:%d %b %Y}",
                money(m.net),
                money(m.vat),
                money(m.gross),
            )
            for m in schedule.milestones
        ]
        milestones.append(
            (
                "Total",
                "100%",
                "",
                money(schedule.net_total),
                money(schedule.vat_total),
                money(schedule.gross_total),
            )
        )
        self._table(doc, ("Milestone", "Share", "Due", "Net", "VAT", "Gross"), milestones)

    def _experience(self, doc: DocumentObject, document: ProposalDocument) -> None:
        self._heading(doc, "8. Relevant experience")
        if not document.relevant_experience:
            doc.add_paragraph("No cited experience is included in this draft.")
        for claim in document.relevant_experience:
            citation = ", ".join(claim.source_ids) or "UNCITED"
            doc.add_paragraph(f"{claim.text} [{citation}]", style="List Bullet")
        if document.sources:
            doc.add_paragraph("Sources (SAMPLE case studies):")
            for source_id, title in document.sources:
                doc.add_paragraph(f"{source_id}: {title}")
