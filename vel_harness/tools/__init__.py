"""
Vel Harness Tools

Additional tools for deep agent capabilities.
"""

from vel_harness.tools.web_search import (
    WebSearchProvider,
    MockWebSearchProvider,
    WebSearchError,
    SearchResult,
    SearchResponse,
    create_web_search_tool,
    create_web_fetch_tool,
    get_web_tools,
)

__all__ = [
    "WebSearchProvider",
    "MockWebSearchProvider",
    "WebSearchError",
    "SearchResult",
    "SearchResponse",
    "create_web_search_tool",
    "create_web_fetch_tool",
    "get_web_tools",
]
