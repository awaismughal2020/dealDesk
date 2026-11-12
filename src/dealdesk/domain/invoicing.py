"""Invoice milestone schedule: net, VAT and gross per milestone, each column summing exactly."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from dealdesk.domain.errors import AllocationError
from dealdesk.domain.models import InvoiceMilestone, InvoicePolicy, InvoiceSchedule
from dealdesk.domain.money import ZERO, allocate, round_money


def build_invoice_schedule(
    net_total: Decimal, start: date, policy: InvoicePolicy
) -> InvoiceSchedule:
    """Split a net (ex-VAT) total into milestones.

    VAT is computed once on the total (rounded to pence, half-up) and allocated with the same
    weights as the net, so net, VAT and gross each sum exactly to their totals.
    """
    if net_total <= ZERO:
        raise AllocationError("an invoice schedule needs a positive net total")
    net_total = round_money(net_total)
    vat_total = round_money(net_total * policy.vat_rate)
    nets = allocate(net_total, policy.percentages)
    vats = allocate(vat_total, policy.percentages)
    milestones = tuple(
        InvoiceMilestone(
            sequence=index + 1,
            percentage=percentage,
            due_date=start + timedelta(days=offset),
            net=net,
            vat=vat,
            gross=net + vat,
        )
        for index, (percentage, offset, net, vat) in enumerate(
            zip(policy.percentages, policy.offset_days, nets, vats, strict=True)
        )
    )
    return InvoiceSchedule(
        milestones=milestones,
        net_total=net_total,
        vat_total=vat_total,
        gross_total=net_total + vat_total,
        vat_rate=policy.vat_rate,
    )
