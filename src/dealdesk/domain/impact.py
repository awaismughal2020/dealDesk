"""Impact calculator: hours, money and capacity (FTE) saved per bid and per year.

Every input is an ASSUMPTION the user can change. Results are targets to be measured, not
measurements. Machine time can come from real runs; everything else is a stated assumption.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType

from dealdesk.domain.errors import InvalidPolicyError
from dealdesk.domain.money import ONE, ZERO, round_hours, round_money


class Step(StrEnum):
    """Bid-preparation steps compared by hand and assisted."""

    EXTRACTION = "extraction"
    ESTIMATE_AND_COSTING = "estimate_and_costing"
    RESOURCE_CHECK = "resource_check"
    PROPOSAL_DRAFT = "proposal_draft"
    PIPELINE_AND_INVOICE = "pipeline_and_invoice"


#: ASSUMPTION: hours per step to do the work by hand (spec section 4; total 40 hours).
DEFAULT_BASELINE_HOURS: Mapping[Step, Decimal] = MappingProxyType(
    {
        Step.EXTRACTION: Decimal(4),
        Step.ESTIMATE_AND_COSTING: Decimal(8),
        Step.RESOURCE_CHECK: Decimal(4),
        Step.PROPOSAL_DRAFT: Decimal(20),
        Step.PIPELINE_AND_INVOICE: Decimal(4),
    }
)

#: ASSUMPTION: human review time per step when assisted (reading, correcting, approving).
DEFAULT_REVIEW_HOURS: Mapping[Step, Decimal] = MappingProxyType(
    {
        Step.EXTRACTION: Decimal("0.5"),
        Step.ESTIMATE_AND_COSTING: Decimal("1.5"),
        Step.RESOURCE_CHECK: Decimal("0.5"),
        Step.PROPOSAL_DRAFT: Decimal(4),
        Step.PIPELINE_AND_INVOICE: Decimal("0.25"),
    }
)

DEFAULT_BIDS_PER_YEAR = 60
DEFAULT_HOURLY_COST = Decimal(75)
DEFAULT_FTE_HOURS_PER_YEAR = Decimal(1650)
DEFAULT_CASHABLE_SHARE = Decimal("0.60")


@dataclass(frozen=True, slots=True)
class ImpactAssumptions:
    """All inputs to the calculator. Each one is an assumption, not a measurement."""

    baseline_hours: Mapping[Step, Decimal]
    machine_hours: Mapping[Step, Decimal]
    review_hours: Mapping[Step, Decimal]
    bids_per_year: int
    hourly_cost: Decimal
    fte_hours_per_year: Decimal
    cashable_share: Decimal

    def __post_init__(self) -> None:
        for name in ("baseline_hours", "machine_hours", "review_hours"):
            mapping: Mapping[Step, Decimal] = getattr(self, name)
            if set(mapping) != set(Step):
                raise InvalidPolicyError(f"{name} must give a value for every step")
            if any(value < ZERO for value in mapping.values()):
                raise InvalidPolicyError(f"{name} must not be negative")
            object.__setattr__(self, name, MappingProxyType(dict(mapping)))
        if self.bids_per_year < 0 or self.hourly_cost < ZERO:
            raise InvalidPolicyError("bids per year and hourly cost must not be negative")
        if self.fte_hours_per_year <= ZERO:
            raise InvalidPolicyError("FTE hours per year must be positive")
        if not ZERO <= self.cashable_share <= ONE:
            raise InvalidPolicyError("cashable share must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class StepImpact:
    """By-hand versus assisted hours for one step."""

    step: Step
    baseline_hours: Decimal
    assisted_hours: Decimal
    hours_saved: Decimal


@dataclass(frozen=True, slots=True)
class ImpactMetrics:
    """Calculator output. Savings can be negative if assisted time exceeds the baseline."""

    steps: tuple[StepImpact, ...]
    baseline_hours_per_bid: Decimal
    assisted_hours_per_bid: Decimal
    hours_saved_per_bid: Decimal
    annual_hours_saved: Decimal
    fte_equivalent: Decimal
    annual_value_full: Decimal
    annual_value_cashable: Decimal


def default_assumptions(machine_hours: Mapping[Step, Decimal] | None = None) -> ImpactAssumptions:
    """Return the spec's default assumptions, optionally with measured machine time."""
    return ImpactAssumptions(
        baseline_hours=DEFAULT_BASELINE_HOURS,
        machine_hours=machine_hours or dict.fromkeys(Step, ZERO),
        review_hours=DEFAULT_REVIEW_HOURS,
        bids_per_year=DEFAULT_BIDS_PER_YEAR,
        hourly_cost=DEFAULT_HOURLY_COST,
        fte_hours_per_year=DEFAULT_FTE_HOURS_PER_YEAR,
        cashable_share=DEFAULT_CASHABLE_SHARE,
    )


def calculate_impact(assumptions: ImpactAssumptions) -> ImpactMetrics:
    """Compute savings. Hours are rounded to 0.01, money to pence, FTE to 0.01."""
    steps = tuple(
        StepImpact(
            step=step,
            baseline_hours=round_hours(assumptions.baseline_hours[step]),
            assisted_hours=round_hours(
                assumptions.machine_hours[step] + assumptions.review_hours[step]
            ),
            hours_saved=round_hours(assumptions.baseline_hours[step])
            - round_hours(assumptions.machine_hours[step] + assumptions.review_hours[step]),
        )
        for step in Step
    )
    baseline = sum((s.baseline_hours for s in steps), ZERO)
    assisted = sum((s.assisted_hours for s in steps), ZERO)
    saved_per_bid = baseline - assisted
    annual_saved = saved_per_bid * assumptions.bids_per_year
    value_full = round_money(annual_saved * assumptions.hourly_cost)
    return ImpactMetrics(
        steps=steps,
        baseline_hours_per_bid=baseline,
        assisted_hours_per_bid=assisted,
        hours_saved_per_bid=saved_per_bid,
        annual_hours_saved=annual_saved,
        fte_equivalent=round_hours(annual_saved / assumptions.fte_hours_per_year),
        annual_value_full=value_full,
        annual_value_cashable=round_money(value_full * assumptions.cashable_share),
    )
