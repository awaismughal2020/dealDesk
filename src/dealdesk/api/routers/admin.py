"""Admin: manage users and read the audit log."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from dealdesk.api.container import Container
from dealdesk.api.deps import ContainerDep, request_id, require_permission
from dealdesk.api.errors import ApiError
from dealdesk.api.schemas import (
    AuditEventOut,
    AuditPageOut,
    UserCreateIn,
    UserListOut,
    UserOut,
    UserPatchIn,
)
from dealdesk.auth.passwords import check_password_policy
from dealdesk.auth.policy import Permission
from dealdesk.auth.port import Principal
from dealdesk.config import AuthMode
from dealdesk.domain.models import AuditEvent
from dealdesk.ports.repositories import AuditQuery, NotFoundError, UserRecord

router = APIRouter(prefix="/v1", tags=["admin"])
Admin = Annotated[Principal, Depends(require_permission(Permission.USER_MANAGE))]
Auditor = Annotated[Principal, Depends(require_permission(Permission.AUDIT_READ))]


def _out(user: UserRecord) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _audit(
    container: Container,
    *,
    action: str,
    actor: Principal,
    subject: UUID,
    rid: str | None,
    details: dict[str, str],
) -> None:
    container.audit.append(
        AuditEvent(action, actor.user_id, "user", str(subject), datetime.now(UTC), rid, details)
    )


@router.get("/admin/users", response_model=UserListOut, operation_id="listUsers")
def list_users(_: Admin, container: ContainerDep) -> UserListOut:
    """All users."""
    return UserListOut(items=[_out(u) for u in container.users.list_all()])


@router.post("/admin/users", response_model=UserOut, status_code=201, operation_id="createUser")
def create_user(
    body: UserCreateIn, request: Request, admin: Admin, container: ContainerDep
) -> UserOut:
    """Create a local user. The password must meet the policy; it is stored only as Argon2id."""
    if container.settings.auth_mode is not AuthMode.LOCAL:
        raise ApiError(409, "Conflict", "Users are managed in the identity provider in OIDC mode.")
    check_password_policy(body.password, email=body.email)
    user = container.users.create(
        email=body.email.strip().lower(),
        display_name=body.display_name,
        role=body.role,
        password_hash=container.hasher.hash(body.password),
    )
    _audit(
        container,
        action="user.created",
        actor=admin,
        subject=user.id,
        rid=request_id(request),
        details={"role": user.role.value},
    )
    return _out(user)


@router.patch("/admin/users/{user_id}", response_model=UserOut, operation_id="updateUser")
def update_user(
    user_id: UUID, body: UserPatchIn, *, request: Request, admin: Admin, container: ContainerDep
) -> UserOut:
    """Change role or active flag. Sessions are revoked so the change applies immediately."""
    if user_id == admin.user_id and (
        body.role not in (None, admin.role) or body.is_active is False
    ):
        raise ApiError(409, "Conflict", "You cannot demote or deactivate yourself.")
    if container.users.get(user_id) is None:
        raise ApiError(404, "Not found", "No such user.")
    try:
        user = container.users.update(user_id, role=body.role, is_active=body.is_active)
    except NotFoundError as exc:
        raise ApiError(404, "Not found", "No such user.") from exc
    container.sessions.revoke_all(user_id)
    changes = {k: str(v) for k, v in body.model_dump(exclude_none=True).items()}
    _audit(
        container,
        action="user.updated",
        actor=admin,
        subject=user_id,
        rid=request_id(request),
        details=changes,
    )
    return _out(user)


@router.get("/audit", response_model=AuditPageOut, operation_id="listAuditEvents")
def audit_log(
    _: Auditor,
    *,
    container: ContainerDep,
    action: Annotated[str | None, Query(max_length=80)] = None,
    actor_id: UUID | None = None,
    subject_id: Annotated[str | None, Query(max_length=80)] = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditPageOut:
    """The append-only audit log, newest first, filterable."""
    events, total = container.audit.query(
        AuditQuery(action, actor_id, subject_id, since, until, limit, offset)
    )
    return AuditPageOut(
        items=[
            AuditEventOut(
                seq=e.seq,
                action=e.event.action,
                actor_id=e.event.actor_id,
                subject_type=e.event.subject_type,
                subject_id=e.event.subject_id,
                occurred_at=e.event.occurred_at,
                request_id=e.event.request_id,
                details=dict(e.event.details),
            )
            for e in events
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
