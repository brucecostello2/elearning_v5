"""
Redis client with async connection pooling.

Uses redis.asyncio for non-blocking Redis access.
Provides JSON helpers, health check, and typed convenience methods.
"""
import json
import logging
from typing import Any, Optional

import redis.asyncio as aioredis

from .config import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Async Redis client wrapper with connection pooling and JSON helpers."""

    def __init__(self) -> None:
        self._pool = aioredis.ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            decode_responses=True,
        )
        self.client = aioredis.Redis(connection_pool=self._pool)

    # ------------------------------------------------------------------
    # Primitive operations
    # ------------------------------------------------------------------

    async def get(self, key: str) -> Optional[str]:
        """Get string value by key."""
        try:
            return await self.client.get(key)
        except Exception as e:
            logger.error(f"Redis GET error for key={key}: {e}")
            return None

    async def set(
        self, key: str, value: str, ex: Optional[int] = None
    ) -> bool:
        """Set key to string value with optional TTL (seconds)."""
        try:
            result = await self.client.set(key, value, ex=ex)
            return bool(result)
        except Exception as e:
            logger.error(f"Redis SET error for key={key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete a key. Returns True if the key existed."""
        try:
            return (await self.client.delete(key)) > 0
        except Exception as e:
            logger.error(f"Redis DELETE error for key={key}: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """Check whether a key exists."""
        try:
            return (await self.client.exists(key)) > 0
        except Exception as e:
            logger.error(f"Redis EXISTS error for key={key}: {e}")
            return False

    async def incr(self, key: str) -> Optional[int]:
        """Atomically increment an integer key."""
        try:
            return await self.client.incr(key)
        except Exception as e:
            logger.error(f"Redis INCR error for key={key}: {e}")
            return None

    async def expire(self, key: str, seconds: int) -> bool:
        """Set TTL on an existing key."""
        try:
            return await self.client.expire(key, seconds)
        except Exception as e:
            logger.error(f"Redis EXPIRE error for key={key}: {e}")
            return False

    # ------------------------------------------------------------------
    # JSON convenience
    # ------------------------------------------------------------------

    async def get_json(self, key: str) -> Optional[dict]:
        """Get and JSON-decode a value."""
        raw = await self.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for key={key}: {e}")
            return None

    async def set_json(
        self, key: str, value: Any, ex: Optional[int] = None
    ) -> bool:
        """JSON-encode and set a value."""
        try:
            return await self.set(key, json.dumps(value, default=str), ex=ex)
        except (TypeError, ValueError) as e:
            logger.error(f"JSON encode error for key={key}: {e}")
            return False

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def ping(self) -> bool:
        """Return True if Redis responds to PING."""
        try:
            return await self.client.ping()
        except Exception as e:
            logger.error(f"Redis PING failed: {e}")
            return False

    async def close(self) -> None:
        """Close the connection pool gracefully."""
        await self.client.aclose()
        logger.info("Redis connection pool closed")


# Global singleton — import and use directly.
redis_client = RedisClient()
