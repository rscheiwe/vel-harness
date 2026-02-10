"""
Web Search Tool

Built-in web search using Tavily API for current information retrieval.
"""

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from vel import ToolSpec


@dataclass
class SearchResult:
    """A single search result."""

    title: str
    url: str
    snippet: str
    raw_content: Optional[str] = None
    score: float = 0.0


@dataclass
class SearchResponse:
    """Response from a web search."""

    query: str
    results: List[SearchResult]
    answer: Optional[str] = None  # Tavily can provide a direct answer


class WebSearchError(Exception):
    """Error during web search."""

    pass


class WebSearchProvider:
    """Web search provider using Tavily API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        """Initialize the web search provider.

        Args:
            api_key: Tavily API key (or TAVILY_API_KEY env var)
            base_url: Optional custom API base URL
        """
        self.api_key = api_key or os.environ.get("TAVILY_API_KEY")
        self.base_url = base_url
        self._client = None

    def _get_client(self):
        """Get or create Tavily client."""
        if self._client is not None:
            return self._client

        if not self.api_key:
            raise WebSearchError(
                "Tavily API key required. Set TAVILY_API_KEY env var or pass api_key."
            )

        try:
            from tavily import TavilyClient

            self._client = TavilyClient(api_key=self.api_key)
            return self._client
        except ImportError:
            raise WebSearchError(
                "Tavily is not installed. Install with: pip install tavily-python"
            )

    def search(
        self,
        query: str,
        max_results: int = 5,
        topic: Literal["general", "news", "finance"] = "general",
        include_raw_content: bool = False,
        include_answer: bool = False,
        search_depth: Literal["basic", "advanced"] = "basic",
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
    ) -> SearchResponse:
        """Search the web for information.

        Args:
            query: Search query
            max_results: Maximum number of results (1-10)
            topic: Search topic category
            include_raw_content: Include full page content
            include_answer: Include AI-generated answer
            search_depth: Search depth (basic or advanced)
            include_domains: Only search these domains
            exclude_domains: Exclude these domains

        Returns:
            SearchResponse with results
        """
        client = self._get_client()

        try:
            # Build search kwargs
            search_kwargs: Dict[str, Any] = {
                "query": query,
                "max_results": min(max_results, 10),
                "topic": topic,
                "include_raw_content": include_raw_content,
                "include_answer": include_answer,
                "search_depth": search_depth,
            }

            if include_domains:
                search_kwargs["include_domains"] = include_domains
            if exclude_domains:
                search_kwargs["exclude_domains"] = exclude_domains

            response = client.search(**search_kwargs)

            # Parse results
            results = []
            for r in response.get("results", []):
                results.append(
                    SearchResult(
                        title=r.get("title", ""),
                        url=r.get("url", ""),
                        snippet=r.get("content", ""),
                        raw_content=r.get("raw_content") if include_raw_content else None,
                        score=r.get("score", 0.0),
                    )
                )

            return SearchResponse(
                query=query,
                results=results,
                answer=response.get("answer") if include_answer else None,
            )
        except Exception as e:
            raise WebSearchError(f"Search failed: {str(e)}")

    async def search_async(
        self,
        query: str,
        **kwargs: Any,
    ) -> SearchResponse:
        """Async version of search."""
        # Tavily client is sync, so we run in executor
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self.search(query, **kwargs)
        )


class MockWebSearchProvider(WebSearchProvider):
    """Mock web search provider for testing."""

    def __init__(self):
        super().__init__(api_key="mock")
        self._mock_results: Dict[str, List[Dict[str, str]]] = {}

    def add_mock_result(
        self,
        query: str,
        results: List[Dict[str, str]],
    ) -> None:
        """Add mock results for a query."""
        self._mock_results[query.lower()] = results

    def search(
        self,
        query: str,
        max_results: int = 5,
        **kwargs: Any,
    ) -> SearchResponse:
        """Search with mock results."""
        query_lower = query.lower()

        # Check for exact match first
        if query_lower in self._mock_results:
            results = self._mock_results[query_lower]
        else:
            # Return default mock results
            results = [
                {
                    "title": f"Mock Result for: {query}",
                    "url": f"https://example.com/search?q={query.replace(' ', '+')}",
                    "content": f"This is a mock search result for the query: {query}",
                }
            ]

        return SearchResponse(
            query=query,
            results=[
                SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("content", ""),
                )
                for r in results[:max_results]
            ],
        )


def create_web_search_tool(
    api_key: Optional[str] = None,
    provider: Optional[WebSearchProvider] = None,
) -> ToolSpec:
    """Create web search tool using Tavily.

    Args:
        api_key: Tavily API key (or TAVILY_API_KEY env var)
        provider: Optional custom provider (for testing)

    Returns:
        ToolSpec for web search
    """
    search_provider = provider or WebSearchProvider(api_key=api_key)

    def web_search(
        query: str,
        max_results: int = 5,
        topic: str = "general",
        include_raw_content: bool = False,
    ) -> Dict[str, Any]:
        """
        Search the web for current information.

        Args:
            query: Search query
            max_results: Maximum number of results (1-10)
            topic: Search topic - "general", "news", or "finance"
            include_raw_content: Include full page content

        Returns:
            Search results with titles, URLs, and snippets
        """
        try:
            # Validate topic
            valid_topics = ("general", "news", "finance")
            if topic not in valid_topics:
                topic = "general"

            response = search_provider.search(
                query=query,
                max_results=max_results,
                topic=topic,  # type: ignore
                include_raw_content=include_raw_content,
            )

            return {
                "query": response.query,
                "results": [
                    {
                        "title": r.title,
                        "url": r.url,
                        "snippet": r.snippet,
                        "raw_content": r.raw_content if include_raw_content else None,
                    }
                    for r in response.results
                ],
                "count": len(response.results),
            }
        except WebSearchError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": f"Search failed: {str(e)}"}

    return ToolSpec.from_function(
        web_search,
        name="web_search",
        description="""
Search the web for current information.

Use for:
- Finding recent news and events
- Looking up current facts
- Researching topics
- Verifying information
- Getting up-to-date data
""",
        category="research",
        tags=["web", "search", "research", "internet"],
    )


def create_web_fetch_tool(
    api_key: Optional[str] = None,
    provider: Optional[WebSearchProvider] = None,
) -> ToolSpec:
    """Create web fetch tool for retrieving page content.

    Args:
        api_key: Tavily API key
        provider: Optional custom provider

    Returns:
        ToolSpec for fetching web pages
    """
    search_provider = provider or WebSearchProvider(api_key=api_key)

    def web_fetch(
        url: str,
        extract_content: bool = True,
    ) -> Dict[str, Any]:
        """
        Fetch content from a web page.

        Args:
            url: URL to fetch
            extract_content: Whether to extract main content

        Returns:
            Page content and metadata
        """
        try:
            # Use search with exact URL to get content
            response = search_provider.search(
                query=f"site:{url}",
                max_results=1,
                include_raw_content=extract_content,
            )

            if response.results:
                result = response.results[0]
                return {
                    "url": url,
                    "title": result.title,
                    "content": result.raw_content or result.snippet,
                    "success": True,
                }
            else:
                return {
                    "url": url,
                    "error": "Could not fetch page content",
                    "success": False,
                }
        except Exception as e:
            return {
                "url": url,
                "error": str(e),
                "success": False,
            }

    return ToolSpec.from_function(
        web_fetch,
        name="web_fetch",
        description="""
Fetch content from a specific web page.

Use for:
- Reading documentation pages
- Extracting content from articles
- Getting data from specific URLs
""",
        category="research",
        tags=["web", "fetch", "read", "url"],
    )


def get_web_tools(
    api_key: Optional[str] = None,
    provider: Optional[WebSearchProvider] = None,
) -> List[ToolSpec]:
    """Get all web-related tools.

    Args:
        api_key: Tavily API key
        provider: Optional custom provider

    Returns:
        List of web tools
    """
    return [
        create_web_search_tool(api_key=api_key, provider=provider),
        create_web_fetch_tool(api_key=api_key, provider=provider),
    ]
