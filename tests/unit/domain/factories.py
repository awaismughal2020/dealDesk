"""Small builders for domain tests."""

from decimal import Decimal

from dealdesk.domain.models import CostingPolicy, InvoicePolicy, RateCard, RateCardEntry, TeamMember

D = Decimal


def rate_card() -> RateCard:
    return RateCard.of(
        RateCardEntry("engineer", D(50), D(100)),
        RateCardEntry("designer", D(40), D(90)),
        RateCardEntry("pm", D(45), D(80)),
    )


def policy(**overrides: Decimal) -> CostingPolicy:
    values = {
        "contingency": D("0.10"),
        "target_margin": D("0.35"),
        "minimum_margin": D("0.25"),
        "max_hours_per_role": D(2000),
    }
    values.update(overrides)
    return CostingPolicy(**values)


def invoice_policy() -> InvoicePolicy:
    return InvoicePolicy(
        percentages=(D(30), D(40), D(30)), offset_days=(0, 42, 84), vat_rate=D("0.20")
    )


def member(member_id: str, role: str, weekly: str) -> TeamMember:
    return TeamMember(
        member_id=member_id, name=f"Sample {member_id}", role=role, weekly_hours=D(weekly)
    )
