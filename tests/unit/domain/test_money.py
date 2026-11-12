from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from dealdesk.domain.errors import AllocationError
from dealdesk.domain.money import PENNY, allocate, round_hours, round_money, round_ratio

D = Decimal

pence = st.integers(min_value=0, max_value=10**9).map(lambda p: D(p) * PENNY)
weights = st.lists(st.integers(min_value=0, max_value=1000).map(D), min_size=1, max_size=12).filter(
    lambda ws: sum(ws) > 0
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("0.005", "0.01"), ("0.004", "0.00"), ("2.675", "2.68"), ("-0.005", "-0.01"), ("1", "1.00")],
)
def test_round_money_is_half_up(value: str, expected: str) -> None:
    assert round_money(D(value)) == D(expected)


def test_round_hours_and_ratio() -> None:
    assert round_hours(D("1.005")) == D("1.01")
    assert round_ratio(D("0.33335")) == D("0.3334")


def test_allocate_splits_30_40_30_exactly() -> None:
    parts = allocate(D("100.00"), [D(30), D(40), D(30)])
    assert parts == [D("30.00"), D("40.00"), D("30.00")]


def test_allocate_gives_leftover_pennies_to_largest_remainders_then_earliest() -> None:
    assert allocate(D("0.10"), [D(1), D(1), D(1)]) == [D("0.04"), D("0.03"), D("0.03")]
    assert allocate(D("1.00"), [D(1), D(2)]) == [D("0.33"), D("0.67")]


def test_allocate_with_custom_unit() -> None:
    assert allocate(D("1.0"), [D(1), D(1), D(1)], unit=D("0.1")) == [D("0.4"), D("0.3"), D("0.3")]


@pytest.mark.parametrize(
    ("total", "ws", "message"),
    [
        (D("1.00"), [], "at least one"),
        (D("1.00"), [D(-1), D(2)], "negative"),
        (D("1.00"), [D(0), D(0)], "all be zero"),
        (D("-1.00"), [D(1)], "total must not be negative"),
        (D("1.001"), [D(1)], "whole number"),
    ],
)
def test_allocate_rejects_bad_input(total: Decimal, ws: list[Decimal], message: str) -> None:
    with pytest.raises(AllocationError, match=message):
        allocate(total, ws)


@given(total=pence, ws=weights)
def test_allocation_always_sums_exactly(total: Decimal, ws: list[Decimal]) -> None:
    parts = allocate(total, ws)
    assert sum(parts, D(0)) == total
    assert all(part >= 0 for part in parts)
    assert all(part == part.quantize(PENNY) for part in parts)


@given(total=pence, ws=weights)
def test_allocation_is_within_one_penny_of_exact_share(total: Decimal, ws: list[Decimal]) -> None:
    weight_sum = sum(ws, D(0))
    for part, weight in zip(allocate(total, ws), ws, strict=True):
        assert abs(part - total * weight / weight_sum) < PENNY


@given(st.decimals(min_value=-(10**9), max_value=10**9, allow_nan=False, places=6))
def test_round_money_moves_at_most_half_a_penny(value: Decimal) -> None:
    rounded = round_money(value)
    assert rounded == rounded.quantize(PENNY)
    assert abs(rounded - value) <= PENNY / 2
