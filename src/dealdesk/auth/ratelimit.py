"""In-memory sliding-window rate limiter (per process).

Good for a single API replica. With several replicas, back this with Redis or the platform's
rate limiting (documented in docs/SECURITY.md).
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

WINDOW_SECONDS = 60.0


class SlidingWindowLimiter:
    """Allows at most `limit` hits per key in any `window` seconds."""

    def __init__(
        self,
        limit: int,
        window: float = WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit
        self._window = window
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> float | None:
        """Record a hit. Return None if allowed, else seconds until the next hit is allowed."""
        now = self._clock()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self._window:
                hits.popleft()
            if len(hits) >= self._limit:
                return max(0.0, self._window - (now - hits[0]))
            hits.append(now)
            return None
