"""Domain entities and value objects. Immutable, `Decimal` for every quantity, no I/O."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID

from dealdesk.domain.errors import InvalidPolicyError, UnknownRoleError
from dealdesk.domain.money import HUNDRED, ONE, ZERO

Role = str
MIN_SELL_RATE = ONE  # GBP per hour; guarantees every priced line is at least one penny


class Flag(StrEnum):
    """Conditions a human reviewer must see before approving."""

    BELOW_MINIMUM_MARGIN = "BELOW_MINIMUM_MARGIN"
    BELOW_TARGET_MARGIN = "BELOW_TARGET_MARGIN"
    REVISION_LIMIT_REACHED = "REVISION_LIMIT_REACHED"
    RESOURCE_CLASH = "RESOURCE_CLASH"
    UNSTAFFED_ROLE = "UNSTAFFED_ROLE"
    UNCITED_CLAIM = "UNCITED_CLAIM"
    MODEL_STATED_FIGURES = "MODEL_STATED_FIGURES"
    POSSIBLE_PROMPT_INJECTION = "POSSIBLE_PROMPT_INJECTION"
    ESTIMATE_REJECTED = "ESTIMATE_REJECTED"


@dataclass(frozen=True, slots=True)
class Brief:
    """A client brief (RFP). Its text is untrusted input."""

    title: str
    text: str
    filename: str


@dataclass(frozen=True, slots=True)
class Requirement:
    """One requirement extracted from a brief."""

    ref: str
    text: str
    category: str
    priority: str


@dataclass(frozen=True, slots=True)
class RateCardEntry:
    """Hourly cost and sell rates for one role, in GBP."""

    role: Role
    cost_rate: Decimal
    sell_rate: Decimal

    def __post_init__(self) -> None:
        if self.cost_rate < ZERO or self.sell_rate < MIN_SELL_RATE:
            raise InvalidPolicyError(
                f"rates for {self.role!r}: cost must be >= 0 and sell >= {MIN_SELL_RATE}"
            )


@dataclass(frozen=True, slots=True)
class RateCard:
    """All roles that can be quoted."""

    entries: Mapping[Role, RateCardEntry]

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", MappingProxyType(dict(self.entries)))

    @classmethod
    def of(cls, *entries: RateCardEntry) -> RateCard:
        """Build a rate card from entries."""
        return cls({entry.role: entry for entry in entries})

    def rate_for(self, role: Role) -> RateCardEntry:
        """Return the rates for `role`, or raise `UnknownRoleError`."""
        try:
            return self.entries[role]
        except KeyError:
            raise UnknownRoleError(role) from None

    def has(self, role: Role) -> bool:
        """Return True if `role` is on the card."""
        return role in self.entries


@dataclass(frozen=True, slots=True)
class CostingPolicy:
    """Commercial guard rails. All ratios are fractions (0.25 means 25%)."""

    contingency: Decimal
    target_margin: Decimal
    minimum_margin: Decimal
    max_hours_per_role: Decimal

    def __post_init__(self) -> None:
        if not ZERO <= self.contingency <= ONE:
            raise InvalidPolicyError("contingency must be between 0 and 1")
        if not ZERO <= self.minimum_margin <= self.target_margin < ONE:
            raise InvalidPolicyError("require 0 <= minimum margin <= target margin < 1")
        if self.max_hours_per_role <= ZERO:
            raise InvalidPolicyError("max hours per role must be positive")


@dataclass(frozen=True, slots=True)
class Estimate:
    """Proposed effort, hours by role. Proposed by the model, validated by code."""

    hours_by_role: Mapping[Role, Decimal]
    rationale: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "hours_by_role", MappingProxyType(dict(self.hours_by_role)))

    @property
    def total_hours(self) -> Decimal:
        """Sum of hours across roles."""
        return sum(self.hours_by_role.values(), ZERO)


@dataclass(frozen=True, slots=True)
class QuoteLine:
    """One role's contribution to a quote. Money is rounded to pence at this level."""

    role: Role
    hours: Decimal
    adjusted_hours: Decimal
    cost_rate: Decimal
    sell_rate: Decimal
    subtotal: Decimal
    cost: Decimal
    price: Decimal


@dataclass(frozen=True, slots=True)
class Quote:
    """A fully computed quote. `margin` is a fraction of price."""

    lines: tuple[QuoteLine, ...]
    subtotal: Decimal
    contingency: Decimal
    price: Decimal
    cost: Decimal
    margin: Decimal
    flags: frozenset[Flag]
    target_price: Decimal | None
    price_gap_to_target: Decimal | None


@dataclass(frozen=True, slots=True)
class TeamMember:
    """A person who can be scheduled. Availability is net of other commitments."""

    member_id: str
    name: str
    role: Role
    weekly_hours: Decimal

    def __post_init__(self) -> None:
        if self.weekly_hours <= ZERO:
            raise InvalidPolicyError(f"{self.member_id} must have positive weekly availability")


@dataclass(frozen=True, slots=True)
class Assignment:
    """Hours assigned to one person in one week."""

    member_id: str
    week_index: int
    hours: Decimal
    capacity: Decimal


@dataclass(frozen=True, slots=True)
class Clash:
    """A person booked above 100% of their availability in a week."""

    member_id: str
    week_index: int
    week_start: date
    hours: Decimal
    capacity: Decimal
    utilisation: Decimal


@dataclass(frozen=True, slots=True)
class ResourcePlan:
    """Hours per person per week, plus clashes and roles nobody can cover."""

    week_starts: tuple[date, ...]
    assignments: tuple[Assignment, ...]
    clashes: tuple[Clash, ...]
    unstaffed_hours: Mapping[Role, Decimal] = field(default_factory=dict)

    @property
    def flags(self) -> frozenset[Flag]:
        """Flags raised by this plan."""
        flags: set[Flag] = set()
        if self.clashes:
            flags.add(Flag.RESOURCE_CLASH)
        if self.unstaffed_hours:
            flags.add(Flag.UNSTAFFED_ROLE)
        return frozenset(flags)


@dataclass(frozen=True, slots=True)
class InvoicePolicy:
    """Milestone percentages (summing to 100), due-date offsets in days, and the VAT rate."""

    percentages: tuple[Decimal, ...]
    offset_days: tuple[int, ...]
    vat_rate: Decimal

    def __post_init__(self) -> None:
        if not self.percentages or len(self.percentages) != len(self.offset_days):
            raise InvalidPolicyError("need one due-date offset per milestone percentage")
        if any(p <= ZERO for p in self.percentages) or sum(self.percentages, ZERO) != HUNDRED:
            raise InvalidPolicyError("milestone percentages must be positive and sum to 100")
        if any(day < 0 for day in self.offset_days) or list(self.offset_days) != sorted(
            self.offset_days
        ):
            raise InvalidPolicyError("milestone offsets must be non-negative and non-decreasing")
        if not ZERO <= self.vat_rate < ONE:
            raise InvalidPolicyError("VAT rate must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class InvoiceMilestone:
    """One invoice: net, VAT and gross shown separately."""

    sequence: int
    percentage: Decimal
    due_date: date
    net: Decimal
    vat: Decimal
    gross: Decimal


@dataclass(frozen=True, slots=True)
class InvoiceSchedule:
    """All milestones; each column sums exactly to its total."""

    milestones: tuple[InvoiceMilestone, ...]
    net_total: Decimal
    vat_total: Decimal
    gross_total: Decimal
    vat_rate: Decimal


class Decision(StrEnum):
    """A human decision on a run."""

    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class Approval:
    """Who decided what, when and why."""

    run_id: UUID
    decided_by: UUID
    decision: Decision
    comment: str
    decided_at: datetime


@dataclass(frozen=True, slots=True)
class PipelineRecord:
    """An approved opportunity in the sales pipeline."""

    run_id: UUID
    title: str
    value: Decimal
    margin: Decimal
    stage: str
    approved_by: UUID
    approved_at: datetime


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """An append-only record of something that happened."""

    action: str
    actor_id: UUID | None
    subject_type: str
    subject_id: str
    occurred_at: datetime
    request_id: str | None = None
    details: Mapping[str, str] = field(default_factory=dict)
