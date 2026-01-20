"""Tests for Redis cache service."""

import json
from unittest.mock import Mock, patch

import pytest

from app.services.cache_service import CacheService


class TestCacheService:
    """Test suite for CacheService."""

    @patch("app.services.cache_service.redis.Redis")
    @patch("app.services.cache_service.settings")
    def test_init_redis_enabled(self, mock_settings, mock_redis):
        """Test cache service initialization when Redis is enabled."""
        mock_settings.redis_enabled = True
        mock_settings.redis_host = "localhost"
        mock_settings.redis_port = 6379
        mock_settings.redis_db = 0
        mock_settings.redis_password = None

        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance

        cache = CacheService()

        assert cache.is_available
        mock_redis_instance.ping.assert_called_once()

    @patch("app.services.cache_service.settings")
    def test_init_redis_disabled(self, mock_settings):
        """Test cache service initialization when Redis is disabled."""
        mock_settings.redis_enabled = False

        cache = CacheService()

        assert not cache.is_available

    @patch("app.services.cache_service.redis.Redis")
    @patch("app.services.cache_service.settings")
    def test_get_cache_hit(self, mock_settings, mock_redis):
        """Test get() returns cached data on hit."""
        mock_settings.redis_enabled = True
        mock_settings.redis_host = "localhost"
        mock_settings.redis_port = 6379
        mock_settings.redis_db = 0
        mock_settings.redis_password = None

        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance

        cached_data = {"key": "value", "number": 42}
        mock_redis_instance.get.return_value = json.dumps(cached_data)

        cache = CacheService()
        result = cache.get("test-key")

        assert result == cached_data
        mock_redis_instance.get.assert_called_once_with("idempotency:test-key")

    @patch("app.services.cache_service.redis.Redis")
    @patch("app.services.cache_service.settings")
    def test_get_cache_miss(self, mock_settings, mock_redis):
        """Test get() returns None on cache miss."""
        mock_settings.redis_enabled = True
        mock_settings.redis_host = "localhost"
        mock_settings.redis_port = 6379
        mock_settings.redis_db = 0
        mock_settings.redis_password = None

        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance
        mock_redis_instance.get.return_value = None

        cache = CacheService()
        result = cache.get("missing-key")

        assert result is None

    @patch("app.services.cache_service.redis.Redis")
    @patch("app.services.cache_service.settings")
    def test_set_cache_success(self, mock_settings, mock_redis):
        """Test set() stores data successfully."""
        mock_settings.redis_enabled = True
        mock_settings.redis_host = "localhost"
        mock_settings.redis_port = 6379
        mock_settings.redis_db = 0
        mock_settings.redis_password = None
        mock_settings.redis_ttl_seconds = 3600

        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance

        cache = CacheService()
        data = {"key": "value"}
        result = cache.set("test-key", data)

        assert result is True
        mock_redis_instance.setex.assert_called_once_with(
            "idempotency:test-key", 3600, json.dumps(data)
        )

    @patch("app.services.cache_service.settings")
    def test_get_when_disabled(self, mock_settings):
        """Test get() returns None when Redis is disabled."""
        mock_settings.redis_enabled = False

        cache = CacheService()
        result = cache.get("test-key")

        assert result is None

    @patch("app.services.cache_service.settings")
    def test_set_when_disabled(self, mock_settings):
        """Test set() returns False when Redis is disabled."""
        mock_settings.redis_enabled = False

        cache = CacheService()
        result = cache.set("test-key", {"data": "value"})

        assert result is False

    @patch("app.services.cache_service.redis.Redis")
    @patch("app.services.cache_service.settings")
    def test_delete_cache_key(self, mock_settings, mock_redis):
        """Test delete() removes cached data."""
        mock_settings.redis_enabled = True
        mock_settings.redis_host = "localhost"
        mock_settings.redis_port = 6379
        mock_settings.redis_db = 0
        mock_settings.redis_password = None

        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance

        cache = CacheService()
        result = cache.delete("test-key")

        assert result is True
        mock_redis_instance.delete.assert_called_once_with("idempotency:test-key")

    @patch("app.services.cache_service.redis.Redis")
    @patch("app.services.cache_service.settings")
    def test_close_connection(self, mock_settings, mock_redis):
        """Test close() closes Redis connection."""
        mock_settings.redis_enabled = True
        mock_settings.redis_host = "localhost"
        mock_settings.redis_port = 6379
        mock_settings.redis_db = 0
        mock_settings.redis_password = None

        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance

        cache = CacheService()
        cache.close()

        mock_redis_instance.close.assert_called_once()
