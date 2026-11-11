from collections import defaultdict
from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from dealdesk.domain.errors import InvalidPolicyError
from dealdesk.domain.models import Flag
from dealdesk.domain.resourcing import plan_resources
from tests.unit.domain.factories import member

D = Decimal
START = date(2026, 1, 5)


def test_spreads_evenly_and_shares_by_capacity() -> None:
    team = [member("p1", "engineer", "30"), member("p2", "engineer", "10")]
    plan = plan_resources({"engineer": D(80)}, team, START, weeks=2)
    assert plan.week_starts == (date(2026, 1, 5), date(2026, 1, 12))
    by_person = {(a.member_id, a.week_index): a.hours for a in plan.assignments}
    assert by_person == {("p1", 0): D(30), ("p2", 0): D(10), ("p1", 1): D(30), ("p2", 1): D(10)}
    assert plan.clashes == ()
    assert plan.flags == frozenset()


def test_overbooking_is_reported_as_clash_with_utilisation() -> None:
    team = [member("p1", "engineer", "20")]
    plan = plan_resources({"engineer": D(50)}, team, START, weeks=2)
    assert [(c.member_id, c.week_index, c.hours, c.utilisation) for c in plan.clashes] == [
        ("p1", 0, D(25), D("1.2500")),
        ("p1", 1, D(25), D("1.2500")),
    ]
    assert plan.clashes[1].week_start == date(2026, 1, 12)
    assert plan.flags == {Flag.RESOURCE_CLASH}


def test_role_without_people_is_unstaffed() -> None:
    plan = plan_resources({"designer": D(10)}, [member("p1", "engineer", "40")], START, weeks=1)
    assert dict(plan.unstaffed_hours) == {"designer": D(10)}
    assert plan.assignments == ()
    assert plan.flags == {Flag.UNSTAFFED_ROLE}


def test_zero_share_assignments_are_omitted() -> None:
    team = [member("p1", "engineer", "40"), member("p2", "engineer", "40")]
    plan = plan_resources({"engineer": D("0.01")}, team, START, weeks=1)
    assert [(a.member_id, a.hours) for a in plan.assignments] == [("p1", D("0.01"))]


def test_requires_at_least_one_week() -> None:
    with pytest.raises(InvalidPolicyError):
        plan_resources({}, [], START, weeks=0)


def test_members_need_positive_availability() -> None:
    with pytest.raises(InvalidPolicyError):
        member("p0", "engineer", "0")


hours = st.integers(min_value=1, max_value=200_000).map(lambda h: D(h) / 100)
capacity = st.integers(min_value=1, max_value=60).map(D)


@given(
    demand=st.dictionaries(st.sampled_from(["a", "b"]), hours, min_size=1),
    caps=st.lists(st.tuples(st.sampled_from(["a", "b", "c"]), capacity), max_size=5),
    weeks=st.integers(min_value=1, max_value=20),
)
def test_hours_are_conserved_and_clashes_are_exactly_the_overbookings(
    demand: dict[str, Decimal], caps: list[tuple[str, Decimal]], weeks: int
) -> None:
    team = [member(f"m{i}", role, str(cap)) for i, (role, cap) in enumerate(caps)]
    plan = plan_resources(demand, team, START, weeks)

    assigned: dict[str, Decimal] = defaultdict(Decimal)
    role_of = {m.member_id: m.role for m in team}
    for a in plan.assignments:
        assigned[role_of[a.member_id]] += a.hours
    for role, total in demand.items():
        assert assigned.get(role, D(0)) + plan.unstaffed_hours.get(role, D(0)) == total

    over = {(a.member_id, a.week_index) for a in plan.assignments if a.hours > a.capacity}
    assert {(c.member_id, c.week_index) for c in plan.clashes} == over
    assert all(c.utilisation > 1 for c in plan.clashes)
