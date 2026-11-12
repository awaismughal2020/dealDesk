from dataclasses import replace
from decimal import Decimal

import pytest

from dealdesk.domain.errors import InvalidPolicyError
from dealdesk.domain.impact import (
    DEFAULT_BASELINE_HOURS,
    Step,
    calculate_impact,
    default_assumptions,
)

D = Decimal


def test_default_baseline_totals_forty_hours() -> None:
    assert sum(DEFAULT_BASELINE_HOURS.values()) == D(40)


def test_defaults_worked_example() -> None:
    # baseline 40h; assisted = machine 0 + review 6.75h; saved 33.25h per bid
    metrics = calculate_impact(default_assumptions())
    assert metrics.baseline_hours_per_bid == D(40)
    assert metrics.assisted_hours_per_bid == D("6.75")
    assert metrics.hours_saved_per_bid == D("33.25")
    assert metrics.annual_hours_saved == D("1995.00")  # x 60 bids
    assert metrics.fte_equivalent == D("1.21")  # 1995 / 1650
    assert metrics.annual_value_full == D("149625.00")  # x GBP 75
    assert metrics.annual_value_cashable == D("89775.00")  # x 60%
    assert [s.step for s in metrics.steps] == list(Step)


def test_measured_machine_time_is_added_to_review_time() -> None:
    machine = dict.fromkeys(Step, D("0.1"))
    metrics = calculate_impact(default_assumptions(machine))
    assert metrics.assisted_hours_per_bid == D("7.25")


def test_savings_can_be_negative_and_are_reported_honestly() -> None:
    assumptions = replace(default_assumptions(), review_hours=dict.fromkeys(Step, D(10)))
    assert calculate_impact(assumptions).hours_saved_per_bid == D(-10)


@pytest.mark.parametrize(
    "change",
    [
        {"baseline_hours": {Step.EXTRACTION: D(1)}},
        {"machine_hours": dict.fromkeys(Step, D(-1))},
        {"bids_per_year": -1},
        {"hourly_cost": D(-1)},
        {"fte_hours_per_year": D(0)},
        {"cashable_share": D("1.1")},
    ],
)
def test_invalid_assumptions_rejected(change: dict[str, object]) -> None:
    with pytest.raises(InvalidPolicyError):
        replace(default_assumptions(), **change)  # type: ignore[arg-type]
