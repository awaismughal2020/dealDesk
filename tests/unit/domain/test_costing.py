from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from dealdesk.domain.costing import (
    needs_revision,
    price_estimate,
    price_for_margin,
    validate_estimate,
)
from dealdesk.domain.errors import EstimateIssueCode, EstimateValidationError, UnknownRoleError
from dealdesk.domain.models import Estimate, Flag, RateCard, RateCardEntry
from tests.unit.domain.factories import policy, rate_card

D = Decimal


def test_worked_example_matches_hand_calculation() -> None:
    # engineer 100h, pm 20h, contingency 10%
    # engineer: adj 110.00h, cost 110*50=5500.00, price 110*100=11000.00, subtotal 10000.00
    # pm:       adj  22.00h, cost  22*45= 990.00, price  22*80= 1760.00, subtotal  1600.00
    quote = price_estimate(Estimate({"engineer": D(100), "pm": D(20)}), rate_card(), policy())
    assert [line.role for line in quote.lines] == ["engineer", "pm"]
    assert quote.lines[0].adjusted_hours == D("110.00")
    assert quote.cost == D("6490.00")
    assert quote.price == D("12760.00")
    assert quote.subtotal == D("11600.00")
    assert quote.contingency == D("1160.00")
    # margin = (12760 - 6490) / 12760 = 0.49137...
    assert quote.margin == D("0.4914")
    assert quote.flags == frozenset()
    assert quote.target_price is None
    assert quote.price_gap_to_target is None


def test_line_money_is_rounded_half_up_to_pence() -> None:
    card = RateCard.of(RateCardEntry("x", D("33.333"), D("66.665")))
    quote = price_estimate(Estimate({"x": D("1.0")}), card, policy(contingency=D(0)))
    assert quote.lines[0].cost == D("33.33")
    assert quote.lines[0].price == D("66.67")


def test_below_target_shows_target_price_and_gap() -> None:
    card = RateCard.of(RateCardEntry("x", D(70), D(100)))  # 30% margin: below 35% target, above 25%
    quote = price_estimate(Estimate({"x": D(10)}), card, policy())
    assert quote.margin == D("0.3000")
    assert quote.flags == {Flag.BELOW_TARGET_MARGIN}
    # cost 11h * 70 = 770.00; target price = 770 / 0.65 = 1184.615... -> 1184.62
    assert quote.target_price == D("1184.62")
    assert quote.price_gap_to_target == D("1184.62") - D("1100.00")


def test_below_minimum_is_flagged() -> None:
    card = RateCard.of(RateCardEntry("x", D(90), D(100)))
    quote = price_estimate(Estimate({"x": D(10)}), card, policy())
    assert quote.flags == {Flag.BELOW_MINIMUM_MARGIN, Flag.BELOW_TARGET_MARGIN}
    assert needs_revision(quote, revisions_done=0, max_revisions=2)
    assert needs_revision(quote, revisions_done=1, max_revisions=2)
    assert not needs_revision(quote, revisions_done=2, max_revisions=2)


def test_healthy_quote_never_needs_revision() -> None:
    quote = price_estimate(Estimate({"engineer": D(10)}), rate_card(), policy())
    assert not needs_revision(quote, revisions_done=0, max_revisions=2)


def test_price_for_margin() -> None:
    assert price_for_margin(D(650), D("0.35")) == D("1000.00")


def test_validation_reports_every_issue_without_clamping() -> None:
    estimate = Estimate({"wizard": D(5), "engineer": D(0), "pm": D(5000), "designer": D("0.001")})
    with pytest.raises(EstimateValidationError) as caught:
        validate_estimate(estimate, rate_card(), policy())
    codes = {(issue.code, issue.role) for issue in caught.value.issues}
    assert codes == {
        (EstimateIssueCode.UNKNOWN_ROLE, "wizard"),
        (EstimateIssueCode.NON_POSITIVE_HOURS, "engineer"),
        (EstimateIssueCode.NON_POSITIVE_HOURS, "designer"),
        (EstimateIssueCode.ABOVE_CEILING, "pm"),
    }
    assert "wizard" in str(caught.value)


def test_empty_estimate_is_rejected() -> None:
    with pytest.raises(EstimateValidationError) as caught:
        price_estimate(Estimate({}), rate_card(), policy())
    assert caught.value.issues[0].code is EstimateIssueCode.EMPTY


def test_negative_hours_rejected() -> None:
    with pytest.raises(EstimateValidationError):
        price_estimate(Estimate({"engineer": D(-3)}), rate_card(), policy())


def test_unknown_role_lookup_raises() -> None:
    with pytest.raises(UnknownRoleError, match="ghost"):
        rate_card().rate_for("ghost")


hours = st.decimals(min_value=D("0.1"), max_value=D(2000), places=1)
rates = st.decimals(min_value=D(1), max_value=D(500), places=2)


@given(
    hours_map=st.dictionaries(st.sampled_from(["a", "b", "c"]), hours, min_size=1),
    cost_rates=st.tuples(rates, rates, rates),
    markups=st.tuples(rates, rates, rates),
    contingency=st.decimals(min_value=D(0), max_value=D("0.5"), places=2),
)
def test_margin_bounds_and_totals(
    hours_map: dict[str, Decimal],
    cost_rates: tuple[Decimal, Decimal, Decimal],
    markups: tuple[Decimal, Decimal, Decimal],
    contingency: Decimal,
) -> None:
    card = RateCard.of(
        *(
            RateCardEntry(role, cost, cost + markup)
            for role, cost, markup in zip("abc", cost_rates, markups, strict=True)
        )
    )
    quote = price_estimate(Estimate(hours_map), card, policy(contingency=contingency))
    assert D(0) <= quote.margin < D(1)  # sell >= cost on every line
    assert quote.price == sum(line.price for line in quote.lines)
    assert quote.cost == sum(line.cost for line in quote.lines)
    assert quote.subtotal + quote.contingency == quote.price
    assert (Flag.BELOW_MINIMUM_MARGIN in quote.flags) == (quote.margin < D("0.25"))
    if quote.target_price is not None:
        assert quote.target_price >= quote.price
