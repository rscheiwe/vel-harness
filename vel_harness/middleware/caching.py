"""
Caching Middleware

Implements caching for improved performance:
- Anthropic prompt caching for reduced latency
- Tool response caching for repeated calls
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from vel import ToolSpec


@dataclass
class CacheEntry:
    """A cached value with metadata."""

    value: Any
    created_at: float
    expires_at: float
    hit_count: int = 0

    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        return time.time() > self.expires_at


@dataclass
class CacheConfig:
    """Configuration for caching behavior."""

    # Prompt caching
    prompt_cache_enabled: bool = True
    prompt_cache_ttl: int = 300  # 5 minutes

    # Tool result caching
    tool_cache_enabled: bool = True
    tool_cache_ttl: int = 60  # 1 minute
    cacheable_tools: set = field(default_factory=lambda: {
        "list_tables",
        "describe_table",
        "list_skills",
        "get_skill",
        "web_search",
    })

    # Cache limits
    max_cache_size: int = 100
    max_entry_size: int = 50_000  # 50KB


class PromptCache:
    """Cache for system prompts and static content."""

    def __init__(self, ttl: int = 300):
        self._cache: Dict[str, CacheEntry] = {}
        self._ttl = ttl

    def _make_key(self, content: str) -> str:
        """Create cache key from content."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def get(self, content: str) -> Optional[Dict[str, Any]]:
        """Get cached prompt wrapper if available."""
        key = self._make_key(content)

        if key in self._cache:
            entry = self._cache[key]
            if not entry.is_expired():
                entry.hit_count += 1
                return entry.value
            else:
                del self._cache[key]

        return None

    def set(self, content: str, wrapped: Dict[str, Any]) -> None:
        """Cache a wrapped prompt."""
        key = self._make_key(content)
        self._cache[key] = CacheEntry(
            value=wrapped,
            created_at=time.time(),
            expires_at=time.time() + self._ttl,
        )

    def clear(self) -> int:
        """Clear all cached entries. Returns count cleared."""
        count = len(self._cache)
        self._cache.clear()
        return count

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_hits = sum(e.hit_count for e in self._cache.values())
        return {
            "entries": len(self._cache),
            "total_hits": total_hits,
            "ttl": self._ttl,
        }


class ToolResultCache:
    """Cache for tool execution results."""

    def __init__(
        self,
        ttl: int = 60,
        max_size: int = 100,
        max_entry_size: int = 50_000,
    ):
        self._cache: Dict[str, CacheEntry] = {}
        self._ttl = ttl
        self._max_size = max_size
        self._max_entry_size = max_entry_size

    def _make_key(self, tool_name: str, args: Dict[str, Any]) -> str:
        """Create cache key from tool name and arguments."""
        # Sort args for consistent hashing
        args_str = json.dumps(args, sort_keys=True, default=str)
        combined = f"{tool_name}:{args_str}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def _evict_oldest(self) -> None:
        """Evict oldest entries if cache is full."""
        while len(self._cache) >= self._max_size:
            oldest_key = min(
                self._cache.keys(),
                key=lambda k: self._cache[k].created_at,
            )
            del self._cache[oldest_key]

    def get(
        self, tool_name: str, args: Dict[str, Any]
    ) -> Optional[Any]:
        """Get cached result if available."""
        key = self._make_key(tool_name, args)

        if key in self._cache:
            entry = self._cache[key]
            if not entry.is_expired():
                entry.hit_count += 1
                return entry.value
            else:
                del self._cache[key]

        return None

    def set(
        self, tool_name: str, args: Dict[str, Any], result: Any
    ) -> bool:
        """Cache a tool result. Returns True if cached."""
        # Check size
        result_str = json.dumps(result, default=str)
        if len(result_str) > self._max_entry_size:
            return False

        # Evict if needed
        self._evict_oldest()

        key = self._make_key(tool_name, args)
        self._cache[key] = CacheEntry(
            value=result,
            created_at=time.time(),
            expires_at=time.time() + self._ttl,
        )
        return True

    def invalidate(self, tool_name: str) -> int:
        """Invalidate all cached results for a tool. Returns count."""
        keys_to_remove = [
            k for k in self._cache.keys()
            if k.startswith(tool_name)
        ]
        for k in keys_to_remove:
            del self._cache[k]
        return len(keys_to_remove)

    def clear(self) -> int:
        """Clear all cached entries."""
        count = len(self._cache)
        self._cache.clear()
        return count

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_hits = sum(e.hit_count for e in self._cache.values())
        return {
            "entries": len(self._cache),
            "max_size": self._max_size,
            "total_hits": total_hits,
            "ttl": self._ttl,
        }


class AnthropicPromptCachingMiddleware:
    """
    Cache system prompts for Anthropic models.

    Reduces latency and cost for repeated prompts by using
    Anthropic's prompt caching feature.
    """

    def __init__(
        self,
        ttl_seconds: int = 300,
        enabled: bool = True,
    ):
        self.ttl = ttl_seconds
        self.enabled = enabled
        self._cache = PromptCache(ttl=ttl_seconds)

    def wrap_system_prompt(
        self, prompt: str, model: str
    ) -> Dict[str, Any]:
        """
        Wrap prompt with cache control for Anthropic.

        Args:
            prompt: System prompt content
            model: Model identifier

        Returns:
            Wrapped prompt with cache_control if applicable
        """
        if not self.enabled:
            return {"content": prompt}

        # Only cache for Claude models
        if "claude" not in model.lower():
            return {"content": prompt}

        # Check cache first
        cached = self._cache.get(prompt)
        if cached:
            return cached

        # Create cacheable wrapper
        wrapped = {
            "content": prompt,
            "cache_control": {"type": "ephemeral"},
        }

        # Cache it
        self._cache.set(prompt, wrapped)

        return wrapped

    def get_stats(self) -> Dict[str, Any]:
        """Get caching statistics."""
        return {
            "enabled": self.enabled,
            "ttl": self.ttl,
            **self._cache.get_stats(),
        }

    def clear_cache(self) -> int:
        """Clear the prompt cache."""
        return self._cache.clear()


class ToolCachingMiddleware:
    """
    Cache tool results for repeated calls.

    Reduces latency for tools that return the same results
    for the same inputs (e.g., schema lookups, skill lists).
    """

    def __init__(
        self,
        config: Optional[CacheConfig] = None,
    ):
        self.config = config or CacheConfig()
        self._cache = ToolResultCache(
            ttl=self.config.tool_cache_ttl,
            max_size=self.config.max_cache_size,
            max_entry_size=self.config.max_entry_size,
        )

    def is_cacheable(self, tool_name: str) -> bool:
        """Check if a tool's results should be cached."""
        if not self.config.tool_cache_enabled:
            return False
        return tool_name in self.config.cacheable_tools

    def get_cached(
        self, tool_name: str, args: Dict[str, Any]
    ) -> Tuple[bool, Optional[Any]]:
        """
        Get cached result if available.

        Returns:
            Tuple of (cache_hit, result)
        """
        if not self.is_cacheable(tool_name):
            return False, None

        result = self._cache.get(tool_name, args)
        return result is not None, result

    def cache_result(
        self, tool_name: str, args: Dict[str, Any], result: Any
    ) -> bool:
        """
        Cache a tool result.

        Returns:
            True if result was cached
        """
        if not self.is_cacheable(tool_name):
            return False

        return self._cache.set(tool_name, args, result)

    def wrap_tool(self, tool: ToolSpec) -> ToolSpec:
        """
        Wrap a tool with caching behavior.

        Args:
            tool: Original tool spec

        Returns:
            Wrapped tool with caching
        """
        if not self.is_cacheable(tool.name):
            return tool

        middleware = self
        original_handler = tool._handler

        def cached_handler(**kwargs: Any) -> Any:
            # Check cache
            hit, cached_result = middleware.get_cached(tool.name, kwargs)
            if hit:
                return cached_result

            # Execute and cache
            result = original_handler(**kwargs)
            middleware.cache_result(tool.name, kwargs, result)
            return result

        # Create new tool with cached handler
        return ToolSpec.from_function(
            cached_handler,
            name=tool.name,
            description=tool.description,
            category=tool.category,
            tags=tool.tags,
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get caching statistics."""
        return {
            "enabled": self.config.tool_cache_enabled,
            "cacheable_tools": list(self.config.cacheable_tools),
            **self._cache.get_stats(),
        }

    def clear_cache(self) -> int:
        """Clear the tool cache."""
        return self._cache.clear()

    def get_tools(self) -> List[ToolSpec]:
        """Get cache management tools."""
        middleware = self

        def get_cache_stats() -> Dict[str, Any]:
            """
            Get caching statistics.

            Returns cache hit rates and entry counts.
            """
            return middleware.get_stats()

        def clear_tool_cache() -> Dict[str, Any]:
            """
            Clear all cached tool results.

            Returns count of entries cleared.
            """
            count = middleware.clear_cache()
            return {"status": "cleared", "entries_removed": count}

        return [
            ToolSpec.from_function(
                get_cache_stats,
                name="get_cache_stats",
                description="Get caching statistics including hit rates",
                category="system",
                tags=["cache", "stats"],
            ),
            ToolSpec.from_function(
                clear_tool_cache,
                name="clear_tool_cache",
                description="Clear all cached tool results",
                category="system",
                tags=["cache", "clear"],
            ),
        ]

    def get_system_prompt_segment(self) -> str:
        """System prompt segment about caching."""
        if not self.config.tool_cache_enabled:
            return ""

        tools = ", ".join(sorted(self.config.cacheable_tools))
        return f"""
## Tool Caching

Some tool results are cached for {self.config.tool_cache_ttl} seconds:
{tools}

Cache is automatic - repeated calls with same arguments return cached results.
Use clear_tool_cache() if you need fresh data.
"""

    def get_state(self) -> Dict[str, Any]:
        """Get serializable state."""
        return {
            "stats": self.get_stats(),
        }

    def load_state(self, state: Dict[str, Any]) -> None:
        """Load state (cache is not restored)."""
        pass


def create_caching_middleware(
    prompt_cache_enabled: bool = True,
    tool_cache_enabled: bool = True,
    prompt_ttl: int = 300,
    tool_ttl: int = 60,
) -> Tuple[AnthropicPromptCachingMiddleware, ToolCachingMiddleware]:
    """
    Create caching middleware components.

    Args:
        prompt_cache_enabled: Enable prompt caching
        tool_cache_enabled: Enable tool result caching
        prompt_ttl: Prompt cache TTL in seconds
        tool_ttl: Tool cache TTL in seconds

    Returns:
        Tuple of (prompt_middleware, tool_middleware)
    """
    prompt_mw = AnthropicPromptCachingMiddleware(
        ttl_seconds=prompt_ttl,
        enabled=prompt_cache_enabled,
    )

    config = CacheConfig(
        prompt_cache_enabled=prompt_cache_enabled,
        prompt_cache_ttl=prompt_ttl,
        tool_cache_enabled=tool_cache_enabled,
        tool_cache_ttl=tool_ttl,
    )
    tool_mw = ToolCachingMiddleware(config=config)

    return prompt_mw, tool_mw
