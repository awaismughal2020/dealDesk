"""Money and quantity arithmetic. GBP, `Decimal` only, half-up rounding, exact allocations."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from dealdesk.domain.errors import AllocationError

PENNY = Decimal("0.01")
HUNDREDTH = Decimal("0.01")
RATIO_PLACES = Decimal("0.0001")
ZERO = Decimal(0)
ONE = Decimal(1)
HUNDRED = Decimal(100)


def round_money(amount: Decimal) -> Decimal:
    """Round to whole pence, half-up (the convention used on UK invoices)."""
    return amount.quantize(PENNY, rounding=ROUND_HALF_UP)


def round_hours(hours: Decimal) -> Decimal:
    """Round hours to hundredths, half-up."""
    return hours.quantize(HUNDREDTH, rounding=ROUND_HALF_UP)


def round_ratio(ratio: Decimal) -> Decimal:
    """Round a ratio (margin, utilisation, share) to four decimal places, half-up."""
    return ratio.quantize(RATIO_PLACES, rounding=ROUND_HALF_UP)


def allocate(total: Decimal, weights: Sequence[Decimal], unit: Decimal = PENNY) -> list[Decimal]:
    """Split `total` across `weights` so the parts sum to `total` exactly.

    Largest-remainder method: every part gets the floor of its exact share in `unit`s, then the
    leftover units go one each to the parts with the largest fractional remainders. Ties go to
    the earlier part, so the result is deterministic.
    """
    if not weights:
        raise AllocationError("at least one weight is required")
    if any(weight < ZERO for weight in weights):
        raise AllocationError("weights must not be negative")
    weight_sum = sum(weights, ZERO)
    if weight_sum == ZERO:
        raise AllocationError("weights must not all be zero")
    if total < ZERO:
        raise AllocationError("total must not be negative")
    if total != total.quantize(unit):
        raise AllocationError(f"total {total} is not a whole number of {unit}")

    units = int(total / unit)
    exact = [Decimal(units) * weight / weight_sum for weight in weights]
    floors = [int(share.to_integral_value(rounding=ROUND_DOWN)) for share in exact]
    leftover = units - sum(floors)
    by_remainder = sorted(range(len(weights)), key=lambda i: (-(exact[i] - floors[i]), i))
    for index in by_remainder[:leftover]:
        floors[index] += 1
    return [Decimal(count) * unit for count in floors]
