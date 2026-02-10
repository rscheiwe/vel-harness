"""
Tests for custom tools parameter on VelHarness.

Tests that custom tools (ToolSpec instances or callables) can be
injected into VelHarness and are available to the agent.
"""

import pytest
from unittest.mock import MagicMock, patch, call

from vel import ToolSpec

from vel_harness import VelHarness


# --- Helpers ---


def my_search_tool(query: str) -> dict:
    """Search for information."""
    return {"results": [f"Result for: {query}"]}


def my_deploy_tool(service: str, version: str) -> dict:
    """Deploy a service to production."""
    return {"status": "deployed", "service": service, "version": version}


async def my_async_tool(url: str) -> dict:
    """Fetch data from a URL."""
    return {"content": f"Data from {url}"}


# --- Tests ---


class TestCustomToolsParam:
    """Tests for the tools parameter on VelHarness."""

    @pytest.fixture
    def mock_agent(self):
        """Mock vel Agent to capture tools passed to it."""
        with patch("vel_harness.factory.Agent") as MockAgent:
            mock_instance = MagicMock()
            MockAgent.return_value = mock_instance
            yield MockAgent

    def test_no_tools_by_default(self, mock_agent):
        """Test no custom tools by default."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
        )
        assert harness._custom_tools == []

    def test_tools_stored(self, mock_agent):
        """Test tools list is stored on harness."""
        tool = ToolSpec.from_function(my_search_tool)
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            tools=[tool],
        )
        assert len(harness._custom_tools) == 1
        assert harness._custom_tools[0] is tool

    def test_toolspec_passed_to_agent(self, mock_agent):
        """Test ToolSpec instances are included in agent's tools."""
        search_tool = ToolSpec.from_function(
            my_search_tool,
            name="search",
            description="Search for information",
        )
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            tools=[search_tool],
        )

        # Agent() was called with tools list
        agent_call = mock_agent.call_args
        tools_arg = agent_call.kwargs.get("tools") or agent_call[1].get("tools")
        tool_names = [t.name for t in tools_arg]
        assert "search" in tool_names

    def test_callable_auto_wrapped(self, mock_agent):
        """Test callable functions are auto-wrapped as ToolSpec."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            tools=[my_search_tool],
        )

        agent_call = mock_agent.call_args
        tools_arg = agent_call.kwargs.get("tools") or agent_call[1].get("tools")
        tool_names = [t.name for t in tools_arg]
        assert "my_search_tool" in tool_names

    def test_multiple_tools(self, mock_agent):
        """Test multiple custom tools are all included."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            tools=[my_search_tool, my_deploy_tool],
        )

        agent_call = mock_agent.call_args
        tools_arg = agent_call.kwargs.get("tools") or agent_call[1].get("tools")
        tool_names = [t.name for t in tools_arg]
        assert "my_search_tool" in tool_names
        assert "my_deploy_tool" in tool_names

    def test_async_callable_wrapped(self, mock_agent):
        """Test async callable is wrapped as ToolSpec."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            tools=[my_async_tool],
        )

        agent_call = mock_agent.call_args
        tools_arg = agent_call.kwargs.get("tools") or agent_call[1].get("tools")
        tool_names = [t.name for t in tools_arg]
        assert "my_async_tool" in tool_names

    def test_mixed_toolspec_and_callable(self, mock_agent):
        """Test mixing ToolSpec and callable in tools list."""
        named_tool = ToolSpec.from_function(
            my_search_tool,
            name="custom_search",
            description="Custom search tool",
        )
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            tools=[named_tool, my_deploy_tool],
        )

        agent_call = mock_agent.call_args
        tools_arg = agent_call.kwargs.get("tools") or agent_call[1].get("tools")
        tool_names = [t.name for t in tools_arg]
        assert "custom_search" in tool_names
        assert "my_deploy_tool" in tool_names

    def test_custom_tools_alongside_middleware_tools(self, mock_agent):
        """Test custom tools coexist with middleware tools."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            tools=[my_search_tool],
            planning=True,
        )

        agent_call = mock_agent.call_args
        tools_arg = agent_call.kwargs.get("tools") or agent_call[1].get("tools")
        tool_names = [t.name for t in tools_arg]
        # Custom tool present
        assert "my_search_tool" in tool_names
        # Middleware tools also present (planning adds write_todos, read_todos)
        assert "write_todos" in tool_names

    def test_invalid_tool_type_raises(self, mock_agent):
        """Test passing invalid tool type raises TypeError."""
        with pytest.raises(TypeError, match="must be a ToolSpec or callable"):
            VelHarness(
                model={"provider": "anthropic", "model": "test"},
                tools=["not_a_tool"],
            )

    def test_empty_tools_list(self, mock_agent):
        """Test empty tools list is fine."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            tools=[],
        )
        assert harness._custom_tools == []

    def test_tools_none(self, mock_agent):
        """Test tools=None is fine (default)."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            tools=None,
        )
        assert harness._custom_tools == []


class TestCustomToolsWithMiddleware:
    """Tests for custom tools interacting with middleware wrapping."""

    @pytest.fixture
    def mock_agent(self):
        with patch("vel_harness.factory.Agent") as MockAgent:
            mock_instance = MagicMock()
            MockAgent.return_value = mock_instance
            yield MockAgent

    def test_tools_with_hooks(self, mock_agent):
        """Test custom tools get wrapped with hooks."""
        from vel_harness.hooks import HookMatcher

        hook_calls = []

        async def track_hook(event):
            hook_calls.append(event.tool_name)

        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            tools=[my_search_tool],
            hooks={
                "post_tool_use": [HookMatcher(handler=track_hook)],
            },
        )

        # Custom tool should be in the agent's tools
        agent_call = mock_agent.call_args
        tools_arg = agent_call.kwargs.get("tools") or agent_call[1].get("tools")
        tool_names = [t.name for t in tools_arg]
        assert "my_search_tool" in tool_names

    def test_tool_count_with_custom_tools(self, mock_agent):
        """Test that custom tools add to the total tool count."""
        # Without custom tools
        harness1 = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            planning=True,
        )
        call1 = mock_agent.call_args
        tools1 = call1.kwargs.get("tools") or call1[1].get("tools")
        count_without = len(tools1)

        mock_agent.reset_mock()

        # With custom tools
        harness2 = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            planning=True,
            tools=[my_search_tool, my_deploy_tool],
        )
        call2 = mock_agent.call_args
        tools2 = call2.kwargs.get("tools") or call2[1].get("tools")
        count_with = len(tools2)

        assert count_with == count_without + 2
