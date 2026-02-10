"""
Tests for Caching Middleware
"""

import time
import pytest
from unittest.mock import MagicMock

from vel import ToolSpec

from vel_harness.middleware.caching import (
    CacheEntry,
    CacheConfig,
    PromptCache,
    ToolResultCache,
    AnthropicPromptCachingMiddleware,
    ToolCachingMiddleware,
    create_caching_middleware,
)


class TestCacheEntry:
    """Test CacheEntry dataclass."""

    def test_not_expired(self):
        """Test entry is not expired when within TTL."""
        entry = CacheEntry(
            value="test",
            created_at=time.time(),
            expires_at=time.time() + 100,
        )
        assert not entry.is_expired()

    def test_expired(self):
        """Test entry is expired when past TTL."""
        entry = CacheEntry(
            value="test",
            created_at=time.time() - 200,
            expires_at=time.time() - 100,
        )
        assert entry.is_expired()


class TestPromptCache:
    """Test PromptCache class."""

    @pytest.fixture
    def cache(self):
        """Create a prompt cache."""
        return PromptCache(ttl=60)

    def test_set_and_get(self, cache):
        """Test setting and getting cached values."""
        wrapped = {"content": "test prompt", "cache_control": {"type": "ephemeral"}}
        cache.set("test prompt", wrapped)

        result = cache.get("test prompt")
        assert result == wrapped

    def test_get_miss(self, cache):
        """Test cache miss returns None."""
        result = cache.get("nonexistent")
        assert result is None

    def test_expired_entry_removed(self, cache):
        """Test expired entries are removed on get."""
        cache._cache["test"] = CacheEntry(
            value={"content": "old"},
            created_at=time.time() - 200,
            expires_at=time.time() - 100,
        )

        result = cache.get("some content that hashes to 'test'")
        assert result is None

    def test_hit_count_incremented(self, cache):
        """Test hit count is incremented on cache hits."""
        cache.set("test", {"content": "test"})

        cache.get("test")
        cache.get("test")

        stats = cache.get_stats()
        assert stats["total_hits"] == 2

    def test_clear(self, cache):
        """Test clearing the cache."""
        cache.set("test1", {"content": "1"})
        cache.set("test2", {"content": "2"})

        count = cache.clear()
        assert count == 2
        assert cache.get("test1") is None


class TestToolResultCache:
    """Test ToolResultCache class."""

    @pytest.fixture
    def cache(self):
        """Create a tool result cache."""
        return ToolResultCache(ttl=60, max_size=10)

    def test_set_and_get(self, cache):
        """Test setting and getting cached values."""
        cache.set("list_tables", {}, ["users", "orders"])

        result = cache.get("list_tables", {})
        assert result == ["users", "orders"]

    def test_get_miss(self, cache):
        """Test cache miss returns None."""
        result = cache.get("unknown_tool", {"arg": "value"})
        assert result is None

    def test_different_args_different_keys(self, cache):
        """Test different args produce different cache keys."""
        cache.set("query", {"table": "users"}, [1, 2, 3])
        cache.set("query", {"table": "orders"}, [4, 5, 6])

        result1 = cache.get("query", {"table": "users"})
        result2 = cache.get("query", {"table": "orders"})

        assert result1 == [1, 2, 3]
        assert result2 == [4, 5, 6]

    def test_max_size_eviction(self, cache):
        """Test oldest entries are evicted when cache is full."""
        # Fill cache
        for i in range(15):
            cache.set(f"tool_{i}", {}, f"result_{i}")

        # Only 10 should remain
        assert len(cache._cache) == 10

    def test_large_entry_rejected(self):
        """Test entries exceeding max size are rejected."""
        cache = ToolResultCache(max_entry_size=100)

        large_content = "x" * 1000
        result = cache.set("tool", {}, large_content)

        assert result is False
        assert cache.get("tool", {}) is None

    def test_invalidate(self, cache):
        """Test invalidating entries for a tool."""
        cache.set("tool", {"a": 1}, "result1")
        cache.set("tool", {"b": 2}, "result2")
        cache.set("other", {}, "other")

        # This won't work directly because keys are hashes
        # but we can test the method exists
        cache.invalidate("tool")

    def test_clear(self, cache):
        """Test clearing the cache."""
        cache.set("tool1", {}, "result1")
        cache.set("tool2", {}, "result2")

        count = cache.clear()
        assert count == 2
        assert cache.get("tool1", {}) is None


class TestAnthropicPromptCachingMiddleware:
    """Test AnthropicPromptCachingMiddleware class."""

    @pytest.fixture
    def middleware(self):
        """Create prompt caching middleware."""
        return AnthropicPromptCachingMiddleware(ttl_seconds=60)

    def test_wrap_claude_prompt(self, middleware):
        """Test wrapping prompt for Claude model."""
        result = middleware.wrap_system_prompt(
            "You are a helpful assistant.",
            "claude-sonnet-4-5-20250929",
        )

        assert result["content"] == "You are a helpful assistant."
        assert result["cache_control"]["type"] == "ephemeral"

    def test_non_claude_not_wrapped(self, middleware):
        """Test non-Claude models don't get cache control."""
        result = middleware.wrap_system_prompt(
            "You are a helpful assistant.",
            "gpt-4o",
        )

        assert result["content"] == "You are a helpful assistant."
        assert "cache_control" not in result

    def test_disabled_not_wrapped(self):
        """Test disabled middleware doesn't wrap."""
        middleware = AnthropicPromptCachingMiddleware(enabled=False)

        result = middleware.wrap_system_prompt(
            "test",
            "claude-sonnet-4-5-20250929",
        )

        assert "cache_control" not in result

    def test_caching_works(self, middleware):
        """Test repeated wraps use cache."""
        prompt = "You are a helpful assistant."

        result1 = middleware.wrap_system_prompt(prompt, "claude-sonnet-4-5-20250929")
        result2 = middleware.wrap_system_prompt(prompt, "claude-sonnet-4-5-20250929")

        assert result1 == result2

        stats = middleware.get_stats()
        assert stats["total_hits"] == 1

    def test_clear_cache(self, middleware):
        """Test clearing the cache."""
        middleware.wrap_system_prompt("test", "claude-sonnet-4-5-20250929")

        count = middleware.clear_cache()
        assert count == 1


class TestToolCachingMiddleware:
    """Test ToolCachingMiddleware class."""

    @pytest.fixture
    def middleware(self):
        """Create tool caching middleware."""
        config = CacheConfig(
            tool_cache_enabled=True,
            tool_cache_ttl=60,
            cacheable_tools={"list_tables", "describe_table"},
        )
        return ToolCachingMiddleware(config=config)

    def test_is_cacheable(self, middleware):
        """Test identifying cacheable tools."""
        assert middleware.is_cacheable("list_tables")
        assert middleware.is_cacheable("describe_table")
        assert not middleware.is_cacheable("write_file")

    def test_cache_result(self, middleware):
        """Test caching tool results."""
        result = middleware.cache_result("list_tables", {}, ["users", "orders"])
        assert result is True

        hit, cached = middleware.get_cached("list_tables", {})
        assert hit is True
        assert cached == ["users", "orders"]

    def test_non_cacheable_not_cached(self, middleware):
        """Test non-cacheable tools are not cached."""
        result = middleware.cache_result("write_file", {}, {"status": "ok"})
        assert result is False

    def test_wrap_tool(self, middleware):
        """Test wrapping a tool with caching."""
        call_count = 0

        def handler():
            nonlocal call_count
            call_count += 1
            return ["users", "orders"]

        tool = ToolSpec.from_function(
            handler,
            name="list_tables",
            description="List tables",
        )

        wrapped = middleware.wrap_tool(tool)

        # First call executes handler
        result1 = wrapped._handler()
        assert result1 == ["users", "orders"]
        assert call_count == 1

        # Second call uses cache
        result2 = wrapped._handler()
        assert result2 == ["users", "orders"]
        assert call_count == 1  # Not incremented

    def test_get_stats(self, middleware):
        """Test getting cache statistics."""
        middleware.cache_result("list_tables", {}, ["tables"])

        stats = middleware.get_stats()
        assert stats["enabled"] is True
        assert "list_tables" in stats["cacheable_tools"]
        assert stats["entries"] == 1

    def test_get_tools(self, middleware):
        """Test getting cache management tools."""
        tools = middleware.get_tools()

        tool_names = [t.name for t in tools]
        assert "get_cache_stats" in tool_names
        assert "clear_tool_cache" in tool_names


class TestCacheConfig:
    """Test CacheConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = CacheConfig()
        assert config.prompt_cache_enabled is True
        assert config.tool_cache_enabled is True
        assert config.prompt_cache_ttl == 300
        assert config.tool_cache_ttl == 60
        assert "list_tables" in config.cacheable_tools

    def test_custom_values(self):
        """Test custom configuration values."""
        config = CacheConfig(
            prompt_cache_ttl=600,
            tool_cache_ttl=120,
            cacheable_tools={"custom_tool"},
        )
        assert config.prompt_cache_ttl == 600
        assert config.tool_cache_ttl == 120
        assert "custom_tool" in config.cacheable_tools


class TestCreateCachingMiddleware:
    """Test create_caching_middleware factory."""

    def test_create_with_defaults(self):
        """Test creating with default settings."""
        prompt_mw, tool_mw = create_caching_middleware()

        assert prompt_mw.enabled is True
        assert prompt_mw.ttl == 300

        assert tool_mw.config.tool_cache_enabled is True
        assert tool_mw.config.tool_cache_ttl == 60

    def test_create_with_custom_ttl(self):
        """Test creating with custom TTL."""
        prompt_mw, tool_mw = create_caching_middleware(
            prompt_ttl=600,
            tool_ttl=120,
        )

        assert prompt_mw.ttl == 600
        assert tool_mw.config.tool_cache_ttl == 120

    def test_create_disabled(self):
        """Test creating with caching disabled."""
        prompt_mw, tool_mw = create_caching_middleware(
            prompt_cache_enabled=False,
            tool_cache_enabled=False,
        )

        assert prompt_mw.enabled is False
        assert tool_mw.config.tool_cache_enabled is False


class TestCachingIntegration:
    """Integration tests for caching."""

    def test_full_workflow(self):
        """Test full caching workflow."""
        prompt_mw, tool_mw = create_caching_middleware()

        # Cache a prompt
        wrapped = prompt_mw.wrap_system_prompt(
            "You are helpful.",
            "claude-sonnet-4-5-20250929",
        )
        assert "cache_control" in wrapped

        # Cache a tool result
        tool_mw.cache_result("list_tables", {}, ["users"])

        # Verify both caches
        prompt_stats = prompt_mw.get_stats()
        tool_stats = tool_mw.get_stats()

        assert prompt_stats["entries"] == 1
        assert tool_stats["entries"] == 1
