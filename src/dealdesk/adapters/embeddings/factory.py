"""Select the embedding adapter from configuration."""

from __future__ import annotations

from dealdesk.adapters.embeddings.fake import FakeEmbedder
from dealdesk.config import EmbeddingProvider, Settings
from dealdesk.ports.embedder import EmbedderPort


def build_embedder(settings: Settings) -> EmbedderPort:
    """Return the configured embedder. The fake one is offline and deterministic."""
    if settings.embedding_provider is EmbeddingProvider.FAKE:
        return FakeEmbedder(dim=settings.embedding_dim, model=settings.embedding_model)
    raise NotImplementedError(settings.embedding_provider)
