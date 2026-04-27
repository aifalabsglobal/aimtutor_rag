"""Per-user skill mastery store.

Default backend is a process-local in-memory dict. When ``REDIS_URL`` is
set the store will lazily connect via ``redis.asyncio`` (TTL 30 days).
Any Redis import error or connection failure logs a warning and
gracefully falls back to in-memory — never raises to callers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import TYPE_CHECKING

from .bkt import DEFAULT_MASTERY, DEFAULT_SKILL

if TYPE_CHECKING:
    from redis.asyncio import Redis  # noqa: F401  (type-only)

logger = logging.getLogger(__name__)

REDIS_KEY_PREFIX = "aimtutor:live:knowledge"
REDIS_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days


def _redis_key(user_id: str) -> str:
    return f"{REDIS_KEY_PREFIX}:{user_id}"


class KnowledgeStore:
    """Async store for per-user skill mastery probabilities.

    Read latency target: < 5 ms (in-memory dict lookup; Redis is best-effort).
    Reads NEVER throw — return ``{DEFAULT_SKILL: DEFAULT_MASTERY}`` if missing.
    """

    def __init__(self, redis_url: str | None = None) -> None:
        self._redis_url = redis_url
        self._memory: dict[str, dict[str, float]] = {}
        self._lock = asyncio.Lock()
        self._redis: object | None = None
        self._redis_init_attempted = False

    async def _get_redis(self) -> object | None:
        if self._redis_init_attempted:
            return self._redis
        self._redis_init_attempted = True

        if not self._redis_url:
            return None

        try:
            from redis.asyncio import Redis  # type: ignore[import-not-found]

            self._redis = Redis.from_url(
                self._redis_url, encoding="utf-8", decode_responses=True
            )
            await self._redis.ping()  # type: ignore[union-attr]
            logger.info("Knowledge store connected to Redis at %s", self._redis_url)
        except Exception as exc:
            logger.warning(
                "Redis unavailable for knowledge store, falling back to in-memory: %s",
                exc,
            )
            self._redis = None
        return self._redis

    async def get(self, user_id: str) -> dict[str, float]:
        """Return the user's skill -> mastery map. Always succeeds."""
        if not user_id:
            return {DEFAULT_SKILL: DEFAULT_MASTERY}

        redis_client = await self._get_redis()
        if redis_client is not None:
            try:
                raw = await redis_client.get(_redis_key(user_id))  # type: ignore[union-attr]
                if raw:
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        # Mirror to memory for next call.
                        self._memory[user_id] = {str(k): float(v) for k, v in data.items()}
                        return dict(self._memory[user_id])
            except Exception as exc:
                logger.warning("Knowledge store Redis read failed: %s", exc)

        async with self._lock:
            return dict(
                self._memory.get(user_id) or {DEFAULT_SKILL: DEFAULT_MASTERY}
            )

    async def update_skill(self, user_id: str, skill: str, p: float) -> None:
        """Persist a single skill's mastery. Bounded to ``[0, 1]``."""
        if not user_id or not skill:
            return
        bounded = max(0.0, min(1.0, float(p)))

        async with self._lock:
            user_map = self._memory.setdefault(user_id, {})
            user_map[skill] = bounded
            snapshot = dict(user_map)

        redis_client = await self._get_redis()
        if redis_client is not None:
            try:
                await redis_client.set(  # type: ignore[union-attr]
                    _redis_key(user_id),
                    json.dumps(snapshot),
                    ex=REDIS_TTL_SECONDS,
                )
            except Exception as exc:
                logger.warning("Knowledge store Redis write failed: %s", exc)


_store: KnowledgeStore | None = None


def get_knowledge_store() -> KnowledgeStore:
    """Singleton accessor. Picks up ``REDIS_URL`` at first call."""
    global _store
    if _store is None:
        _store = KnowledgeStore(redis_url=os.environ.get("REDIS_URL") or None)
    return _store
