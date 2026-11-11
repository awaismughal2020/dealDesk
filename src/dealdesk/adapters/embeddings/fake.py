"""Deterministic, offline embedder using signed feature hashing over words and word pairs.

Good enough to rank SAMPLE past projects by topical overlap; it is not a semantic model.
"""

from __future__ import annotations

import hashlib
import itertools
import math
import re
from collections.abc import Sequence

WORD = re.compile(r"[a-z][a-z0-9]+")
STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "our",
        "that",
        "the",
        "their",
        "this",
        "to",
        "we",
        "will",
        "with",
        "you",
        "your",
        "shall",
        "must",
        "should",
        "can",
        "may",
        "into",
        "within",
        "per",
    ]
)
HASH_BYTES = 8


class FakeEmbedder:
    """Implements `EmbedderPort` without any network access."""

    def __init__(self, dim: int = 256, model: str = "fake-hashing-v1") -> None:
        self._dim = dim
        self._model = model

    @property
    def model(self) -> str:
        """Model identifier."""
        return self._model

    @property
    def dim(self) -> int:
        """Vector length."""
        return self._dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed each text as an L2-normalised hashed bag of words and bigrams."""
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        words = [w for w in WORD.findall(text.lower()) if w not in STOPWORDS]
        features = words + [f"{a}_{b}" for a, b in itertools.pairwise(words)]
        vector = [0.0] * self._dim
        for feature in features:
            digest = hashlib.sha256(feature.encode()).digest()
            index = int.from_bytes(digest[:HASH_BYTES], "big") % self._dim
            vector[index] += 1.0 if digest[HASH_BYTES] % 2 == 0 else -1.0
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            vector[0] = 1.0
            return vector
        return [v / norm for v in vector]
