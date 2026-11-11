import pytest
from pydantic import ValidationError

from dealdesk.config import Settings


def make(**kwargs: object) -> Settings:
    return Settings(cookie_secure=False, **kwargs)  # type: ignore[arg-type]


def test_defaults_are_offline_and_local() -> None:
    settings = make()
    assert settings.llm_provider == "fake"
    assert settings.auth_mode == "local"
    assert settings.is_local


def test_csv_lists_are_parsed() -> None:
    settings = make(
        allowed_origins="http://a.test, http://b.test",
        invoice_milestone_percentages="50,50",
        invoice_milestone_offset_days="0,30",
    )
    assert settings.allowed_origins == ["http://a.test", "http://b.test"]
    assert [str(p) for p in settings.invoice_milestone_percentages] == ["50", "50"]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"minimum_margin": "0.5", "target_margin": "0.3"}, "MINIMUM_MARGIN"),
        (
            {"invoice_milestone_percentages": "100", "invoice_milestone_offset_days": "0,1"},
            "same length",
        ),
        ({"auth_mode": "oidc"}, "OIDC_ISSUER"),
        ({"llm_provider": "anthropic"}, "ANTHROPIC_API_KEY"),
        ({"llm_provider": "openai"}, "OPENAI_API_KEY"),
        ({"embedding_provider": "openai"}, "OPENAI_API_KEY"),
        ({"llm_provider": "vertex"}, "GOOGLE_CLOUD_PROJECT"),
    ],
)
def test_invalid_combinations_fail_fast(overrides: dict[str, str], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        make(**overrides)


def test_secure_cookies_allowed_in_production() -> None:
    settings = Settings(app_env="production", cookie_secure=True)  # type: ignore[arg-type]
    assert not settings.is_local
