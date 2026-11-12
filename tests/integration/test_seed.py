from __future__ import annotations

import pytest
from pydantic import SecretStr
from sqlalchemy import Engine, func, select

from dealdesk.adapters.db.models import (
    CaseStudyRow,
    PastProjectRow,
    RateCardRow,
    TeamMemberRow,
    UserRow,
)
from dealdesk.adapters.db.session import SessionFactory
from dealdesk.config import Settings
from scripts import seed

pytestmark = pytest.mark.integration
ROLES = ("ADMIN", "ESTIMATOR", "APPROVER", "VIEWER")


def _settings(url: str, env: str = "local") -> Settings:
    return Settings(  # type: ignore[call-arg]
        app_env=env,
        cookie_secure=env != "local",
        database_url=SecretStr(url),
        argon2_time_cost=2,
        argon2_memory_cost_kib=19456,
    )


def _counts(engine: Engine) -> tuple[int, ...]:
    with engine.connect() as connection:
        return tuple(
            connection.scalar(select(func.count()).select_from(model)) or 0
            for model in (RateCardRow, TeamMemberRow, PastProjectRow, CaseStudyRow, UserRow)
        )


def test_seed_is_idempotent(
    sessions: SessionFactory, engine: Engine, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    for index, role in enumerate(ROLES):
        monkeypatch.setenv(f"DEMO_{role}_EMAIL", f"{role.lower()}@seed.example")
        monkeypatch.setenv(f"DEMO_{role}_PASSWORD", f"generated-{index}-Xk29fQwZ")
    seed.main(_settings(database_url))
    first = _counts(engine)
    seed.main(_settings(database_url))
    assert _counts(engine) == first == (8, 10, 5, 5, 4)

    monkeypatch.setenv("DEMO_ADMIN_PASSWORD", "rotated-password-Pz81mW")
    seed.main(_settings(database_url))  # a changed .env password takes effect
    assert _counts(engine) == first


def test_seed_refuses_outside_local(database_url: str) -> None:
    with pytest.raises(SystemExit) as caught:
        seed.main(_settings(database_url, env="staging"))
    assert caught.value.code == 1


def test_seed_requires_demo_credentials(
    sessions: SessionFactory, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    for role in ROLES:
        monkeypatch.delenv(f"DEMO_{role}_PASSWORD", raising=False)
    with pytest.raises(SystemExit) as caught:
        seed.main(_settings(database_url))
    assert caught.value.code == 2
