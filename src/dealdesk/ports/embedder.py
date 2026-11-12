"""Embedding port. Vectors are floats by nature; they never enter the domain layer."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class EmbedderPort(Protocol):
    """Turns text into fixed-length vectors for similarity search."""

    @property
    def model(self) -> str:
        """Model identifier recorded alongside retrievals."""

    @property
    def dim(self) -> int:
        """Vector length."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed each text. Same input, same output for deterministic adapters."""
