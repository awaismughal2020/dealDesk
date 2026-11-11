"""Application settings, loaded from the environment and validated at startup (fail fast)."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from functools import cached_property
from typing import Annotated, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from dealdesk.domain.models import CostingPolicy, InvoicePolicy


class AppEnv(StrEnum):
    """Deployment environment."""

    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class AuthMode(StrEnum):
    """Where access tokens come from."""

    LOCAL = "local"
    OIDC = "oidc"


class LLMProvider(StrEnum):
    """Supported language-model providers."""

    FAKE = "fake"
    VERTEX = "vertex"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class EmbeddingProvider(StrEnum):
    """Supported embedding providers."""

    FAKE = "fake"
    VERTEX = "vertex"
    OPENAI = "openai"


def _split_csv(value: object) -> object:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return value


class Settings(BaseSettings):
    """All runtime configuration. Unknown keys are ignored; invalid values stop the process."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore", frozen=True)

    app_env: AppEnv = AppEnv.LOCAL
    log_level: str = "INFO"

    database_url: SecretStr = SecretStr("")
    db_pool_size: int = Field(default=10, ge=1, le=100)

    auth_mode: AuthMode = AuthMode.LOCAL
    jwt_issuer: str = "dealdesk-local"
    jwt_audience: str = "dealdesk-api"
    jwt_keys_dir: str = "/run/dealdesk-keys"
    access_token_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    refresh_token_ttl_seconds: int = Field(default=1_209_600, ge=3600)
    cookie_secure: bool = True
    allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    argon2_time_cost: int = Field(default=3, ge=2)
    argon2_memory_cost_kib: int = Field(default=65_536, ge=19_456)
    argon2_parallelism: int = Field(default=1, ge=1)
    login_rate_limit_per_ip_per_minute: int = Field(default=20, ge=1)
    login_rate_limit_per_account_per_minute: int = Field(default=10, ge=1)
    lockout_threshold: int = Field(default=5, ge=1)
    lockout_seconds: int = Field(default=900, ge=1)
    api_rate_limit_per_minute: int = Field(default=300, ge=1)

    oidc_issuer: str = ""
    oidc_audience: str = ""
    oidc_jwks_url: str = ""
    oidc_role_claim: str = "dealdesk_role"
    oidc_clock_skew_seconds: int = Field(default=30, ge=0, le=300)

    llm_provider: LLMProvider = LLMProvider.FAKE
    llm_model: str = "fake-deterministic-v1"
    llm_temperature: Decimal = Field(default=Decimal("0.1"), ge=0, le=1)
    llm_timeout_seconds: int = Field(default=60, ge=1)
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    llm_max_output_tokens: int = Field(default=4096, ge=256)
    llm_input_gbp_per_mtok: Decimal = Field(default=Decimal(0), ge=0)
    llm_output_gbp_per_mtok: Decimal = Field(default=Decimal(0), ge=0)
    embedding_provider: EmbeddingProvider = EmbeddingProvider.FAKE
    embedding_model: str = "fake-hashing-v1"
    # Fixed by the database schema (vector(256)); real providers are asked for 256 dimensions.
    embedding_dim: int = Field(default=256, ge=256, le=256)
    google_cloud_project: str = ""
    google_cloud_location: str = "europe-west2"
    anthropic_api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")

    contingency: Decimal = Field(default=Decimal("0.10"), ge=0, le=1)
    target_margin: Decimal = Field(default=Decimal("0.35"), ge=0, lt=1)
    minimum_margin: Decimal = Field(default=Decimal("0.25"), ge=0, lt=1)
    max_hours_per_role: Decimal = Field(default=Decimal(2000), gt=0)
    max_revisions: int = Field(default=2, ge=0, le=2)
    vat_rate: Decimal = Field(default=Decimal("0.20"), ge=0, lt=1)
    invoice_milestone_percentages: Annotated[list[Decimal], NoDecode] = Field(
        default_factory=lambda: [Decimal(30), Decimal(40), Decimal(30)]
    )
    invoice_milestone_offset_days: Annotated[list[int], NoDecode] = Field(
        default_factory=lambda: [0, 42, 84]
    )
    project_weeks: int = Field(default=12, ge=1, le=104)
    start_date_lead_days: int = Field(default=14, ge=0)
    retrieval_top_k: int = Field(default=3, ge=1, le=10)

    upload_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)
    workflow_max_workers: int = Field(default=4, ge=1, le=32)

    @field_validator(
        "allowed_origins",
        "invoice_milestone_percentages",
        "invoice_milestone_offset_days",
        mode="before",
    )
    @classmethod
    def _csv(cls, value: object) -> object:
        return _split_csv(value)

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        if self.app_env is not AppEnv.LOCAL and not self.cookie_secure:
            msg = "COOKIE_SECURE=false is only allowed when APP_ENV=local"
            raise ValueError(msg)
        if self.minimum_margin > self.target_margin:
            msg = "MINIMUM_MARGIN must not exceed TARGET_MARGIN"
            raise ValueError(msg)
        if len(self.invoice_milestone_percentages) != len(self.invoice_milestone_offset_days):
            msg = "INVOICE_MILESTONE_PERCENTAGES and _OFFSET_DAYS must have the same length"
            raise ValueError(msg)
        self._check_providers()
        return self

    def _check_providers(self) -> None:
        if self.auth_mode is AuthMode.OIDC and not (
            self.oidc_issuer and self.oidc_audience and self.oidc_jwks_url
        ):
            msg = "AUTH_MODE=oidc requires OIDC_ISSUER, OIDC_AUDIENCE and OIDC_JWKS_URL"
            raise ValueError(msg)
        if self.llm_provider is LLMProvider.ANTHROPIC and not self.anthropic_api_key:
            msg = "LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY"
            raise ValueError(msg)
        if LLMProvider.OPENAI in (self.llm_provider, self.embedding_provider) and not (
            self.openai_api_key.get_secret_value()
        ):
            msg = "OpenAI provider requires OPENAI_API_KEY"
            raise ValueError(msg)
        uses_vertex = LLMProvider.VERTEX in (self.llm_provider, self.embedding_provider)
        if uses_vertex and not self.google_cloud_project:
            msg = "Vertex provider requires GOOGLE_CLOUD_PROJECT"
            raise ValueError(msg)

    @cached_property
    def costing_policy(self) -> CostingPolicy:
        """Commercial policy as a domain value object."""
        return CostingPolicy(
            contingency=self.contingency,
            target_margin=self.target_margin,
            minimum_margin=self.minimum_margin,
            max_hours_per_role=self.max_hours_per_role,
        )

    @cached_property
    def invoice_policy(self) -> InvoicePolicy:
        """Invoice milestone policy as a domain value object."""
        return InvoicePolicy(
            percentages=tuple(self.invoice_milestone_percentages),
            offset_days=tuple(self.invoice_milestone_offset_days),
            vat_rate=self.vat_rate,
        )

    @property
    def is_local(self) -> bool:
        """True when running on a developer machine."""
        return self.app_env is AppEnv.LOCAL


def load_settings() -> Settings:
    """Read settings from the process environment. Raises on any invalid value."""
    return Settings()
