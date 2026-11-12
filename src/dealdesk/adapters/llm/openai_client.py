"""OpenAI Responses API adapter. Opt-in only: LLM_PROVIDER=openai."""

from __future__ import annotations

from typing import Any

import openai
from pydantic import BaseModel

from dealdesk.adapters.llm.base import RawCompletion, TransientLLMError
from dealdesk.ports.llm import PromptSpec

TRANSIENT = (
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.RateLimitError,
    openai.InternalServerError,
)


class OpenAIModelClient:
    """Implements `ModelClient` with `responses.parse(text_format=...)`."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        temperature: float,
        timeout_seconds: int,
        max_output_tokens: int,
        client: Any = None,
    ) -> None:
        self._client = client or openai.OpenAI(
            api_key=api_key, timeout=timeout_seconds, max_retries=0
        )
        self._model = model
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens

    @property
    def provider(self) -> str:
        """Provider name."""
        return "openai"

    @property
    def model(self) -> str:
        """Model name from configuration."""
        return self._model

    def complete(self, prompt: PromptSpec, schema: type[BaseModel]) -> RawCompletion:
        """Call `responses.parse` and return the parsed output as JSON text."""
        try:
            response = self._client.responses.parse(
                model=self._model,
                instructions=prompt.system,
                input=prompt.user,
                text_format=schema,
                temperature=self._temperature,
                max_output_tokens=self._max_output_tokens,
            )
        except TRANSIENT as exc:
            raise TransientLLMError(type(exc).__name__) from exc
        parsed = response.output_parsed
        usage = response.usage
        return RawCompletion(
            text=parsed.model_dump_json() if parsed is not None else (response.output_text or ""),
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
        )
