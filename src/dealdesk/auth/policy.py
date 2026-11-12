"""The single place where roles map to permissions. Deny by default.

| Capability                                   | viewer | estimator | approver            | admin |
| Read runs, proposals and the impact panel    | yes    | yes       | yes                 | yes   |
| Create runs and upload briefs                | no     | yes       | no                  | yes   |
| Approve or reject a run                      | no     | no        | yes, never own runs | no    |
| Manage users and read the audit log          | no     | no        | no                  | yes   |

Separation of duties (never your own run) is an object-level rule enforced in the application
layer (`RunService.decide`), not here.
"""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType

from dealdesk.domain.models import UserRole


class Permission(StrEnum):
    """Things a route can require."""

    SESSION = "session"  # any signed-in, active user (who am I, sign out)
    RUN_READ = "run:read"
    RUN_CREATE = "run:create"
    RUN_DECIDE = "run:decide"
    IMPACT_READ = "impact:read"
    USER_MANAGE = "user:manage"
    AUDIT_READ = "audit:read"


_READ = frozenset({Permission.SESSION, Permission.RUN_READ, Permission.IMPACT_READ})

ROLE_PERMISSIONS = MappingProxyType(
    {
        UserRole.VIEWER: _READ,
        UserRole.ESTIMATOR: _READ | {Permission.RUN_CREATE},
        UserRole.APPROVER: _READ | {Permission.RUN_DECIDE},
        UserRole.ADMIN: _READ
        | {Permission.RUN_CREATE, Permission.USER_MANAGE, Permission.AUDIT_READ},
    }
)


def has_permission(role: UserRole, permission: Permission) -> bool:
    """Return True if `role` grants `permission`. Unknown roles get nothing."""
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def permissions_for(role: UserRole) -> list[str]:
    """Sorted permission names for a role (shown to the UI for usability only)."""
    return sorted(p.value for p in ROLE_PERMISSIONS.get(role, frozenset()))
