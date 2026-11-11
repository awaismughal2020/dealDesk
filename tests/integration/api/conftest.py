"""API test harness: the real app and database, inline workflow execution, in-memory keys."""

from __future__ import annotations

import secrets
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from dealdesk.adapters.db.session import SessionFactory
from dealdesk.api.app import create_app
from dealdesk.api.container import Container, build_container
from dealdesk.api.deps import CSRF_HEADER
from dealdesk.auth.passwords import Argon2Params, PasswordHasher
from dealdesk.auth.tokens import KeyRing
from dealdesk.config import Settings
from dealdesk.domain.models import UserRole

ORIGIN = "http://testserver"
FAST_ARGON = Argon2Params(time_cost=2, memory_cost_kib=19456, parallelism=1)
ROLES = (UserRole.VIEWER, UserRole.ESTIMATOR, UserRole.APPROVER, UserRole.ADMIN)


class InlineExecutor:
    def submit(self, fn: Callable[[], None], /) -> None:
        fn()


def test_settings(database_url: str, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "local",
        "cookie_secure": False,
        "database_url": SecretStr(database_url),
        "allowed_origins": ORIGIN,
        "argon2_time_cost": FAST_ARGON.time_cost,
        "argon2_memory_cost_kib": FAST_ARGON.memory_cost_kib,
        "api_rate_limit_per_minute": 100_000,
        "login_rate_limit_per_ip_per_minute": 1000,
        "login_rate_limit_per_account_per_minute": 1000,
        "lockout_threshold": 3,
        "lockout_seconds": 60,
        "upload_max_bytes": 64 * 1024,
        "log_level": "WARNING",
    }
    values.update(overrides)
    return Settings(**values)


@dataclass
class Api:
    app: FastAPI
    container: Container
    keys: KeyRing
    passwords: dict[str, str]
    emails: dict[UserRole, str]

    def client(self) -> TestClient:
        client = TestClient(self.app, base_url=ORIGIN)
        client.headers["Origin"] = ORIGIN
        return client

    def anonymous(self) -> TestClient:
        client = self.client()
        token = client.get("/v1/auth/csrf").json()["csrf_token"]
        client.headers[CSRF_HEADER] = token
        return client

    def login(self, email: str, password: str | None = None) -> TestClient:
        client = self.anonymous()
        response = client.post(
            "/v1/auth/login", json={"email": email, "password": password or self.passwords[email]}
        )
        assert response.status_code == 200, response.text
        return client

    def as_role(self, role: UserRole) -> TestClient:
        return self.login(self.emails[role])

    def add_user(self, role: UserRole, email: str | None = None) -> tuple[str, str]:
        email = email or f"{role.value}-{secrets.token_hex(4)}@test.example"
        password = f"pw-{secrets.token_urlsafe(12)}"
        self.container.users.create(
            email=email,
            display_name=f"Test {role.value}",
            role=role,
            password_hash=PasswordHasher(FAST_ARGON).hash(password),
        )
        self.passwords[email] = password
        return email, password


@pytest.fixture
def make_api(sessions: SessionFactory, database_url: str) -> Iterator[Callable[..., Api]]:
    managers: list[TestClient] = []

    def build(**overrides: Any) -> Api:
        settings = test_settings(database_url, **overrides)
        keys = KeyRing.generate()
        holder: dict[str, Container] = {}

        def factory(s: Settings) -> Container:
            holder["c"] = build_container(s, executor=InlineExecutor(), keys=keys)
            return holder["c"]

        app = create_app(settings, container_factory=factory, recover_on_start=False)
        manager = TestClient(app, base_url=ORIGIN)
        manager.__enter__()
        managers.append(manager)
        api = Api(app, holder["c"], keys, {}, {})
        for role in ROLES:
            email, _ = api.add_user(role)
            api.emails[role] = email
        return api

    yield build
    for manager in managers:
        manager.__exit__(None, None, None)


@pytest.fixture
def api(make_api: Callable[..., Api]) -> Api:
    return make_api()


def start_sample_run(client: TestClient, sample: str = "clean_brief") -> dict[str, Any]:
    response = client.post("/v1/runs", data={"sample_id": sample})
    assert response.status_code == 202, response.text
    body: dict[str, Any] = response.json()
    return body
