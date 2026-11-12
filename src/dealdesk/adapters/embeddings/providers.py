"""Real embedding adapters (opt-in). Both request 256-dimension vectors to match the schema."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


class VertexEmbedder:
    """Vertex AI embeddings through the Google Gen AI SDK."""

    def __init__(
        self, *, project: str, location: str, model: str, dim: int, client: Any = None
    ) -> None:
        if client is None:
            from google import genai  # noqa: PLC0415

            client = genai.Client(vertexai=True, project=project, location=location)
        self._client = client
        self._model = model
        self._dim = dim

    @property
    def model(self) -> str:
        """Model name from configuration."""
        return self._model

    @property
    def dim(self) -> int:
        """Vector length."""
        return self._dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed texts with the requested output dimensionality."""
        from google.genai import types  # noqa: PLC0415

        response = self._client.models.embed_content(
            model=self._model,
            contents=list(texts),
            config=types.EmbedContentConfig(output_dimensionality=self._dim),
        )
        return [list(item.values) for item in response.embeddings]


class OpenAIEmbedder:
    """OpenAI embeddings with the `dimensions` parameter."""

    def __init__(self, *, api_key: str, model: str, dim: int, client: Any = None) -> None:
        if client is None:
            import openai  # noqa: PLC0415

            client = openai.OpenAI(api_key=api_key, max_retries=2)
        self._client = client
        self._model = model
        self._dim = dim

    @property
    def model(self) -> str:
        """Model name from configuration."""
        return self._model

    @property
    def dim(self) -> int:
        """Vector length."""
        return self._dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed texts."""
        response = self._client.embeddings.create(
            model=self._model, input=list(texts), dimensions=self._dim
        )
        return [list(item.embedding) for item in response.data]
