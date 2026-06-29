"""
Simple in-memory cache with TTL for event data.
Keeps memory usage low for Railway free tier (512MB).
"""
import time
import logging
from typing import Any

from config import CACHE_TTL

logger = logging.getLogger(__name__)


class EventCache:
    """Thread-safe in-memory cache with TTL expiration."""

    def __init__(self, default_ttl: int = CACHE_TTL):
        self._store: dict[str, dict[str, Any]] = {}
        self._default_ttl = default_ttl

    def _make_key(self, city: str, state: str, suffix: str = "") -> str:
        key = f"{city.lower()}:{state.upper()}"
        if suffix:
            key += f":{suffix}"
        return key

    def get(self, city: str, state: str, suffix: str = "") -> list | None:
        """Get cached events for a city. Returns None if expired or missing."""
        key = self._make_key(city, state, suffix)
        entry = self._store.get(key)
        if entry is None:
            return None

        if time.time() > entry["expires_at"]:
            del self._store[key]
            logger.debug(f"Cache expired for {key}")
            return None

        logger.debug(f"Cache hit for {key} ({len(entry['data'])} events)")
        return entry["data"]

    def set(self, city: str, state: str, events: list, suffix: str = "", ttl: int | None = None):
        """Cache events for a city with TTL."""
        key = self._make_key(city, state, suffix)
        self._store[key] = {
            "data": events,
            "expires_at": time.time() + (ttl or self._default_ttl),
            "stored_at": time.time(),
        }
        logger.debug(f"Cached {len(events)} events for {key}")

    def invalidate(self, city: str, state: str, suffix: str = ""):
        """Remove a specific cache entry."""
        key = self._make_key(city, state, suffix)
        if key in self._store:
            del self._store[key]
            logger.debug(f"Invalidated cache for {key}")

    def invalidate_city(self, city: str, state: str):
        """Remove all cache entries for a city."""
        prefix = self._make_key(city, state)
        keys_to_remove = [k for k in self._store if k.startswith(prefix)]
        for key in keys_to_remove:
            del self._store[key]
        logger.debug(f"Invalidated {len(keys_to_remove)} cache entries for {prefix}")

    def clear(self):
        """Clear the entire cache."""
        count = len(self._store)
        self._store.clear()
        logger.info(f"Cache cleared ({count} entries removed)")

    @property
    def size(self) -> int:
        """Number of cached entries."""
        return len(self._store)

    def cleanup_expired(self):
        """Remove expired entries to free memory."""
        now = time.time()
        expired = [k for k, v in self._store.items() if now > v["expires_at"]]
        for key in expired:
            del self._store[key]
        if expired:
            logger.info(f"Cleaned up {len(expired)} expired cache entries")


# Singleton cache instance
event_cache = EventCache()
