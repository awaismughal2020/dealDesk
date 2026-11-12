"""Google Vertex AI through the official Google Gen AI SDK (`google-genai`).

Uses Application Default Credentials. Opt-in only: LLM_PROVIDER=vertex. Brief text is sent to
Google Cloud in the configured project and region when this adapter is enabled.
"""

from __future__ import annotations

from typing import Any

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from dealdesk.adapters.llm.base import RawCompletion, TransientLLMError
from dealdesk.ports.llm import PromptSpec

RATE_LIMITED = 429
MS_PER_SECOND = 1000


class VertexModelClient:
    """Implements `ModelClient` with JSON-schema constrained output."""

    def __init__(
        self,
        *,
        project: str,
        location: str,
        model: str,
        temperature: float,
        timeout_seconds: int,
        max_output_tokens: int,
        client: Any = None,
    ) -> None:
        self._client = client or genai.Client(
            vertexai=True,
            project=project,
            location=location,
            http_options=types.HttpOptions(timeout=timeout_seconds * MS_PER_SECOND),
        )
        self._model = model
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens

    @property
    def provider(self) -> str:
        """Provider name."""
        return "vertex"

    @property
    def model(self) -> str:
        """Model name from configuration."""
        return self._model

    def complete(self, prompt: PromptSpec, schema: type[BaseModel]) -> RawCompletion:
        """Call `generate_content` with a response JSON schema."""
        config = types.GenerateContentConfig(
            system_instruction=prompt.system,
            temperature=self._temperature,
            max_output_tokens=self._max_output_tokens,
            response_mime_type="application/json",
            response_json_schema=schema.model_json_schema(),
        )
        try:
            response = self._client.models.generate_content(
                model=self._model, contents=prompt.user, config=config
            )
        except errors.ServerError as exc:
            raise TransientLLMError(str(exc.code)) from exc
        except errors.ClientError as exc:
            if exc.code == RATE_LIMITED:
                raise TransientLLMError("rate limited") from exc
            raise
        usage = response.usage_metadata
        return RawCompletion(
            text=response.text or "",
            input_tokens=(usage.prompt_token_count or 0) if usage else 0,
            output_tokens=(usage.candidates_token_count or 0) if usage else 0,
        )
