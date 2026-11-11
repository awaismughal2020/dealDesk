"""Typed domain errors. Each carries enough structure for callers to act on it."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DomainError(Exception):
    """Base class for all domain rule violations."""


class AllocationError(DomainError):
    """An amount cannot be allocated as requested."""


class InvalidPolicyError(DomainError):
    """A policy or reference value is inconsistent."""


class UnknownRoleError(DomainError):
    """A role is not on the rate card."""

    def __init__(self, role: str) -> None:
        super().__init__(f"role {role!r} is not on the rate card")
        self.role = role


class SeparationOfDutiesError(DomainError):
    """The person who created a run tried to approve or reject it."""


class EstimateIssueCode(StrEnum):
    """Why a proposed estimate was rejected."""

    EMPTY = "EMPTY"
    UNKNOWN_ROLE = "UNKNOWN_ROLE"
    NON_POSITIVE_HOURS = "NON_POSITIVE_HOURS"
    ABOVE_CEILING = "ABOVE_CEILING"


@dataclass(frozen=True, slots=True)
class EstimateIssue:
    """One problem with one role in a proposed estimate."""

    code: EstimateIssueCode
    role: str
    message: str


class EstimateValidationError(DomainError):
    """A model-proposed estimate broke the rules. Triggers a revision; never silently clamped."""

    def __init__(self, issues: tuple[EstimateIssue, ...]) -> None:
        super().__init__("; ".join(issue.message for issue in issues))
        self.issues = issues
