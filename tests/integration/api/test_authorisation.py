"""Deny by default: no unprotected route, a full permission matrix, separation of duties."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from dealdesk.api.app import PUBLIC_ROUTES, ROUTERS
from dealdesk.api.deps import PERMISSION_ATTR
from dealdesk.domain.models import UserRole
from tests.integration.api.conftest import ROLES, Api, start_sample_run

pytestmark = pytest.mark.integration


def _permissions(dependant: Dependant) -> list[str]:
    found = []
    if dependant.call is not None and hasattr(dependant.call, PERMISSION_ATTR):
        found.append(str(getattr(dependant.call, PERMISSION_ATTR)))
    for child in dependant.dependencies:
        found.extend(_permissions(child))
    return found


def _routes(_api: Api) -> list[tuple[str, str, APIRoute]]:
    return [
        (method, route.path, route)
        for router in ROUTERS
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in sorted(route.methods)
    ]


def test_route_enumeration_matches_what_the_app_serves(api: Api) -> None:
    served = {
        (method.upper(), path)
        for path, operations in api.app.openapi()["paths"].items()
        for method in operations
    }
    assert {(m, p) for m, p, _ in _routes(api)} == served
    assert len(served) > len(PUBLIC_ROUTES)


def test_every_route_requires_a_permission_unless_explicitly_public(api: Api) -> None:
    unprotected = [
        (method, path)
        for method, path, route in _routes(api)
        if not _permissions(route.dependant) and (method, path) not in PUBLIC_ROUTES
    ]
    assert unprotected == []
    registered = {(m, p) for m, p, _ in _routes(api)}
    assert registered >= PUBLIC_ROUTES  # the allowlist names only real routes
    public_with_permission = [
        (m, p) for m, p, r in _routes(api) if (m, p) in PUBLIC_ROUTES and _permissions(r.dependant)
    ]
    assert public_with_permission == []


def test_anonymous_requests_to_protected_routes_get_401(api: Api) -> None:
    client = api.anonymous()
    fake_id = "00000000-0000-0000-0000-000000000000"
    for method, path, _ in _routes(api):
        if (method, path) in PUBLIC_ROUTES:
            continue
        url = path.replace("{run_id}", fake_id).replace("{user_id}", fake_id)
        response = client.request(method, url, json={})
        assert response.status_code == 401, (method, path, response.status_code)
        assert response.headers["content-type"] == "application/problem+json"


# ---------------------------------------------------------------- the permission matrix

Case = tuple[str, str, Callable[[Api, dict[str, Any]], dict[str, Any]], set[UserRole], int]


def _no_body(_api: Api, _ctx: dict[str, Any]) -> dict[str, Any]:
    return {}


def _sample(_api: Api, _ctx: dict[str, Any]) -> dict[str, Any]:
    return {"data": {"sample_id": "clean_brief"}}


def _comment(_api: Api, _ctx: dict[str, Any]) -> dict[str, Any]:
    return {"json": {"comment": "matrix test"}}


def _impact(api: Api, _ctx: dict[str, Any]) -> dict[str, Any]:
    estimator = api.as_role(UserRole.ESTIMATOR)
    return {"json": estimator.get("/v1/impact").json()["assumptions"]}


def _new_user(_api: Api, ctx: dict[str, Any]) -> dict[str, Any]:
    return {
        "json": {
            "email": f"new-{ctx['n']}@test.example",
            "display_name": "N",
            "role": "viewer",
            "password": "kettle-orbit-lantern",
        }
    }


def _patch_user(_api: Api, _ctx: dict[str, Any]) -> dict[str, Any]:
    return {"json": {"role": "estimator"}}


EVERYONE = set(ROLES)
CASES: list[Case] = [
    ("GET", "/v1/auth/me", _no_body, EVERYONE, 200),
    ("GET", "/v1/runs", _no_body, EVERYONE, 200),
    ("GET", "/v1/runs/{run_id}", _no_body, EVERYONE, 200),
    ("GET", "/v1/runs/{run_id}/proposal.docx", _no_body, EVERYONE, 200),
    ("GET", "/v1/impact", _no_body, EVERYONE, 200),
    ("POST", "/v1/impact/calculate", _impact, EVERYONE, 200),
    ("GET", "/v1/samples", _no_body, {UserRole.ESTIMATOR, UserRole.ADMIN}, 200),
    ("POST", "/v1/runs", _sample, {UserRole.ESTIMATOR, UserRole.ADMIN}, 202),
    ("POST", "/v1/runs/{run_id}/approve", _comment, {UserRole.APPROVER}, 200),
    ("POST", "/v1/runs/{run_id}/reject", _comment, {UserRole.APPROVER}, 200),
    ("GET", "/v1/admin/users", _no_body, {UserRole.ADMIN}, 200),
    ("POST", "/v1/admin/users", _new_user, {UserRole.ADMIN}, 201),
    ("PATCH", "/v1/admin/users/{user_id}", _patch_user, {UserRole.ADMIN}, 200),
    ("GET", "/v1/audit", _no_body, {UserRole.ADMIN}, 200),
    ("POST", "/v1/auth/logout", _no_body, EVERYONE, 204),
]


@pytest.mark.parametrize("role", [*ROLES, None], ids=[*(r.value for r in ROLES), "anonymous"])
@pytest.mark.parametrize("case", CASES, ids=[f"{c[0]} {c[1]}" for c in CASES])
def test_permission_matrix(api: Api, case: Case, role: UserRole | None) -> None:
    method, path, body, allowed, success = case
    run = start_sample_run(api.as_role(UserRole.ESTIMATOR))
    target_user, _ = api.add_user(UserRole.VIEWER)
    target_id = next(u.id for u in api.container.users.list_all() if u.email == target_user)
    url = path.replace("{run_id}", run["id"]).replace("{user_id}", str(target_id))
    client = api.as_role(role) if role else api.anonymous()
    response = client.request(method, url, **body(api, {"n": f"{method}{role}"}))
    expected = success if role in allowed else (403 if role else 401)
    assert response.status_code == expected, response.text


def test_separation_of_duties_blocks_approving_own_run(api: Api) -> None:
    email, _ = api.add_user(UserRole.ESTIMATOR)
    creator = api.login(email)
    run = start_sample_run(creator)
    admin = api.as_role(UserRole.ADMIN)
    user_id = next(u.id for u in api.container.users.list_all() if u.email == email)
    assert admin.patch(f"/v1/admin/users/{user_id}", json={"role": "approver"}).status_code == 200

    promoted = api.login(email)  # role change revoked old sessions; sign in again
    detail = promoted.get(f"/v1/runs/{run['id']}").json()
    assert detail["actions"] == {
        "can_decide": False,
        "decide_blocked_reason": (
            "You created this run, so someone else must approve it (separation of duties)."
        ),
    }
    response = promoted.post(f"/v1/runs/{run['id']}/approve", json={"comment": "self"})
    assert response.status_code == 403
    assert response.json()["title"] == "Separation of duties"
    other = api.as_role(UserRole.APPROVER)
    assert other.get(f"/v1/runs/{run['id']}").json()["actions"]["can_decide"] is True


def test_rejection_needs_a_comment_and_decisions_need_the_right_state(api: Api) -> None:
    run = start_sample_run(api.as_role(UserRole.ESTIMATOR))
    approver = api.as_role(UserRole.APPROVER)
    blank = approver.post(f"/v1/runs/{run['id']}/reject", json={"comment": "  "})
    assert blank.status_code == 422
    assert blank.json()["title"] == "Comment required"
    assert approver.post(f"/v1/runs/{run['id']}/approve", json={}).status_code == 200
    again = approver.post(f"/v1/runs/{run['id']}/approve", json={})
    assert again.status_code == 409


def test_unknown_objects_are_404_problems(api: Api) -> None:
    client = api.as_role(UserRole.APPROVER)
    missing = "11111111-1111-1111-1111-111111111111"
    for url in (f"/v1/runs/{missing}", f"/v1/runs/{missing}/proposal.docx"):
        response = client.get(url)
        assert response.status_code == 404
        assert response.json()["instance"] == url
    assert client.post(f"/v1/runs/{missing}/approve", json={}).status_code == 404
    admin = api.as_role(UserRole.ADMIN)
    assert admin.patch(f"/v1/admin/users/{missing}", json={"is_active": False}).status_code == 404


def test_admin_cannot_lock_themselves_out_and_deactivation_is_immediate(api: Api) -> None:
    admin = api.as_role(UserRole.ADMIN)
    me = admin.get("/v1/auth/me").json()
    assert admin.patch(f"/v1/admin/users/{me['id']}", json={"is_active": False}).status_code == 409
    assert admin.patch(f"/v1/admin/users/{me['id']}", json={"role": "viewer"}).status_code == 409
    email, _ = api.add_user(UserRole.VIEWER)
    viewer = api.login(email)
    user_id = next(u.id for u in api.container.users.list_all() if u.email == email)
    assert admin.patch(f"/v1/admin/users/{user_id}", json={"is_active": False}).status_code == 200
    assert viewer.get("/v1/auth/me").status_code == 401  # access token no longer honoured
    assert viewer.post("/v1/auth/refresh").status_code == 401  # sessions revoked


def test_admin_user_creation_enforces_password_policy(api: Api) -> None:
    admin = api.as_role(UserRole.ADMIN)
    base = {"email": "policy@test.example", "display_name": "P", "role": "viewer"}
    for weak in ("short-pw", "password1234"):
        response = admin.post("/v1/admin/users", json={**base, "password": weak})
        assert response.status_code == 422
        assert response.json()["title"] == "Password not accepted"
    created = admin.post("/v1/admin/users", json={**base, "password": "kettle-orbit-lantern"})
    assert created.status_code == 201
    assert "password" not in created.text
    duplicate = admin.post(
        "/v1/admin/users",
        json={**base, "email": "POLICY@test.example", "password": "kettle-orbit-lantern"},
    )
    assert duplicate.status_code == 409
    assert (
        api.login("policy@test.example", "kettle-orbit-lantern").get("/v1/auth/me").json()["role"]
        == "viewer"
    )


def test_audit_log_is_filterable_and_records_actor_and_request_id(api: Api) -> None:
    admin = api.as_role(UserRole.ADMIN)
    response = admin.get("/v1/audit", params={"action": "auth.login_succeeded", "limit": 2})
    page = response.json()
    assert page["total"] >= 1
    assert len(page["items"]) <= 2
    event = page["items"][0]
    assert event["actor_id"] is not None
    assert event["request_id"]
    assert admin.get("/v1/audit", params={"limit": 500}).status_code == 422
