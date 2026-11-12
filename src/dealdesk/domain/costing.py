"""Costing and margin policy. Every number here is computed by code, never by a model.

Rules (docs/SPEC.md section 4):
    adjusted_hours = hours * (1 + contingency)          (rounded to 0.01 h, half-up)
    cost  = sum(adjusted_hours * cost_rate)             (each line rounded to pence, half-up)
    price = sum(adjusted_hours * sell_rate)             (each line rounded to pence, half-up)
    margin = (price - cost) / price                     (rounded to 4 dp, half-up)
    target_price = cost / (1 - target_margin)           (only when margin < target)

Adjusted hours are rounded before money is computed so every displayed line reconciles exactly.
"""

from __future__ import annotations

from decimal import Decimal

from dealdesk.domain.errors import EstimateIssue, EstimateIssueCode, EstimateValidationError
from dealdesk.domain.models import CostingPolicy, Estimate, Flag, Quote, QuoteLine, RateCard
from dealdesk.domain.money import HUNDREDTH, ONE, ZERO, round_hours, round_money, round_ratio


def validate_estimate(estimate: Estimate, rate_card: RateCard, policy: CostingPolicy) -> None:
    """Raise `EstimateValidationError` listing every rule the estimate breaks.

    Unknown roles, non-positive hours and hours above the ceiling are rejected, never clamped:
    the caller is expected to ask for a revision.
    """
    issues: list[EstimateIssue] = []
    if not estimate.hours_by_role:
        issues.append(EstimateIssue(EstimateIssueCode.EMPTY, "", "estimate has no roles"))
    for role, hours in sorted(estimate.hours_by_role.items()):
        if not rate_card.has(role):
            issues.append(
                EstimateIssue(EstimateIssueCode.UNKNOWN_ROLE, role, f"{role!r} is not a known role")
            )
        if hours < HUNDREDTH:
            issues.append(
                EstimateIssue(
                    EstimateIssueCode.NON_POSITIVE_HOURS,
                    role,
                    f"{role!r} hours must be positive (at least {HUNDREDTH})",
                )
            )
        elif hours > policy.max_hours_per_role:
            issues.append(
                EstimateIssue(
                    EstimateIssueCode.ABOVE_CEILING,
                    role,
                    f"{role!r} hours exceed the ceiling of {policy.max_hours_per_role}",
                )
            )
    if issues:
        raise EstimateValidationError(tuple(issues))


def price_for_margin(cost: Decimal, margin: Decimal) -> Decimal:
    """Return the price earning `margin` on `cost`: cost / (1 - margin), to pence."""
    return round_money(cost / (ONE - margin))


def price_estimate(estimate: Estimate, rate_card: RateCard, policy: CostingPolicy) -> Quote:
    """Validate the estimate and compute a quote with margin flags."""
    validate_estimate(estimate, rate_card, policy)
    lines = tuple(
        _price_line(role, hours, rate_card, policy)
        for role, hours in sorted(estimate.hours_by_role.items())
    )
    subtotal = sum((line.subtotal for line in lines), ZERO)
    price = sum((line.price for line in lines), ZERO)
    cost = sum((line.cost for line in lines), ZERO)
    margin = round_ratio((price - cost) / price)

    flags: set[Flag] = set()
    target_price: Decimal | None = None
    gap: Decimal | None = None
    if margin < policy.minimum_margin:
        flags.add(Flag.BELOW_MINIMUM_MARGIN)
    if margin < policy.target_margin:
        flags.add(Flag.BELOW_TARGET_MARGIN)
        target_price = price_for_margin(cost, policy.target_margin)
        gap = target_price - price
    return Quote(
        lines=lines,
        subtotal=subtotal,
        contingency=price - subtotal,
        price=price,
        cost=cost,
        margin=margin,
        flags=frozenset(flags),
        target_price=target_price,
        price_gap_to_target=gap,
    )


def needs_revision(quote: Quote, revisions_done: int, max_revisions: int) -> bool:
    """Return True if the quote is below minimum margin and revisions remain."""
    return Flag.BELOW_MINIMUM_MARGIN in quote.flags and revisions_done < max_revisions


def _price_line(role: str, hours: Decimal, rate_card: RateCard, policy: CostingPolicy) -> QuoteLine:
    rates = rate_card.rate_for(role)
    adjusted = round_hours(hours * (ONE + policy.contingency))
    return QuoteLine(
        role=role,
        hours=hours,
        adjusted_hours=adjusted,
        cost_rate=rates.cost_rate,
        sell_rate=rates.sell_rate,
        subtotal=round_money(hours * rates.sell_rate),
        cost=round_money(adjusted * rates.cost_rate),
        price=round_money(adjusted * rates.sell_rate),
    )
