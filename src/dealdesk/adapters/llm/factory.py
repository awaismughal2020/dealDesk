"""Select the language-model adapter from configuration. Provider SDKs load only when chosen."""

from __future__ import annotations

from pathlib import Path

from dealdesk.adapters.llm.base import ModelClient, StructuredLLM
from dealdesk.adapters.llm.fake import FakeModelClient
from dealdesk.config import LLMProvider, Settings


def build_model_client(settings: Settings, fixtures_dir: Path | None = None) -> ModelClient:
    """Return the raw client for the configured provider."""
    temperature = float(settings.llm_temperature)
    if settings.llm_provider is LLMProvider.VERTEX:
        from dealdesk.adapters.llm.vertex import VertexModelClient  # noqa: PLC0415

        return VertexModelClient(
            project=settings.google_cloud_project,
            location=settings.google_cloud_location,
            model=settings.llm_model,
            temperature=temperature,
            timeout_seconds=settings.llm_timeout_seconds,
            max_output_tokens=settings.llm_max_output_tokens,
        )
    if settings.llm_provider is LLMProvider.ANTHROPIC:
        from dealdesk.adapters.llm.anthropic_client import AnthropicModelClient  # noqa: PLC0415

        return AnthropicModelClient(
            api_key=settings.anthropic_api_key.get_secret_value(),
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
            max_output_tokens=settings.llm_max_output_tokens,
        )
    if settings.llm_provider is LLMProvider.OPENAI:
        from dealdesk.adapters.llm.openai_client import OpenAIModelClient  # noqa: PLC0415

        return OpenAIModelClient(
            api_key=settings.openai_api_key.get_secret_value(),
            model=settings.llm_model,
            temperature=temperature,
            timeout_seconds=settings.llm_timeout_seconds,
            max_output_tokens=settings.llm_max_output_tokens,
        )
    return FakeModelClient(model=settings.llm_model, fixtures_dir=fixtures_dir)


def build_llm(settings: Settings, fixtures_dir: Path | None = None) -> StructuredLLM:
    """Return the configured `LLMPort` with retries and validation."""
    return StructuredLLM(
        build_model_client(settings, fixtures_dir), max_retries=settings.llm_max_retries
    )
