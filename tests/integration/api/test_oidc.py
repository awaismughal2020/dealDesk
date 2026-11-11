"""OIDC mode with a mocked JWKS: issuer, audience, signature, expiry, skew and role mapping."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from dealdesk.api.deps import ACCESS_COOKIE
from dealdesk.auth.oidc import JwksCache, OidcAuthenticator
from tests.integration.api.conftest import Api

pytestmark = pytest.mark.integration
ISSUER = "https://idp.test.example/realms/dealdesk"
AUDIENCE = "dealdesk-api"


class Idp:
    def __init__(self) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = "idp-key-1"
        self.fetches = 0

    def jwks(self) -> dict[str, Any]:
        self.fetches += 1
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key(), as_dict=True)
        return {"keys": [{**jwk, "kid": self.kid, "alg": "RS256", "use": "sig"}]}

    def token(self, **overrides: Any) -> str:
        now = datetime.now(UTC)
        claims: dict[str, Any] = {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": "idp-user-1",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "email": "oidc.user@idp.test.example",
            "name": "OIDC User",
            "dealdesk_role": ["offline_access", "dealdesk:approver"],
        }
        kid = overrides.pop("kid", self.kid)
        key = overrides.pop("key", self.key)
        claims.update(overrides)
        claims = {k: v for k, v in claims.items() if v is not None}
        return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


@pytest.fixture
def oidc(make_api: Callable[..., Api]) -> tuple[Api, Idp]:
    idp = Idp()
    api = make_api(
        auth_mode="oidc",
        oidc_issuer=ISSUER,
        oidc_audience=AUDIENCE,
        oidc_jwks_url="https://idp.test.example/jwks",
    )
    api.container.authenticator = OidcAuthenticator(
        jwks=JwksCache(idp.jwks),
        issuer=ISSUER,
        audience=AUDIENCE,
        role_claim="dealdesk_role",
        leeway_seconds=30,
        users=api.container.users,
    )
    return api, idp


def me(api: Api, token: str) -> Any:
    client = api.client()
    client.cookies.set(ACCESS_COOKIE, token)
    return client.get("/v1/auth/me")


def test_valid_provider_token_provisions_and_maps_role(oidc: tuple[Api, Idp]) -> None:
    api, idp = oidc
    response = me(api, idp.token())
    assert response.status_code == 200
    body = response.json()
    assert (body["role"], body["auth_mode"], body["email"]) == (
        "approver",
        "oidc",
        "oidc.user@idp.test.example",
    )
    assert (
        me(api, idp.token(dealdesk_role="viewer")).json()["role"] == "viewer"
    )  # IdP is the source of truth
    assert idp.fetches == 1  # JWKS cached


@pytest.mark.parametrize(
    "override",
    [
        {"iss": "https://evil.example"},
        {"aud": "another-api"},
        {"exp": int((datetime.now(UTC) - timedelta(minutes=5)).timestamp())},
        {"dealdesk_role": None},
        {"dealdesk_role": ["unrelated-group"]},
        {"sub": None},
        {"kid": "unknown-kid"},
        {"key": rsa.generate_private_key(public_exponent=65537, key_size=2048)},
    ],
    ids=[
        "issuer",
        "audience",
        "expired",
        "no-role",
        "unmapped-role",
        "no-subject",
        "unknown-kid",
        "wrong-key",
    ],
)
def test_bad_provider_tokens_are_rejected(oidc: tuple[Api, Idp], override: dict[str, Any]) -> None:
    api, idp = oidc
    assert me(api, idp.token(**override)).status_code == 401


def test_clock_skew_is_tolerated_within_leeway(oidc: tuple[Api, Idp]) -> None:
    api, idp = oidc
    just_expired = int((datetime.now(UTC) - timedelta(seconds=10)).timestamp())
    assert me(api, idp.token(exp=just_expired)).status_code == 200


def test_disallowed_algorithm_is_rejected(oidc: tuple[Api, Idp]) -> None:
    api, _ = oidc
    token = jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "sub": "x", "exp": 9_999_999_999, "iat": 1},
        "an-attacker-chosen-32-byte-secret!!",
        algorithm="HS256",
        headers={"kid": "idp-key-1"},
    )
    assert me(api, token).status_code == 401


def test_local_sign_in_is_disabled_in_oidc_mode(oidc: tuple[Api, Idp]) -> None:
    api, _ = oidc
    client = api.anonymous()
    assert (
        client.post("/v1/auth/login", json={"email": "a@b.example", "password": "x"}).status_code
        == 404
    )
    assert client.post("/v1/auth/refresh").status_code == 404


def test_deactivated_oidc_user_is_refused(oidc: tuple[Api, Idp]) -> None:
    api, idp = oidc
    assert me(api, idp.token()).status_code == 200
    user = api.container.users.get_by_subject("idp-user-1")
    assert user is not None
    api.container.users.update(user.id, is_active=False)
    assert me(api, idp.token()).status_code == 401
