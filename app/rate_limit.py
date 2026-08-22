from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone


class InMemoryRateLimiter:
    """Simple sliding-window rate limiter for sensitive endpoints."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[datetime]] = defaultdict(deque)

    def is_allowed(self, key: str) -> bool:
        now = datetime.now(timezone.utc)
        window_start = now.timestamp() - self.window_seconds
        hits = self._hits[key]
        while hits and hits[0].timestamp() < window_start:
            hits.popleft()
        if len(hits) >= self.max_requests:
            return False
        hits.append(now)
        return True
