import uuid
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ec import SECP256R1, generate_private_key

from dealdesk.auth.csrf import new_csrf_token, origin_allowed, tokens_match
from dealdesk.auth.oidc import map_role
from dealdesk.auth.policy import ROLE_PERMISSIONS, Permission, has_permission, permissions_for
from dealdesk.auth.ratelimit import SlidingWindowLimiter
from dealdesk.auth.tokens import InvalidTokenError, KeyConfigurationError, KeyRing, TokenService
from dealdesk.domain.models import UserRole
from scripts import init as init_script


def write_key(directory: Path, kid: str) -> None:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    pem = Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    (directory / f"{kid}.pem").write_bytes(pem)


def test_key_rotation_keeps_old_tokens_valid(tmp_path: Path) -> None:
    write_key(tmp_path, "old")
    (tmp_path / "active_kid").write_text("old\n")
    old_service = TokenService(KeyRing.load(tmp_path), issuer="i", audience="a", ttl_seconds=60)
    old_token, _ = old_service.issue(uuid.uuid4(), UserRole.VIEWER)

    write_key(tmp_path, "new")
    (tmp_path / "active_kid").write_text("new\n")
    rotated = TokenService(KeyRing.load(tmp_path), issuer="i", audience="a", ttl_seconds=60)
    new_token, _ = rotated.issue(uuid.uuid4(), UserRole.VIEWER)
    assert jwt.get_unverified_header(new_token)["kid"] == "new"
    assert rotated.verify(old_token).role == "viewer"
    assert {k["kid"] for k in rotated.jwks()["keys"]} == {"old", "new"}
    assert all(k["alg"] == "EdDSA" and "d" not in k for k in rotated.jwks()["keys"])


def test_key_ring_errors(tmp_path: Path) -> None:
    with pytest.raises(KeyConfigurationError, match="make init"):
        KeyRing.load(tmp_path)
    (tmp_path / "active_kid").write_text("missing")
    with pytest.raises(KeyConfigurationError, match="not found"):
        KeyRing.load(tmp_path)
    pem = generate_private_key(SECP256R1()).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    (tmp_path / "ec.pem").write_bytes(pem)
    with pytest.raises(KeyConfigurationError, match="Ed25519"):
        KeyRing.load(tmp_path)


def test_token_with_wrong_algorithm_header_is_rejected() -> None:
    service = TokenService(KeyRing.generate(), issuer="i", audience="a", ttl_seconds=60)
    with pytest.raises(InvalidTokenError):
        service.verify(jwt.encode({"sub": "x"}, "k" * 32, algorithm="HS256"))


def test_init_script_generates_secrets_and_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    example = tmp_path / ".env.example"
    example.write_text(
        "APP_ENV=local\nPOSTGRES_PASSWORD=\nDEMO_ADMIN_PASSWORD=\nDEMO_VIEWER_PASSWORD=kept-value-123\n"
    )
    monkeypatch.setattr(init_script, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(init_script, "ENV_EXAMPLE", example)
    monkeypatch.setattr(init_script, "KEYS_DIR", tmp_path / "keys")
    created = init_script.ensure_env()
    assert set(created) == {"POSTGRES_PASSWORD", "DEMO_ADMIN_PASSWORD"}
    assert "DEMO_VIEWER_PASSWORD=kept-value-123" in (tmp_path / ".env").read_text()
    assert init_script.ensure_env() == {}  # idempotent
    kids = [init_script.generate_key() for _ in range(3)]
    assert len(list((tmp_path / "keys").glob("*.pem"))) == 2  # current and previous only
    assert KeyRing.load(tmp_path / "keys").active_kid == kids[-1]


def test_policy_matrix_is_deny_by_default() -> None:
    assert has_permission(UserRole.ESTIMATOR, Permission.RUN_CREATE)
    assert not has_permission(UserRole.APPROVER, Permission.RUN_CREATE)
    assert not has_permission(UserRole.ADMIN, Permission.RUN_DECIDE)
    assert not has_permission(UserRole.VIEWER, Permission.AUDIT_READ)
    assert set(ROLE_PERMISSIONS) == set(UserRole)
    assert "user:manage" in permissions_for(UserRole.ADMIN)


def test_rate_limiter_window_slides() -> None:
    now = [0.0]
    limiter = SlidingWindowLimiter(2, window=10, clock=lambda: now[0])
    assert limiter.hit("k") is None
    assert limiter.hit("k") is None
    assert limiter.hit("k") == 10
    now[0] = 10.5
    assert limiter.hit("k") is None
    assert limiter.hit("other") is None


def test_csrf_helpers() -> None:
    token = new_csrf_token()
    assert tokens_match(token, token)
    assert not tokens_match(token, token + "x")
    assert not tokens_match(None, token)
    allowed = ["http://localhost:3000"]
    assert origin_allowed("http://localhost:3000/", None, allowed)
    assert not origin_allowed("http://localhost:3000.evil.example", None, allowed)
    assert origin_allowed(None, "http://localhost:3000/runs/1", allowed)
    assert not origin_allowed(None, "http://localhost:30001/x", allowed)
    assert not origin_allowed(None, None, allowed)


@pytest.mark.parametrize(
    ("claim", "role"),
    [
        ("approver", UserRole.APPROVER),
        (["dealdesk:viewer", "dealdesk:admin"], UserRole.ADMIN),
        (["Estimator"], UserRole.ESTIMATOR),
        (["other"], None),
        (None, None),
        (42, None),
    ],
)
def test_oidc_role_mapping(claim: object, role: UserRole | None) -> None:
    assert map_role(claim) is role
