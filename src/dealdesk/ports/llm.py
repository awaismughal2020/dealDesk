"""Language-model port. The model reads and writes text; it never computes money or dates.

The model has no tools and no way to change state: it receives a prompt and returns JSON that is
validated against a strict Pydantic schema before anything else sees it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


@dataclass(frozen=True, slots=True)
class PromptSpec:
    """A rendered, versioned prompt. Untrusted text is already delimited inside `user`."""

    prompt_id: str
    version: str
    system: str
    user: str


@dataclass(frozen=True, slots=True)
class LLMUsage:
    """Accounting for one logical call (summed over retries)."""

    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    attempts: int


@dataclass(frozen=True, slots=True)
class LLMResult[T: BaseModel]:
    """A validated model output and its usage."""

    output: T
    usage: LLMUsage


class LLMError(Exception):
    """The model could not produce a valid answer within the retry budget."""


class LLMPort(Protocol):
    """Generate a schema-valid structured output for a prompt."""

    def generate[T: BaseModel](self, prompt: PromptSpec, schema: type[T]) -> LLMResult[T]:
        """Return a validated instance of `schema`, or raise `LLMError`."""
