"""Tiny in-process TTL cache.

Phase 3 / §8.14: grid endpoints are read-heavy and the upstream EIA data
only refreshes hourly. Caching reads for a few minutes makes the demo snappy
without lying about freshness — `last_updated` in the response always
reflects the underlying data's true timestamp, not the cache fill time.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Tuple


class TTLCache:
    def __init__(self, ttl_s: float) -> None:
        self._ttl = ttl_s
        self._store: dict[str, Tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            expires_at, value = entry
            if expires_at < time.monotonic():
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = (time.monotonic() + self._ttl, value)

    def get_or_set(self, key: str, factory: Callable[[], Any]) -> Any:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = factory()
        self.set(key, value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
