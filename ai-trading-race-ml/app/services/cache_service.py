"""Redis cache service for idempotency and response deduplication."""

import json
import logging
from typing import Optional

import redis
from redis.exceptions import RedisError

from app.config import settings

logger = logging.getLogger(__name__)


class CacheService:
    """
    Redis-based cache service for request idempotency.
    
    Caches responses by idempotency key to prevent duplicate processing
    of the same request within the TTL window (default 1 hour).
    """

    def __init__(self):
        """Initialize Redis connection if enabled."""
        self._redis_client: Optional[redis.Redis] = None
        
        if settings.redis_enabled:
            try:
                self._redis_client = redis.Redis(
                    host=settings.redis_host,
                    port=settings.redis_port,
                    db=settings.redis_db,
                    password=settings.redis_password,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                )
                # Test connection
                self._redis_client.ping()
                logger.info(
                    f"Redis cache connected: {settings.redis_host}:{settings.redis_port}"
                )
            except RedisError as e:
                logger.warning(f"Redis connection failed, cache disabled: {e}")
                self._redis_client = None

    @property
    def is_available(self) -> bool:
        """Check if Redis is available."""
        return self._redis_client is not None

    def get(self, idempotency_key: str) -> Optional[dict]:
        """
        Get cached response by idempotency key.
        
        Args:
            idempotency_key: Unique key for the request
            
        Returns:
            Cached response dict or None if not found/expired
        """
        if not self.is_available:
            return None

        try:
            cached = self._redis_client.get(f"idempotency:{idempotency_key}")
            if cached:
                logger.info(f"Cache HIT for key: {idempotency_key}")
                return json.loads(cached)
            logger.debug(f"Cache MISS for key: {idempotency_key}")
            return None
        except (RedisError, json.JSONDecodeError) as e:
            logger.error(f"Error reading from cache: {e}")
            return None

    def set(self, idempotency_key: str, response: dict) -> bool:
        """
        Cache a response with TTL.
        
        Args:
            idempotency_key: Unique key for the request
            response: Response dict to cache
            
        Returns:
            True if cached successfully, False otherwise
        """
        if not self.is_available:
            return False

        try:
            serialized = json.dumps(response)
            self._redis_client.setex(
                f"idempotency:{idempotency_key}",
                settings.redis_ttl_seconds,
                serialized,
            )
            logger.info(
                f"Cached response for key: {idempotency_key} "
                f"(TTL: {settings.redis_ttl_seconds}s)"
            )
            return True
        except (RedisError, TypeError) as e:
            logger.error(f"Error writing to cache: {e}")
            return False

    def delete(self, idempotency_key: str) -> bool:
        """
        Delete a cached response.
        
        Args:
            idempotency_key: Key to delete
            
        Returns:
            True if deleted successfully
        """
        if not self.is_available:
            return False

        try:
            self._redis_client.delete(f"idempotency:{idempotency_key}")
            logger.debug(f"Deleted cache key: {idempotency_key}")
            return True
        except RedisError as e:
            logger.error(f"Error deleting from cache: {e}")
            return False

    def close(self):
        """Close Redis connection."""
        if self._redis_client:
            try:
                self._redis_client.close()
                logger.info("Redis connection closed")
            except RedisError as e:
                logger.error(f"Error closing Redis connection: {e}")


# Global cache instance
cache_service = CacheService()
