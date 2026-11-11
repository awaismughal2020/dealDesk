"""Token attacks, refresh rotation and reuse, CSRF, lockout and rate limits."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives import serialization

from dealdesk.api.deps import ACCESS_COOKIE, CSRF_HEADER, REFRESH_COOKIE
from dealdesk.auth.tokens import KeyRing, TokenService
from dealdesk.domain.models import UserRole
from dealdesk.ports.repositories import AuditQuery
from tests.integration.api.conftest import ORIGIN, Api

pytestmark = pytest.mark.integration


def user_id(api: Api, role: UserRole) -> str:
    return next(str(u.id) for u in api.container.users.list_all() if u.email == api.emails[role])


def service(
    keys: KeyRing,
    *,
    audience: str = "dealdesk-api",
    issuer: str = "dealdesk-local",
    clock: Callable[[], datetime] | None = None,
) -> TokenService:
    return TokenService(
        keys,
        issuer=issuer,
        audience=audience,
        ttl_seconds=900,
        clock=clock or (lambda: datetime.now(UTC)),
    )


def attack(api: Api, token: str) -> int:
    client = api.client()
    client.cookies.set(ACCESS_COOKIE, token)
    return client.get("/v1/auth/me").status_code


def test_valid_token_is_accepted(api: Api) -> None:
    token, _ = service(api.keys).issue(uuid.UUID(user_id(api, UserRole.VIEWER)), UserRole.VIEWER)
    assert attack(api, token) == 200


@pytest.mark.parametrize(
    "forge",
    [
        "expired",
        "tampered",
        "wrong_audience",
        "wrong_issuer",
        "unsigned",
        "hs256_confusion",
        "unknown_key",
        "garbage",
    ],
)
def test_forged_tokens_are_rejected(api: Api, forge: str) -> None:
    subject = uuid.UUID(user_id(api, UserRole.VIEWER))
    good, _ = service(api.keys).issue(subject, UserRole.ADMIN)
    now = int(datetime.now(UTC).timestamp())
    claims = {
        "iss": "dealdesk-local",
        "aud": "dealdesk-api",
        "sub": str(subject),
        "iat": now,
        "exp": now + 600,
        "jti": "x",
        "role": "admin",
    }
    public_pem = (
        api.keys.private_keys[api.keys.active_kid]
        .public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    )
    tokens = {
        "expired": service(api.keys, clock=lambda: datetime.now(UTC) - timedelta(hours=1)).issue(
            subject, UserRole.VIEWER
        )[0],
        "tampered": _tamper(good),
        "wrong_audience": service(api.keys, audience="someone-else").issue(
            subject, UserRole.VIEWER
        )[0],
        "wrong_issuer": service(api.keys, issuer="evil").issue(subject, UserRole.VIEWER)[0],
        "unsigned": jwt.encode(
            claims, None, algorithm="none", headers={"kid": api.keys.active_kid}
        ),
        "hs256_confusion": _hs256(claims, public_pem, api.keys.active_kid),
        "unknown_key": service(KeyRing.generate()).issue(subject, UserRole.VIEWER)[0],
        "garbage": "not.a.jwt",
    }
    assert attack(api, tokens[forge]) == 401


def _tamper(token: str) -> str:
    header, payload, signature = token.split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    claims["role"] = "admin"
    claims["sub"] = "00000000-0000-0000-0000-000000000000"
    forged = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"{header}.{forged}.{signature}"


def _hs256(claims: dict[str, object], secret: bytes, kid: str) -> str:
    header = {"alg": "HS256", "typ": "JWT", "kid": kid}

    def encode(part: object) -> str:
        return base64.urlsafe_b64encode(json.dumps(part).encode()).rstrip(b"=").decode()

    signing_input = f"{encode(header)}.{encode(claims)}".encode()
    signature = (
        base64.urlsafe_b64encode(hmac.new(secret, signing_input, hashlib.sha256).digest())
        .rstrip(b"=")
        .decode()
    )
    return f"{signing_input.decode()}.{signature}"


def test_token_role_claim_is_not_trusted_over_the_database(api: Api) -> None:
    viewer = uuid.UUID(user_id(api, UserRole.VIEWER))
    token, _ = service(api.keys).issue(viewer, UserRole.ADMIN)  # validly signed but claims admin
    client = api.client()
    client.cookies.set(ACCESS_COOKIE, token)
    assert client.get("/v1/auth/me").json()["role"] == "viewer"
    assert client.get("/v1/admin/users").status_code == 403


def test_cookies_are_httponly_lax_and_narrow(api: Api) -> None:
    client = api.anonymous()
    response = client.post(
        "/v1/auth/login",
        json={
            "email": api.emails[UserRole.VIEWER],
            "password": api.passwords[api.emails[UserRole.VIEWER]],
        },
    )
    cookies = response.headers.get_list("set-cookie")
    access = next(c for c in cookies if c.startswith(f"{ACCESS_COOKIE}="))
    refresh = next(c for c in cookies if c.startswith(f"{REFRESH_COOKIE}="))
    assert "HttpOnly" in access and "SameSite=lax" in access and "Path=/" in access
    assert "HttpOnly" in refresh and "Path=/v1/auth" in refresh
    assert "token" not in response.json()  # tokens never appear in a body


def test_refresh_rotates_and_reuse_revokes_the_family(api: Api) -> None:
    client = api.as_role(UserRole.VIEWER)
    stolen = client.cookies.get(REFRESH_COOKIE)
    assert client.post("/v1/auth/refresh").status_code == 200
    rotated = client.cookies.get(REFRESH_COOKIE)
    assert rotated and rotated != stolen

    attacker = api.anonymous()
    attacker.cookies.set(REFRESH_COOKIE, stolen, path="/v1/auth")
    assert attacker.post("/v1/auth/refresh").status_code == 401  # reuse detected
    assert client.post("/v1/auth/refresh").status_code == 401  # the whole family is revoked
    events, _ = api.container.audit.query(AuditQuery(action="auth.refresh_token_reuse"))
    revoked = sorted(e.event.details["revoked"] for e in events)
    assert revoked == [
        "0",
        "1",
    ]  # the attacker's replay revoked the family; the victim's next try logs too


def test_logout_revokes_on_the_server(api: Api) -> None:
    client = api.as_role(UserRole.VIEWER)
    refresh_token = client.cookies.get(REFRESH_COOKIE)
    assert client.post("/v1/auth/logout").status_code == 204
    replay = api.anonymous()
    replay.cookies.set(REFRESH_COOKIE, refresh_token, path="/v1/auth")
    assert replay.post("/v1/auth/refresh").status_code == 401
    assert api.anonymous().post("/v1/auth/refresh").status_code == 401  # no cookie at all


@pytest.mark.parametrize(
    "variant", ["no_header", "wrong_header", "no_cookie", "bad_origin", "no_origin"]
)
def test_csrf_failures(api: Api, variant: str) -> None:
    client = api.as_role(UserRole.ESTIMATOR)
    if variant == "no_header":
        del client.headers[CSRF_HEADER]
    elif variant == "wrong_header":
        client.headers[CSRF_HEADER] = "forged"
    elif variant == "no_cookie":
        client.cookies.delete("dd_csrf")
    elif variant == "bad_origin":
        client.headers["Origin"] = "https://evil.example"
    else:
        del client.headers["Origin"]
    response = client.post("/v1/runs", data={"sample_id": "clean_brief"})
    assert response.status_code == 403
    assert response.json()["title"] == "CSRF check failed"


def test_referer_is_accepted_when_origin_is_absent(api: Api) -> None:
    client = api.as_role(UserRole.VIEWER)
    del client.headers["Origin"]
    client.headers["Referer"] = f"{ORIGIN}/runs"
    assert (
        client.post(
            "/v1/impact/calculate", json=client.get("/v1/impact").json()["assumptions"]
        ).status_code
        == 200
    )


def test_unknown_user_and_wrong_password_look_identical(api: Api) -> None:
    client = api.anonymous()
    unknown = client.post(
        "/v1/auth/login", json={"email": "nobody@test.example", "password": "whatever-123456"}
    )
    wrong = client.post(
        "/v1/auth/login",
        json={"email": api.emails[UserRole.VIEWER], "password": "wrong-password-1"},
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_lockout_after_repeated_failures(api: Api) -> None:
    email = api.emails[UserRole.VIEWER]
    client = api.anonymous()
    for _ in range(3):
        assert (
            client.post(
                "/v1/auth/login", json={"email": email, "password": "wrong-password-1"}
            ).status_code
            == 401
        )
    locked = client.post("/v1/auth/login", json={"email": email, "password": api.passwords[email]})
    assert locked.status_code == 401  # correct password, but locked
    events, total = api.container.audit.query(AuditQuery(action="auth.login_failed", limit=10))
    assert total == 4
    assert events[0].event.details["reason"] == "locked"
    user = api.container.users.get_by_email(email)
    assert user is not None and user.locked_until is not None


def test_inactive_users_cannot_sign_in(api: Api) -> None:
    email = api.emails[UserRole.VIEWER]
    user = api.container.users.get_by_email(email)
    assert user is not None
    api.container.users.update(user.id, is_active=False)
    response = api.anonymous().post(
        "/v1/auth/login", json={"email": email, "password": api.passwords[email]}
    )
    assert response.status_code == 401


def test_sign_in_is_rate_limited_per_account(make_api: Callable[..., Api]) -> None:
    api = make_api(login_rate_limit_per_account_per_minute=2)
    client = api.anonymous()
    email = api.emails[UserRole.VIEWER]
    for _ in range(2):
        client.post("/v1/auth/login", json={"email": email, "password": "wrong-password-1"})
    limited = client.post("/v1/auth/login", json={"email": email, "password": api.passwords[email]})
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) >= 1


def test_api_is_rate_limited_per_client(make_api: Callable[..., Api]) -> None:
    api = make_api(api_rate_limit_per_minute=5)
    client = api.client()
    statuses = [client.get("/v1/auth/csrf").status_code for _ in range(7)]
    assert statuses[:5] == [200] * 5
    assert statuses[5:] == [429, 429]
    assert client.get("/healthz").status_code == 200  # probes are never limited
