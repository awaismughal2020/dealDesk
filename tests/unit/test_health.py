from fastapi.testclient import TestClient

from dealdesk.api.app import create_app
from dealdesk.config import Settings


def test_healthz_is_ok() -> None:
    client = TestClient(create_app(Settings(cookie_secure=False)))
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_insecure_cookies_rejected_outside_local() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        Settings(app_env="production", cookie_secure=False)  # type: ignore[arg-type]
