from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from dealdesk.domain.errors import AllocationError, InvalidPolicyError
from dealdesk.domain.invoicing import build_invoice_schedule
from dealdesk.domain.models import InvoicePolicy
from tests.unit.domain.factories import invoice_policy

D = Decimal
START = date(2026, 2, 2)


def test_default_30_40_30_schedule_with_vat() -> None:
    schedule = build_invoice_schedule(D("12760.00"), START, invoice_policy())
    rows = [(m.sequence, m.due_date, m.net, m.vat, m.gross) for m in schedule.milestones]
    assert rows == [
        (1, date(2026, 2, 2), D("3828.00"), D("765.60"), D("4593.60")),
        (2, date(2026, 3, 16), D("5104.00"), D("1020.80"), D("6124.80")),
        (3, date(2026, 4, 27), D("3828.00"), D("765.60"), D("4593.60")),
    ]
    assert schedule.vat_total == D("2552.00")
    assert schedule.gross_total == D("15312.00")
    assert schedule.vat_rate == D("0.20")


def test_awkward_total_still_sums_exactly() -> None:
    schedule = build_invoice_schedule(D("100.01"), START, invoice_policy())
    assert [m.net for m in schedule.milestones] == [D("30.00"), D("40.01"), D("30.00")]
    assert sum(m.net for m in schedule.milestones) == D("100.01")


def test_non_positive_total_rejected() -> None:
    with pytest.raises(AllocationError):
        build_invoice_schedule(D(0), START, invoice_policy())


@pytest.mark.parametrize(
    ("percentages", "offsets", "vat"),
    [
        ((), (), D("0.2")),
        ((D(50), D(50)), (0,), D("0.2")),
        ((D(50), D(40)), (0, 10), D("0.2")),
        ((D(110), D(-10)), (0, 10), D("0.2")),
        ((D(50), D(50)), (10, 0), D("0.2")),
        ((D(50), D(50)), (-1, 0), D("0.2")),
        ((D(100),), (0,), D("1.5")),
    ],
)
def test_invalid_invoice_policies(
    percentages: tuple[Decimal, ...], offsets: tuple[int, ...], vat: Decimal
) -> None:
    with pytest.raises(InvalidPolicyError):
        InvoicePolicy(percentages=percentages, offset_days=offsets, vat_rate=vat)


@given(
    pence=st.integers(min_value=1, max_value=10**10),
    vat_pct=st.integers(min_value=0, max_value=99),
)
def test_every_column_sums_to_its_total(pence: int, vat_pct: int) -> None:
    policy = InvoicePolicy((D(30), D(40), D(30)), (0, 30, 60), D(vat_pct) / 100)
    schedule = build_invoice_schedule(D(pence) / 100, START, policy)
    assert sum(m.net for m in schedule.milestones) == schedule.net_total
    assert sum(m.vat for m in schedule.milestones) == schedule.vat_total
    assert sum(m.gross for m in schedule.milestones) == schedule.gross_total
