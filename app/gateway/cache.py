"""Redis caching layer for NBA API responses."""

import hashlib
import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)


class RedisCache:
    def __init__(self, redis_url: str | None = None, ttl: int | None = None):
        self.redis_url = redis_url or settings.redis_url
        self.ttl = ttl or settings.cache_ttl
        self._client: aioredis.Redis | None = None

    async def connect(self) -> None:
        try:
            self._client = aioredis.from_url(self.redis_url, decode_responses=True)
            await self._client.ping()
            logger.info("Connected to Redis at %s", self.redis_url)
        except Exception:
            logger.warning("Redis unavailable — caching disabled")
            self._client = None

    async def disconnect(self) -> None:
        if self._client:
            await self._client.close()

    @staticmethod
    def _make_key(prefix: str, *args: str) -> str:
        raw = ":".join([prefix, *args])
        return f"courtvision:{hashlib.md5(raw.encode()).hexdigest()}"

    async def get(self, prefix: str, *args: str) -> Any | None:
        if not self._client:
            return None
        key = self._make_key(prefix, *args)
        try:
            data = await self._client.get(key)
            if data:
                return json.loads(data)
        except Exception as exc:
            logger.debug("Cache get failed: %s", exc)
        return None

    async def set(self, prefix: str, value: Any, *args: str, ttl: int | None = None) -> None:
        if not self._client:
            return
        key = self._make_key(prefix, *args)
        try:
            await self._client.set(key, json.dumps(value), ex=ttl or self.ttl)
        except Exception as exc:
            logger.debug("Cache set failed: %s", exc)

    async def delete_pattern(self, prefix: str) -> int:
        if not self._client:
            return 0
        pattern = f"courtvision:*"
        deleted = 0
        async for key in self._client.scan_iter(match=pattern):
            await self._client.delete(key)
            deleted += 1
        return deleted


cache = RedisCache()
