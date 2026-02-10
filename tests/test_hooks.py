"""
Tests for Hooks System (WS2)

Tests the control hook system including:
- HookResult allow/deny/modify
- HookMatcher regex matching
- HookEngine dispatch logic
- Pre-tool hooks blocking/modifying execution
- Post-tool hooks (informational)
- Timeout handling
- Multiple matchers (first deny wins)
- Factory and VelHarness integration
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from vel_harness.hooks import (
    HookEngine,
    HookMatcher,
    HookResult,
    PreToolUseEvent,
    PostToolUseEvent,
    PostToolUseFailureEvent,
)
from vel_harness.factory import create_deep_agent
from vel_harness import VelHarness


# --- HookResult Tests ---


class TestHookResult:
    """Tests for HookResult dataclass."""

    def test_default_allow(self):
        """Test default result is allow."""
        result = HookResult()
        assert result.decision == "allow"
        assert result.updated_input is None
        assert result.reason is None

    def test_deny(self):
        """Test deny result."""
        result = HookResult(decision="deny", reason="Not allowed")
        assert result.decision == "deny"
        assert result.reason == "Not allowed"

    def test_modify(self):
        """Test modify result."""
        result = HookResult(
            decision="modify",
            updated_input={"command": "safe-command"},
        )
        assert result.decision == "modify"
        assert result.updated_input == {"command": "safe-command"}


# --- HookMatcher Tests ---


class TestHookMatcher:
    """Tests for HookMatcher regex matching."""

    def test_none_matches_all(self):
        """Test None matcher matches everything."""
        matcher = HookMatcher(matcher=None)
        assert matcher.matches("write_file") is True
        assert matcher.matches("read_file") is True
        assert matcher.matches("any_tool") is True

    def test_exact_match(self):
        """Test exact tool name match."""
        matcher = HookMatcher(matcher="write_file")
        assert matcher.matches("write_file") is True
        assert matcher.matches("read_file") is False

    def test_regex_alternation(self):
        """Test regex alternation pattern."""
        matcher = HookMatcher(matcher="write_file|edit_file|delete_file")
        assert matcher.matches("write_file") is True
        assert matcher.matches("edit_file") is True
        assert matcher.matches("delete_file") is True
        assert matcher.matches("read_file") is False

    def test_regex_wildcard(self):
        """Test regex wildcard pattern."""
        matcher = HookMatcher(matcher="execute.*")
        assert matcher.matches("execute") is True
        assert matcher.matches("execute_python") is True
        assert matcher.matches("execute_sql") is True
        assert matcher.matches("write_file") is False

    def test_invalid_regex_no_match(self):
        """Test invalid regex doesn't match (fails gracefully)."""
        matcher = HookMatcher(matcher="[invalid")
        assert matcher.matches("anything") is False

    def test_default_timeout(self):
        """Test default timeout is 30s."""
        matcher = HookMatcher()
        assert matcher.timeout == 30.0

    def test_custom_timeout(self):
        """Test custom timeout."""
        matcher = HookMatcher(timeout=5.0)
        assert matcher.timeout == 5.0


# --- Event Types Tests ---


class TestEventTypes:
    """Tests for hook event dataclasses."""

    def test_pre_tool_use_event(self):
        """Test PreToolUseEvent creation."""
        event = PreToolUseEvent(
            tool_name="write_file",
            tool_input={"path": "/test.txt", "content": "hello"},
            tool_call_id="tc_123",
            step=3,
        )
        assert event.tool_name == "write_file"
        assert event.tool_input["path"] == "/test.txt"
        assert event.tool_call_id == "tc_123"
        assert event.step == 3

    def test_post_tool_use_event(self):
        """Test PostToolUseEvent creation."""
        event = PostToolUseEvent(
            tool_name="read_file",
            tool_input={"path": "/test.txt"},
            tool_output="file contents",
            duration_ms=42.5,
        )
        assert event.tool_name == "read_file"
        assert event.tool_output == "file contents"
        assert event.duration_ms == 42.5

    def test_post_tool_use_failure_event(self):
        """Test PostToolUseFailureEvent creation."""
        event = PostToolUseFailureEvent(
            tool_name="execute",
            tool_input={"command": "bad-cmd"},
            error="Command not found",
            duration_ms=10.0,
        )
        assert event.error == "Command not found"


# --- HookEngine Tests ---


class TestHookEngine:
    """Tests for HookEngine dispatch logic."""

    def test_empty_engine(self):
        """Test engine with no hooks allows everything."""
        engine = HookEngine()
        assert engine.has_hooks("pre_tool_use") is False

    def test_has_hooks(self):
        """Test has_hooks returns True when hooks are registered."""
        engine = HookEngine(hooks={
            "pre_tool_use": [HookMatcher(handler=AsyncMock())],
        })
        assert engine.has_hooks("pre_tool_use") is True
        assert engine.has_hooks("post_tool_use") is False

    @pytest.mark.asyncio
    async def test_pre_hook_allow(self):
        """Test pre-tool hook that allows execution."""
        handler = AsyncMock(return_value=HookResult(decision="allow"))
        engine = HookEngine(hooks={
            "pre_tool_use": [HookMatcher(handler=handler)],
        })

        event = PreToolUseEvent(tool_name="write_file", tool_input={"path": "/test"})
        result = await engine.run_pre_tool_hooks(event)

        assert result.decision == "allow"
        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_pre_hook_deny(self):
        """Test pre-tool hook that denies execution."""
        handler = AsyncMock(
            return_value=HookResult(decision="deny", reason="Blocked")
        )
        engine = HookEngine(hooks={
            "pre_tool_use": [HookMatcher(handler=handler)],
        })

        event = PreToolUseEvent(tool_name="write_file", tool_input={"path": "/test"})
        result = await engine.run_pre_tool_hooks(event)

        assert result.decision == "deny"
        assert result.reason == "Blocked"

    @pytest.mark.asyncio
    async def test_pre_hook_modify(self):
        """Test pre-tool hook that modifies input."""
        handler = AsyncMock(return_value=HookResult(
            decision="modify",
            updated_input={"path": "/safe/test"},
        ))
        engine = HookEngine(hooks={
            "pre_tool_use": [HookMatcher(handler=handler)],
        })

        event = PreToolUseEvent(tool_name="write_file", tool_input={"path": "/test"})
        result = await engine.run_pre_tool_hooks(event)

        assert result.decision == "modify"
        assert result.updated_input == {"path": "/safe/test"}

    @pytest.mark.asyncio
    async def test_pre_hook_first_deny_wins(self):
        """Test that first deny wins when multiple matchers are registered."""
        allow_handler = AsyncMock(return_value=HookResult(decision="allow"))
        deny_handler = AsyncMock(
            return_value=HookResult(decision="deny", reason="Blocked by second")
        )
        third_handler = AsyncMock(return_value=HookResult(decision="allow"))

        engine = HookEngine(hooks={
            "pre_tool_use": [
                HookMatcher(handler=allow_handler),
                HookMatcher(handler=deny_handler),
                HookMatcher(handler=third_handler),
            ],
        })

        event = PreToolUseEvent(tool_name="write_file", tool_input={})
        result = await engine.run_pre_tool_hooks(event)

        assert result.decision == "deny"
        assert result.reason == "Blocked by second"
        # Third handler should NOT be called (short-circuit on deny)
        third_handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_pre_hook_matcher_filters(self):
        """Test that matcher regex filters which hooks run."""
        write_handler = AsyncMock(
            return_value=HookResult(decision="deny", reason="No writes")
        )
        engine = HookEngine(hooks={
            "pre_tool_use": [
                HookMatcher(matcher="write_file|edit_file", handler=write_handler),
            ],
        })

        # Should deny write_file
        event1 = PreToolUseEvent(tool_name="write_file", tool_input={})
        result1 = await engine.run_pre_tool_hooks(event1)
        assert result1.decision == "deny"

        # Should allow read_file (doesn't match)
        event2 = PreToolUseEvent(tool_name="read_file", tool_input={})
        result2 = await engine.run_pre_tool_hooks(event2)
        assert result2.decision == "allow"

    @pytest.mark.asyncio
    async def test_pre_hook_none_return_treated_as_allow(self):
        """Test that returning None from handler is treated as allow."""
        handler = AsyncMock(return_value=None)
        engine = HookEngine(hooks={
            "pre_tool_use": [HookMatcher(handler=handler)],
        })

        event = PreToolUseEvent(tool_name="write_file", tool_input={})
        result = await engine.run_pre_tool_hooks(event)

        assert result.decision == "allow"

    @pytest.mark.asyncio
    async def test_post_hook_called(self):
        """Test post-tool hook is called."""
        handler = AsyncMock()
        engine = HookEngine(hooks={
            "post_tool_use": [HookMatcher(handler=handler)],
        })

        event = PostToolUseEvent(
            tool_name="read_file",
            tool_input={"path": "/test"},
            tool_output="contents",
            duration_ms=10.0,
        )
        await engine.run_post_tool_hooks(event)

        handler.assert_called_once()
        call_event = handler.call_args[0][0]
        assert call_event.tool_name == "read_file"
        assert call_event.tool_output == "contents"

    @pytest.mark.asyncio
    async def test_post_failure_hook_called(self):
        """Test post-tool-failure hook is called."""
        handler = AsyncMock()
        engine = HookEngine(hooks={
            "post_tool_use_failure": [HookMatcher(handler=handler)],
        })

        event = PostToolUseFailureEvent(
            tool_name="execute",
            tool_input={"command": "bad"},
            error="Command failed",
        )
        await engine.run_post_tool_failure_hooks(event)

        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_hook_timeout_denies(self):
        """Test that a timed-out hook results in deny."""
        async def slow_handler(event):
            await asyncio.sleep(10)
            return HookResult(decision="allow")

        engine = HookEngine(hooks={
            "pre_tool_use": [
                HookMatcher(handler=slow_handler, timeout=0.01),
            ],
        })

        event = PreToolUseEvent(tool_name="write_file", tool_input={})
        result = await engine.run_pre_tool_hooks(event)

        assert result.decision == "deny"
        assert "timed out" in result.reason

    @pytest.mark.asyncio
    async def test_hook_exception_treated_as_allow(self):
        """Test that a hook raising an exception doesn't block execution."""
        async def bad_handler(event):
            raise ValueError("Hook crashed")

        engine = HookEngine(hooks={
            "pre_tool_use": [HookMatcher(handler=bad_handler)],
        })

        event = PreToolUseEvent(tool_name="write_file", tool_input={})
        result = await engine.run_pre_tool_hooks(event)

        # Exception should not block — treated as allow
        assert result.decision == "allow"

    @pytest.mark.asyncio
    async def test_sync_handler_supported(self):
        """Test that synchronous handlers work."""
        def sync_handler(event):
            return HookResult(decision="deny", reason="Sync deny")

        engine = HookEngine(hooks={
            "pre_tool_use": [HookMatcher(handler=sync_handler)],
        })

        event = PreToolUseEvent(tool_name="write_file", tool_input={})
        result = await engine.run_pre_tool_hooks(event)

        assert result.decision == "deny"
        assert result.reason == "Sync deny"

    @pytest.mark.asyncio
    async def test_modify_propagates_to_subsequent_hooks(self):
        """Test that modify updates input for subsequent hooks to see."""
        calls = []

        async def modifier(event):
            calls.append(("modifier", dict(event.tool_input)))
            return HookResult(
                decision="modify",
                updated_input={"command": "modified-cmd"},
            )

        async def observer(event):
            calls.append(("observer", dict(event.tool_input)))
            return HookResult(decision="allow")

        engine = HookEngine(hooks={
            "pre_tool_use": [
                HookMatcher(handler=modifier),
                HookMatcher(handler=observer),
            ],
        })

        event = PreToolUseEvent(
            tool_name="execute",
            tool_input={"command": "original-cmd"},
        )
        result = await engine.run_pre_tool_hooks(event)

        assert result.decision == "modify"
        # Observer should see the modified input
        assert calls[0] == ("modifier", {"command": "original-cmd"})
        assert calls[1] == ("observer", {"command": "modified-cmd"})

    @pytest.mark.asyncio
    async def test_no_hooks_returns_allow(self):
        """Test that no hooks for an event returns allow."""
        engine = HookEngine(hooks={
            "post_tool_use": [HookMatcher(handler=AsyncMock())],
        })

        event = PreToolUseEvent(tool_name="write_file", tool_input={})
        result = await engine.run_pre_tool_hooks(event)

        assert result.decision == "allow"


# --- Factory Integration Tests ---


class TestFactoryHookWiring:
    """Tests that hooks are wired into the factory."""

    def test_no_hooks_by_default(self):
        """Test that factory works without hooks."""
        agent = create_deep_agent()
        # Should create without errors
        assert agent is not None

    def test_with_hook_engine(self):
        """Test that factory accepts a hook engine."""
        handler = AsyncMock(return_value=HookResult(decision="allow"))
        engine = HookEngine(hooks={
            "pre_tool_use": [HookMatcher(handler=handler)],
        })

        agent = create_deep_agent(hook_engine=engine)
        assert agent is not None
        # Tools should still exist after wrapping
        tool_names = [t.name for t in agent.get_all_tools()]
        assert len(tool_names) > 0


# --- VelHarness Integration Tests ---


class TestVelHarnessHooks:
    """Tests for hooks through VelHarness constructor."""

    @pytest.fixture
    def mock_agent(self):
        """Create a mock Vel Agent."""
        with patch("vel_harness.factory.Agent") as MockAgent:
            mock_instance = MagicMock()
            MockAgent.return_value = mock_instance
            yield MockAgent

    def test_no_hooks_by_default(self, mock_agent):
        """Test VelHarness defaults to no hooks."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
        )

        assert harness.hook_engine is None

    def test_with_hooks(self, mock_agent):
        """Test VelHarness with hooks parameter."""
        handler = AsyncMock(return_value=HookResult(decision="allow"))
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            hooks={
                "pre_tool_use": [
                    HookMatcher(matcher="write_file", handler=handler),
                ],
            },
        )

        assert harness.hook_engine is not None
        assert harness.hook_engine.has_hooks("pre_tool_use") is True

    def test_hooks_with_caching_and_retry(self, mock_agent):
        """Test hooks coexist with caching and retry."""
        handler = AsyncMock(return_value=HookResult(decision="allow"))
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            caching=True,
            retry=True,
            hooks={
                "pre_tool_use": [HookMatcher(handler=handler)],
            },
        )

        assert harness.hook_engine is not None
        assert harness.config.caching.enabled is True
        assert harness.config.retry.enabled is True
