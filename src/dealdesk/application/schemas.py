"""Strict schemas for everything a model may return. Extra fields are rejected.

Hours are strings matching a decimal pattern so no provider ever emits a float, and so the schema
works with every provider's structured-output mode (no free-form maps).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

HOURS_PATTERN = r"^\d{1,5}(\.\d{1,2})?$"

Category = Literal[
    "functional", "non_functional", "integration", "data", "ux", "security", "delivery", "other"
]
Priority = Literal["must", "should", "could"]


class StrictModel(BaseModel):
    """Base for model outputs: no extra keys, immutable, whitespace trimmed."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ExtractedRequirement(StrictModel):
    """One requirement, quoted or closely paraphrased from the brief."""

    ref: str = Field(pattern=r"^R-\d{1,3}$")
    text: str = Field(min_length=3, max_length=500)
    category: Category
    priority: Priority


class ExtractionOutput(StrictModel):
    """Output of the `extract_requirements` prompt."""

    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(max_length=1200)
    requirements: list[ExtractedRequirement] = Field(max_length=60)
    ambiguities: list[str] = Field(max_length=20)


class RoleHours(StrictModel):
    """Proposed hours for one role. Validated against the rate card by code."""

    role: str = Field(min_length=1, max_length=60)
    hours: str = Field(pattern=HOURS_PATTERN)

    @property
    def hours_decimal(self) -> Decimal:
        """Hours as a Decimal (the pattern guarantees this parses)."""
        return Decimal(self.hours)


class EstimateOutput(StrictModel):
    """Output of the `estimate` and `revise_estimate` prompts."""

    roles: list[RoleHours] = Field(min_length=1, max_length=20)
    rationale: str = Field(max_length=2000)
    reference_project_ids: list[str] = Field(max_length=10)
    assumptions: list[str] = Field(max_length=20)


class ExperienceClaim(StrictModel):
    """A claim about past work. Must cite at least one retrieved case study id."""

    text: str = Field(min_length=3, max_length=600)
    source_ids: list[str] = Field(max_length=5)


class ProposalDraftOutput(StrictModel):
    """Output of the `draft_proposal` prompt. Commercials and terms are added by code."""

    executive_summary: str = Field(max_length=3000)
    understanding: str = Field(max_length=3000)
    scope_and_deliverables: list[str] = Field(max_length=30)
    approach: str = Field(max_length=3000)
    team_and_timeline: str = Field(max_length=2000)
    assumptions_and_exclusions: list[str] = Field(max_length=30)
    relevant_experience: list[ExperienceClaim] = Field(max_length=10)
