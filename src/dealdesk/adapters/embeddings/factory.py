"""Select the embedding adapter from configuration."""

from __future__ import annotations

from dealdesk.adapters.embeddings.fake import FakeEmbedder
from dealdesk.adapters.embeddings.providers import OpenAIEmbedder, VertexEmbedder
from dealdesk.config import EmbeddingProvider, Settings
from dealdesk.ports.embedder import EmbedderPort


def build_embedder(settings: Settings) -> EmbedderPort:
    """Return the configured embedder. The fake one is offline and deterministic."""
    if settings.embedding_provider is EmbeddingProvider.VERTEX:
        return VertexEmbedder(
            project=settings.google_cloud_project,
            location=settings.google_cloud_location,
            model=settings.embedding_model,
            dim=settings.embedding_dim,
        )
    if settings.embedding_provider is EmbeddingProvider.OPENAI:
        return OpenAIEmbedder(
            api_key=settings.openai_api_key.get_secret_value(),
            model=settings.embedding_model,
            dim=settings.embedding_dim,
        )
    return FakeEmbedder(dim=settings.embedding_dim, model=settings.embedding_model)
