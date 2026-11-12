"""Provider-independent structured generation: timeouts, bounded retries, validation, usage.

Provider adapters implement `ModelClient` (one raw call). `StructuredLLM` wraps any client and
implements `LLMPort`: it retries transient failures with exponential backoff, re-asks once per
attempt budget when the JSON does not validate, and sums token usage across attempts.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ValidationError

from dealdesk.observability import get_logger
from dealdesk.ports.llm import LLMError, LLMResult, LLMUsage, PromptSpec

log = get_logger("llm")
BACKOFF_BASE_SECONDS = 0.5
BACKOFF_CAP_SECONDS = 8.0


class TransientLLMError(Exception):
    """A retryable provider failure (timeout, rate limit, 5xx, connection error)."""


@dataclass(frozen=True, slots=True)
class RawCompletion:
    """What a provider returned for one call."""

    text: str
    input_tokens: int
    output_tokens: int


class ModelClient(Protocol):
    """One provider call that returns JSON text intended to match `schema`."""

    @property
    def provider(self) -> str:
        """Provider name for the audit log."""

    @property
    def model(self) -> str:
        """Model name (from configuration, never hard-coded)."""

    def complete(self, prompt: PromptSpec, schema: type[BaseModel]) -> RawCompletion:
        """Make one call. Raise `TransientLLMError` for retryable failures."""


class StructuredLLM:
    """Implements `LLMPort` over a `ModelClient`."""

    def __init__(
        self,
        client: ModelClient,
        *,
        max_retries: int,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._max_attempts = max_retries + 1
        self._sleep = sleep
        self._clock = clock

    def generate[T: BaseModel](self, prompt: PromptSpec, schema: type[T]) -> LLMResult[T]:
        """Return a validated output or raise `LLMError` after the retry budget is spent."""
        started = self._clock()
        input_tokens = output_tokens = 0
        last_error = "no attempt made"
        for attempt in range(1, self._max_attempts + 1):
            try:
                raw = self._client.complete(prompt, schema)
            except TransientLLMError as exc:
                last_error = f"transient provider error: {exc}"
                log.warning(
                    "llm.retry", prompt_id=prompt.prompt_id, attempt=attempt, reason="transient"
                )
                self._backoff(attempt)
                continue
            input_tokens += raw.input_tokens
            output_tokens += raw.output_tokens
            try:
                output = schema.model_validate_json(raw.text)
            except ValidationError as exc:
                last_error = f"output failed schema validation ({exc.error_count()} errors)"
                log.warning(
                    "llm.retry", prompt_id=prompt.prompt_id, attempt=attempt, reason="schema"
                )
                continue
            usage = LLMUsage(
                provider=self._client.provider,
                model=self._client.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=int((self._clock() - started) * 1000),
                attempts=attempt,
            )
            return LLMResult(output=output, usage=usage)
        raise LLMError(f"{prompt.prompt_id}: {last_error} after {self._max_attempts} attempts")

    def _backoff(self, attempt: int) -> None:
        if attempt < self._max_attempts:
            self._sleep(min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * 2 ** (attempt - 1)))
