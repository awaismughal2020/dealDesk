"""Proposal rendering port. The renderer lays out content; it never computes a number."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from dealdesk.domain.models import InvoiceSchedule, Quote


@dataclass(frozen=True, slots=True)
class CitedClaim:
    """A relevant-experience claim and the case-study ids it cites."""

    text: str
    source_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProposalDocument:
    """Everything a proposal shows. Money comes only from the code-computed quote and schedule."""

    title: str
    run_reference: str
    generated_at: datetime
    executive_summary: str
    understanding: str
    scope_and_deliverables: tuple[str, ...]
    approach: str
    team_and_timeline: str
    team_roles: tuple[tuple[str, str], ...]  # (role label, adjusted hours as text)
    start_date: date
    weeks: int
    quote: Quote
    schedule: InvoiceSchedule
    assumptions_and_exclusions: tuple[str, ...]
    relevant_experience: tuple[CitedClaim, ...]
    sources: tuple[tuple[str, str], ...]  # (case-study id, title)
    terms: tuple[str, ...]
    flags: tuple[str, ...]
    is_final: bool
    approved_by: str | None = None
    approved_at: datetime | None = None


class ProposalRendererPort(Protocol):
    """Turns a proposal into a document file."""

    @property
    def content_type(self) -> str:
        """MIME type of the rendered file."""

    def render(self, document: ProposalDocument) -> bytes:
        """Render the proposal."""
