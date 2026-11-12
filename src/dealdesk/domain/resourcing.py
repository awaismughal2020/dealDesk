"""Resource check: spread each role's hours over the project weeks and book people.

Deterministic, no model involvement:
1. Each role's hours are split evenly across the weeks (largest remainder, 0.01 h units), so the
   weekly amounts sum exactly to the role total.
2. Each week's demand for a role is shared between the people with that role in proportion to
   their weekly availability (largest remainder again), so everyone carries the same load factor.
3. Anyone booked above 100% of availability in a week is reported as a clash. Roles with no
   people are reported as unstaffed hours.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal

from dealdesk.domain.errors import InvalidPolicyError
from dealdesk.domain.models import Assignment, Clash, ResourcePlan, Role, TeamMember
from dealdesk.domain.money import HUNDREDTH, ZERO, allocate, round_ratio

DAYS_PER_WEEK = 7


def plan_resources(
    hours_by_role: Mapping[Role, Decimal],
    team: Sequence[TeamMember],
    start: date,
    weeks: int,
) -> ResourcePlan:
    """Build a week-by-week plan and report clashes and unstaffed roles."""
    if weeks < 1:
        raise InvalidPolicyError("a plan needs at least one week")
    week_starts = tuple(start + timedelta(days=DAYS_PER_WEEK * i) for i in range(weeks))
    assignments: list[Assignment] = []
    unstaffed: dict[Role, Decimal] = {}

    for role, hours in sorted(hours_by_role.items()):
        members = sorted((m for m in team if m.role == role), key=lambda m: m.member_id)
        if not members:
            unstaffed[role] = hours
            continue
        weekly = allocate(hours, [Decimal(1)] * weeks, unit=HUNDREDTH)
        for week_index, demand in enumerate(weekly):
            shares = allocate(demand, [m.weekly_hours for m in members], unit=HUNDREDTH)
            assignments.extend(
                Assignment(m.member_id, week_index, share, m.weekly_hours)
                for m, share in zip(members, shares, strict=True)
                if share > ZERO
            )

    clashes = tuple(
        Clash(
            member_id=a.member_id,
            week_index=a.week_index,
            week_start=week_starts[a.week_index],
            hours=a.hours,
            capacity=a.capacity,
            utilisation=round_ratio(a.hours / a.capacity),
        )
        for a in assignments
        if a.hours > a.capacity
    )
    return ResourcePlan(
        week_starts=week_starts,
        assignments=tuple(assignments),
        clashes=clashes,
        unstaffed_hours=unstaffed,
    )
