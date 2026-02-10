"""
Tests for Web Search Tools
"""

import pytest
from unittest.mock import MagicMock, patch

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


class TestSearchResult:
    """Test SearchResult dataclass."""

    def test_basic_result(self):
        """Test creating a basic search result."""
        result = SearchResult(
            title="Test Page",
            url="https://example.com",
            snippet="This is a test page.",
        )
        assert result.title == "Test Page"
        assert result.url == "https://example.com"
        assert result.snippet == "This is a test page."
        assert result.raw_content is None

    def test_result_with_content(self):
        """Test result with raw content."""
        result = SearchResult(
            title="Test Page",
            url="https://example.com",
            snippet="Summary",
            raw_content="Full page content here...",
            score=0.95,
        )
        assert result.raw_content == "Full page content here..."
        assert result.score == 0.95


class TestSearchResponse:
    """Test SearchResponse dataclass."""

    def test_basic_response(self):
        """Test creating a basic search response."""
        results = [
            SearchResult(
                title="Result 1",
                url="https://example.com/1",
                snippet="First result",
            ),
            SearchResult(
                title="Result 2",
                url="https://example.com/2",
                snippet="Second result",
            ),
        ]
        response = SearchResponse(
            query="test query",
            results=results,
        )
        assert response.query == "test query"
        assert len(response.results) == 2
        assert response.answer is None

    def test_response_with_answer(self):
        """Test response with AI answer."""
        response = SearchResponse(
            query="What is Python?",
            results=[],
            answer="Python is a programming language.",
        )
        assert response.answer == "Python is a programming language."


class TestMockWebSearchProvider:
    """Test MockWebSearchProvider class."""

    @pytest.fixture
    def provider(self):
        """Create a mock provider."""
        return MockWebSearchProvider()

    def test_default_search(self, provider):
        """Test search returns default mock results."""
        response = provider.search("test query")
        assert response.query == "test query"
        assert len(response.results) == 1
        assert "test query" in response.results[0].title

    def test_custom_mock_results(self, provider):
        """Test adding custom mock results."""
        provider.add_mock_result("python tutorial", [
            {
                "title": "Learn Python",
                "url": "https://python.org/tutorial",
                "content": "A great Python tutorial",
            },
            {
                "title": "Python Docs",
                "url": "https://docs.python.org",
                "content": "Official Python documentation",
            },
        ])

        response = provider.search("python tutorial")
        assert len(response.results) == 2
        assert response.results[0].title == "Learn Python"

    def test_case_insensitive_query(self, provider):
        """Test queries are case insensitive."""
        provider.add_mock_result("python", [
            {"title": "Python", "url": "https://python.org", "content": "Python.org"},
        ])

        response1 = provider.search("python")
        response2 = provider.search("PYTHON")
        response3 = provider.search("Python")

        assert len(response1.results) == 1
        assert len(response2.results) == 1
        assert len(response3.results) == 1

    def test_max_results(self, provider):
        """Test max_results limits output."""
        provider.add_mock_result("many results", [
            {"title": f"Result {i}", "url": f"https://example.com/{i}", "content": f"Content {i}"}
            for i in range(10)
        ])

        response = provider.search("many results", max_results=3)
        assert len(response.results) == 3


class TestWebSearchProvider:
    """Test WebSearchProvider class."""

    def test_init_with_api_key(self):
        """Test initialization with API key."""
        provider = WebSearchProvider(api_key="test-key")
        assert provider.api_key == "test-key"

    def test_init_from_env(self):
        """Test initialization from environment."""
        with patch.dict("os.environ", {"TAVILY_API_KEY": "env-key"}):
            provider = WebSearchProvider()
            assert provider.api_key == "env-key"

    def test_get_client_without_key_raises(self):
        """Test getting client without API key raises error."""
        with patch.dict("os.environ", {}, clear=True):
            provider = WebSearchProvider()
            provider.api_key = None
            with pytest.raises(WebSearchError, match="API key required"):
                provider._get_client()

    def test_get_client_without_tavily_raises(self):
        """Test getting client without tavily installed raises error."""
        provider = WebSearchProvider(api_key="test-key")
        with patch.dict("sys.modules", {"tavily": None}):
            with pytest.raises(WebSearchError, match="Tavily is not installed"):
                provider._get_client()


class TestCreateWebSearchTool:
    """Test create_web_search_tool function."""

    @pytest.fixture
    def mock_provider(self):
        """Create a mock provider."""
        provider = MockWebSearchProvider()
        provider.add_mock_result("current events", [
            {
                "title": "Today's News",
                "url": "https://news.example.com",
                "content": "Latest news and events",
            },
        ])
        return provider

    def test_create_tool(self, mock_provider):
        """Test creating web search tool."""
        tool = create_web_search_tool(provider=mock_provider)
        assert tool.name == "web_search"
        assert "research" in tool.category

    def test_tool_execution(self, mock_provider):
        """Test executing web search tool."""
        tool = create_web_search_tool(provider=mock_provider)

        result = tool._handler(query="current events")
        assert result["query"] == "current events"
        assert len(result["results"]) == 1
        assert result["results"][0]["title"] == "Today's News"

    def test_tool_max_results(self, mock_provider):
        """Test max_results parameter."""
        mock_provider.add_mock_result("many", [
            {"title": f"R{i}", "url": f"http://x.com/{i}", "content": f"C{i}"}
            for i in range(10)
        ])
        tool = create_web_search_tool(provider=mock_provider)

        result = tool._handler(query="many", max_results=3)
        assert len(result["results"]) == 3

    def test_tool_invalid_topic(self, mock_provider):
        """Test invalid topic defaults to general."""
        tool = create_web_search_tool(provider=mock_provider)

        # Should not raise, should use default
        result = tool._handler(query="test", topic="invalid")
        assert "error" not in result


class TestCreateWebFetchTool:
    """Test create_web_fetch_tool function."""

    @pytest.fixture
    def mock_provider(self):
        """Create a mock provider."""
        return MockWebSearchProvider()

    def test_create_tool(self, mock_provider):
        """Test creating web fetch tool."""
        tool = create_web_fetch_tool(provider=mock_provider)
        assert tool.name == "web_fetch"
        assert "research" in tool.category

    def test_tool_fetch(self, mock_provider):
        """Test fetching a URL."""
        tool = create_web_fetch_tool(provider=mock_provider)

        result = tool._handler(url="https://example.com")
        assert result["url"] == "https://example.com"
        # Mock will return generic result
        assert "success" in result


class TestGetWebTools:
    """Test get_web_tools function."""

    def test_returns_all_tools(self):
        """Test returning all web tools."""
        provider = MockWebSearchProvider()
        tools = get_web_tools(provider=provider)

        assert len(tools) == 2
        tool_names = [t.name for t in tools]
        assert "web_search" in tool_names
        assert "web_fetch" in tool_names


class TestWebSearchIntegration:
    """Integration tests for web search."""

    def test_full_search_workflow(self):
        """Test full search workflow with mock."""
        provider = MockWebSearchProvider()
        provider.add_mock_result("python programming", [
            {
                "title": "Python.org",
                "url": "https://python.org",
                "content": "Official Python website",
            },
            {
                "title": "Python Tutorial",
                "url": "https://docs.python.org/tutorial",
                "content": "Learn Python programming",
            },
        ])

        tool = create_web_search_tool(provider=provider)
        result = tool._handler(
            query="python programming",
            max_results=5,
            topic="general",
        )

        assert result["query"] == "python programming"
        assert result["count"] == 2
        assert result["results"][0]["title"] == "Python.org"

    def test_search_error_handling(self):
        """Test error handling in search."""
        # Create provider that will fail
        provider = WebSearchProvider(api_key=None)

        tool = create_web_search_tool(provider=provider)
        result = tool._handler(query="test")

        # Should return error instead of raising
        assert "error" in result


class TestWebSearchProviderAsync:
    """Test async methods of WebSearchProvider."""

    @pytest.mark.asyncio
    async def test_search_async_mock(self):
        """Test async search with mock provider."""
        provider = MockWebSearchProvider()
        response = await provider.search_async("test query")
        assert response.query == "test query"
        assert len(response.results) >= 1
