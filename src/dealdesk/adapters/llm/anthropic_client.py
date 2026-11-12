"""Anthropic Messages API adapter. Opt-in only: LLM_PROVIDER=anthropic.

Structured output via `messages.parse(output_format=...)`. The installed SDK (2.x) does not take a
sampling temperature on this call, so none is sent; determinism comes from the strict schema and
code-side validation.
"""

from __future__ import annotations

from typing import Any

import anthropic
from pydantic import BaseModel

from dealdesk.adapters.llm.base import RawCompletion, TransientLLMError
from dealdesk.ports.llm import PromptSpec

TRANSIENT = (
    anthropic.APITimeoutError,
    anthropic.APIConnectionError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)


class AnthropicModelClient:
    """Implements `ModelClient`."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: int,
        max_output_tokens: int,
        client: Any = None,
    ) -> None:
        self._client = client or anthropic.Anthropic(
            api_key=api_key, timeout=timeout_seconds, max_retries=0
        )
        self._model = model
        self._max_output_tokens = max_output_tokens

    @property
    def provider(self) -> str:
        """Provider name."""
        return "anthropic"

    @property
    def model(self) -> str:
        """Model name from configuration."""
        return self._model

    def complete(self, prompt: PromptSpec, schema: type[BaseModel]) -> RawCompletion:
        """Call `messages.parse` and return the parsed output as JSON text."""
        try:
            message = self._client.messages.parse(
                model=self._model,
                max_tokens=self._max_output_tokens,
                system=prompt.system,
                messages=[{"role": "user", "content": prompt.user}],
                output_format=schema,
            )
        except TRANSIENT as exc:
            raise TransientLLMError(type(exc).__name__) from exc
        parsed = message.parsed_output
        text = parsed.model_dump_json() if parsed is not None else _text_blocks(message)
        return RawCompletion(text, message.usage.input_tokens, message.usage.output_tokens)


def _text_blocks(message: Any) -> str:
    return "".join(getattr(block, "text", "") for block in message.content)
