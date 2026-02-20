"""
Tests for HarnessSession (WS7)

Tests the dynamic mid-conversation controls including:
- HarnessSession creation and defaults
- query() streaming with session_id persistence
- run() non-streaming wrapper
- set_model() with shorthand and full config
- interrupt() stops current generation
- set_reasoning() mode switching
- Async context manager lifecycle
- VelHarness.create_session() integration
- Session state (get_state, query_count)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from vel_harness.session import HarnessSession
from vel_harness.reasoning import ReasoningConfig
from vel_harness import VelHarness


# --- Helpers ---


async def async_iter(events):
    """Create an async iterator from a list of events."""
    for event in events:
        yield event


def make_mock_harness(model_cfg=None):
    """Create a mock VelHarness with a mock deep_agent."""
    harness = MagicMock()
    harness.deep_agent = MagicMock()
    harness.deep_agent.agent = MagicMock()
    harness.deep_agent.agent.model_cfg = model_cfg or {
        "provider": "anthropic",
        "model": "claude-sonnet-4-5-20250929",
    }
    harness._reasoning_config = None
    return harness


# --- HarnessSession Creation Tests ---


class TestSessionCreation:
    """Tests for HarnessSession initialization."""

    def test_default_session_id(self):
        """Test auto-generated session_id."""
        harness = make_mock_harness()
        session = HarnessSession(harness=harness)
        assert session.session_id is not None
        assert len(session.session_id) > 0

    def test_custom_session_id(self):
        """Test custom session_id."""
        harness = make_mock_harness()
        session = HarnessSession(harness=harness, session_id="my-session")
        assert session.session_id == "my-session"

    def test_harness_reference(self):
        """Test harness is stored."""
        harness = make_mock_harness()
        session = HarnessSession(harness=harness)
        assert session.harness is harness

    def test_initial_query_count(self):
        """Test query count starts at 0."""
        harness = make_mock_harness()
        session = HarnessSession(harness=harness)
        assert session.query_count == 0

    def test_initial_not_interrupted(self):
        """Test session starts not interrupted."""
        harness = make_mock_harness()
        session = HarnessSession(harness=harness)
        assert session.is_interrupted is False

    def test_model_property(self):
        """Test model property returns current model config."""
        model = {"provider": "anthropic", "model": "test-model"}
        harness = make_mock_harness(model_cfg=model)
        session = HarnessSession(harness=harness)
        assert session.model == model

    def test_unique_session_ids(self):
        """Test auto-generated session IDs are unique."""
        harness = make_mock_harness()
        s1 = HarnessSession(harness=harness)
        s2 = HarnessSession(harness=harness)
        assert s1.session_id != s2.session_id


# --- query() Streaming Tests ---


class TestQuery:
    """Tests for HarnessSession.query()."""

    @pytest.mark.asyncio
    async def test_basic_streaming(self):
        """Test basic streaming query."""
        harness = make_mock_harness()
        events = [
            {"type": "text-delta", "delta": "Hello "},
            {"type": "text-delta", "delta": "world"},
        ]
        harness.deep_agent.run_stream = MagicMock(return_value=async_iter(events))

        session = HarnessSession(harness=harness, session_id="test")

        collected = []
        async for event in session.query("Hi"):
            collected.append(event)

        assert len(collected) == 2
        assert collected[0]["delta"] == "Hello "
        assert collected[1]["delta"] == "world"

    @pytest.mark.asyncio
    async def test_session_id_passed_to_agent(self):
        """Test session_id is passed through to run_stream."""
        harness = make_mock_harness()
        call_kwargs = {}

        def mock_run_stream(**kwargs):
            call_kwargs.update(kwargs)
            return async_iter([{"type": "text-delta", "delta": "ok"}])

        harness.deep_agent.run_stream = mock_run_stream

        session = HarnessSession(harness=harness, session_id="persistent-id")

        async for _ in session.query("test"):
            pass

        assert call_kwargs["session_id"] == "persistent-id"

    @pytest.mark.asyncio
    async def test_context_passed_through(self):
        """Test context is passed to run_stream."""
        harness = make_mock_harness()
        call_kwargs = {}

        def mock_run_stream(**kwargs):
            call_kwargs.update(kwargs)
            return async_iter([{"type": "text-delta", "delta": "ok"}])

        harness.deep_agent.run_stream = mock_run_stream

        session = HarnessSession(harness=harness, session_id="test")
        async for _ in session.query("test", context={"key": "value"}):
            pass

        assert call_kwargs["context"] == {"key": "value"}

    @pytest.mark.asyncio
    async def test_query_count_increments(self):
        """Test query count increments with each query."""
        harness = make_mock_harness()
        harness.deep_agent.run_stream = MagicMock(
            return_value=async_iter([{"type": "text-delta", "delta": "ok"}])
        )

        session = HarnessSession(harness=harness)
        assert session.query_count == 0

        async for _ in session.query("first"):
            pass
        assert session.query_count == 1

        harness.deep_agent.run_stream = MagicMock(
            return_value=async_iter([{"type": "text-delta", "delta": "ok"}])
        )
        async for _ in session.query("second"):
            pass
        assert session.query_count == 2

    @pytest.mark.asyncio
    async def test_multiple_queries_same_session_id(self):
        """Test multiple queries use the same session_id."""
        harness = make_mock_harness()
        session_ids = []

        def mock_run_stream(**kwargs):
            session_ids.append(kwargs.get("session_id"))
            return async_iter([{"type": "text-delta", "delta": "ok"}])

        harness.deep_agent.run_stream = mock_run_stream

        session = HarnessSession(harness=harness, session_id="persistent")

        async for _ in session.query("first"):
            pass
        async for _ in session.query("second"):
            pass
        async for _ in session.query("third"):
            pass

        assert session_ids == ["persistent", "persistent", "persistent"]

    @pytest.mark.asyncio
    async def test_empty_stream(self):
        """Test query with empty stream."""
        harness = make_mock_harness()
        harness.deep_agent.run_stream = MagicMock(return_value=async_iter([]))

        session = HarnessSession(harness=harness)
        collected = []
        async for event in session.query("test"):
            collected.append(event)

        assert collected == []


class TestRoleWorkflow:
    """Tests for session-level role workflow helper."""

    @pytest.mark.asyncio
    async def test_run_role_workflow_passes_session_id(self):
        """Session helper should call harness workflow with the current session id."""
        harness = make_mock_harness()
        harness.run_role_workflow = AsyncMock(return_value={"status": "completed"})
        session = HarnessSession(harness=harness, session_id="abc123")

        out = await session.run_role_workflow("Improve reliability", include_critic=False)

        assert out["status"] == "completed"
        harness.run_role_workflow.assert_called_once_with(
            goal="Improve reliability",
            session_id="abc123",
            include_critic=False,
        )


# --- run() Non-Streaming Tests ---


class TestRun:
    """Tests for HarnessSession.run()."""

    @pytest.mark.asyncio
    async def test_run_collects_text(self):
        """Test run() collects text-delta events."""
        harness = make_mock_harness()
        harness.deep_agent.run_stream = MagicMock(return_value=async_iter([
            {"type": "text-delta", "delta": "Hello "},
            {"type": "text-delta", "delta": "world"},
        ]))

        session = HarnessSession(harness=harness)
        result = await session.run("test")
        assert result == "Hello world"

    @pytest.mark.asyncio
    async def test_run_returns_error_string(self):
        """Test run() returns error string for errors."""
        harness = make_mock_harness()
        harness.deep_agent.run_stream = MagicMock(return_value=async_iter([
            {"type": "error", "error": "Something went wrong"},
        ]))

        session = HarnessSession(harness=harness)
        result = await session.run("test")
        assert result == "[error: Something went wrong]"

    @pytest.mark.asyncio
    async def test_run_returns_interrupted(self):
        """Test run() returns interrupted string when interrupted."""
        harness = make_mock_harness()

        # Create an async generator that yields one event then checks interrupt
        async def slow_stream(**kwargs):
            yield {"type": "text-delta", "delta": "partial"}
            # Simulate interrupt being set during iteration
            yield {"type": "interrupted", "session_id": "test"}

        harness.deep_agent.run_stream = slow_stream

        session = HarnessSession(harness=harness, session_id="test")
        # We can't easily interrupt mid-stream in a test, but we can test
        # that interrupt events are handled
        result = await session.run("test")
        assert result == "[interrupted]"

    @pytest.mark.asyncio
    async def test_run_empty_stream(self):
        """Test run() with empty stream returns empty string."""
        harness = make_mock_harness()
        harness.deep_agent.run_stream = MagicMock(return_value=async_iter([]))

        session = HarnessSession(harness=harness)
        result = await session.run("test")
        assert result == ""


# --- set_model() Tests ---


class TestSetModel:
    """Tests for HarnessSession.set_model()."""

    def test_set_model_shorthand_haiku(self):
        """Test set_model with 'haiku' shorthand."""
        harness = make_mock_harness()
        session = HarnessSession(harness=harness)

        session.set_model("haiku")
        assert harness.deep_agent.agent.model_cfg == {
            "provider": "anthropic",
            "model": "claude-haiku-4-5-20251001",
        }

    def test_set_model_shorthand_sonnet(self):
        """Test set_model with 'sonnet' shorthand."""
        harness = make_mock_harness()
        session = HarnessSession(harness=harness)

        session.set_model("sonnet")
        assert harness.deep_agent.agent.model_cfg == {
            "provider": "anthropic",
            "model": "claude-sonnet-4-5-20250929",
        }

    def test_set_model_shorthand_opus(self):
        """Test set_model with 'opus' shorthand."""
        harness = make_mock_harness()
        session = HarnessSession(harness=harness)

        session.set_model("opus")
        assert harness.deep_agent.agent.model_cfg == {
            "provider": "anthropic",
            "model": "claude-opus-4-6",
        }

    def test_set_model_full_config_dict(self):
        """Test set_model with full config dict."""
        harness = make_mock_harness()
        session = HarnessSession(harness=harness)

        model = {"provider": "openai", "model": "gpt-4"}
        session.set_model(model)
        assert harness.deep_agent.agent.model_cfg == model

    def test_set_model_full_model_id_string(self):
        """Test set_model with full model ID string."""
        harness = make_mock_harness()
        session = HarnessSession(harness=harness)

        session.set_model("claude-3-5-sonnet-20241022")
        assert harness.deep_agent.agent.model_cfg == {
            "provider": "anthropic",
            "model": "claude-3-5-sonnet-20241022",
        }

    def test_set_model_inherit_raises(self):
        """Test set_model with 'inherit' raises ValueError."""
        harness = make_mock_harness()
        session = HarnessSession(harness=harness)

        with pytest.raises(ValueError, match="Cannot resolve model"):
            session.set_model("inherit")

    def test_set_model_updates_model_property(self):
        """Test set_model updates the model property."""
        harness = make_mock_harness()
        session = HarnessSession(harness=harness)

        original = session.model
        session.set_model("haiku")
        assert session.model != original
        assert session.model["model"] == "claude-haiku-4-5-20251001"

    @pytest.mark.asyncio
    async def test_model_switch_between_queries(self):
        """Test switching model between queries uses new model."""
        harness = make_mock_harness()
        models_during_calls = []

        def mock_run_stream(**kwargs):
            models_during_calls.append(dict(harness.deep_agent.agent.model_cfg))
            return async_iter([{"type": "text-delta", "delta": "ok"}])

        harness.deep_agent.run_stream = mock_run_stream

        session = HarnessSession(harness=harness)

        # First query with default model
        async for _ in session.query("first"):
            pass

        # Switch model
        session.set_model("haiku")

        # Second query with new model
        async for _ in session.query("second"):
            pass

        assert models_during_calls[0]["model"] == "claude-sonnet-4-5-20250929"
        assert models_during_calls[1]["model"] == "claude-haiku-4-5-20251001"


# --- interrupt() Tests ---


class TestInterrupt:
    """Tests for HarnessSession.interrupt()."""

    def test_interrupt_sets_flag(self):
        """Test interrupt() sets the interrupted flag."""
        harness = make_mock_harness()
        session = HarnessSession(harness=harness)

        assert session.is_interrupted is False
        session.interrupt()
        assert session.is_interrupted is True

    @pytest.mark.asyncio
    async def test_interrupt_stops_stream(self):
        """Test interrupting during streaming stops events."""
        harness = make_mock_harness()

        events_yielded = 0

        async def slow_stream(**kwargs):
            nonlocal events_yielded
            for i in range(10):
                events_yielded += 1
                yield {"type": "text-delta", "delta": f"chunk-{i} "}

        harness.deep_agent.run_stream = slow_stream

        session = HarnessSession(harness=harness)
        collected = []

        async for event in session.query("test"):
            collected.append(event)
            if len(collected) == 3:
                session.interrupt()

        # Should get 3 regular events + 1 interrupted event
        assert len(collected) == 4
        assert collected[3]["type"] == "interrupted"

    @pytest.mark.asyncio
    async def test_interrupt_includes_session_id(self):
        """Test interrupted event includes session_id."""
        harness = make_mock_harness()

        async def slow_stream(**kwargs):
            yield {"type": "text-delta", "delta": "a"}
            yield {"type": "text-delta", "delta": "b"}

        harness.deep_agent.run_stream = slow_stream

        session = HarnessSession(harness=harness, session_id="my-session")

        collected = []
        async for event in session.query("test"):
            collected.append(event)
            if len(collected) == 1:
                session.interrupt()

        interrupted_event = collected[-1]
        assert interrupted_event["type"] == "interrupted"
        assert interrupted_event["session_id"] == "my-session"

    @pytest.mark.asyncio
    async def test_interrupt_resets_on_new_query(self):
        """Test interrupt flag is reset when starting a new query."""
        harness = make_mock_harness()
        harness.deep_agent.run_stream = MagicMock(
            return_value=async_iter([{"type": "text-delta", "delta": "ok"}])
        )

        session = HarnessSession(harness=harness)
        session.interrupt()
        assert session.is_interrupted is True

        # New query should reset the flag
        async for _ in session.query("test"):
            pass

        # The flag gets reset at the start of query()
        # (it was set before, but query() resets it)
        # After the query completes normally, is_interrupted should be False
        assert session.is_interrupted is False


# --- set_reasoning() Tests ---


class TestSetReasoning:
    """Tests for HarnessSession.set_reasoning()."""

    def test_set_reasoning_native(self):
        """Test set_reasoning with native mode."""
        harness = make_mock_harness()
        session = HarnessSession(harness=harness)

        session.set_reasoning("native")

        assert harness._reasoning_config is not None
        assert harness._reasoning_config.mode == "native"
        # Should also set generation_config on the agent
        assert harness.deep_agent.agent.generation_config == {
            "thinking": {"type": "enabled", "budget_tokens": 10000}
        }

    def test_set_reasoning_native_custom_budget(self):
        """Test set_reasoning with native mode and custom budget."""
        harness = make_mock_harness()
        session = HarnessSession(harness=harness)

        session.set_reasoning({"mode": "native", "budget_tokens": 5000})

        assert harness._reasoning_config.mode == "native"
        assert harness.deep_agent.agent.generation_config == {
            "thinking": {"type": "enabled", "budget_tokens": 5000}
        }

    def test_set_reasoning_none(self):
        """Test set_reasoning to none clears generation_config."""
        harness = make_mock_harness()
        harness.deep_agent.agent.generation_config = {"thinking": {"type": "enabled"}}
        session = HarnessSession(harness=harness)

        session.set_reasoning("none")

        assert harness._reasoning_config.mode == "none"
        assert harness.deep_agent.agent.generation_config == {}

    def test_set_reasoning_null_clears(self):
        """Test set_reasoning(None) clears the config."""
        harness = make_mock_harness()
        harness._reasoning_config = ReasoningConfig(mode="native")
        session = HarnessSession(harness=harness)

        session.set_reasoning(None)
        assert harness._reasoning_config is None

    def test_set_reasoning_prompted(self):
        """Test set_reasoning with prompted mode stores config."""
        harness = make_mock_harness()
        session = HarnessSession(harness=harness)

        session.set_reasoning("prompted")
        assert harness._reasoning_config.mode == "prompted"

    def test_set_reasoning_reflection(self):
        """Test set_reasoning with reflection mode stores config."""
        harness = make_mock_harness()
        session = HarnessSession(harness=harness)

        session.set_reasoning("reflection")
        assert harness._reasoning_config.mode == "reflection"

    def test_set_reasoning_config_instance(self):
        """Test set_reasoning with ReasoningConfig instance."""
        harness = make_mock_harness()
        session = HarnessSession(harness=harness)

        config = ReasoningConfig(mode="native", budget_tokens=20000)
        session.set_reasoning(config)

        assert harness._reasoning_config.mode == "native"
        assert harness._reasoning_config.budget_tokens == 20000


# --- Async Context Manager Tests ---


class TestAsyncContextManager:
    """Tests for HarnessSession as async context manager."""

    @pytest.mark.asyncio
    async def test_enter_returns_session(self):
        """Test __aenter__ returns the session."""
        harness = make_mock_harness()
        session = HarnessSession(harness=harness)

        async with session as s:
            assert s is session

    @pytest.mark.asyncio
    async def test_exit_resets_interrupt(self):
        """Test __aexit__ resets interrupt flag."""
        harness = make_mock_harness()
        session = HarnessSession(harness=harness)

        async with session as s:
            s.interrupt()
            assert s.is_interrupted is True

        assert session.is_interrupted is False

    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        """Test complete session lifecycle."""
        harness = make_mock_harness()

        async def mock_run_stream(**kwargs):
            yield {"type": "text-delta", "delta": "response"}

        harness.deep_agent.run_stream = mock_run_stream

        async with HarnessSession(harness=harness, session_id="lifecycle") as session:
            assert session.session_id == "lifecycle"
            assert session.query_count == 0

            collected = []
            async for event in session.query("hello"):
                collected.append(event)

            assert len(collected) == 1
            assert session.query_count == 1


# --- get_state() Tests ---


class TestGetState:
    """Tests for HarnessSession.get_state()."""

    def test_get_state_includes_session_id(self):
        """Test get_state includes session_id."""
        harness = make_mock_harness()
        session = HarnessSession(harness=harness, session_id="my-session")
        state = session.get_state()
        assert state["session_id"] == "my-session"

    def test_get_state_includes_query_count(self):
        """Test get_state includes query_count."""
        harness = make_mock_harness()
        session = HarnessSession(harness=harness)
        state = session.get_state()
        assert state["query_count"] == 0

    def test_get_state_includes_model(self):
        """Test get_state includes current model."""
        model = {"provider": "anthropic", "model": "test"}
        harness = make_mock_harness(model_cfg=model)
        session = HarnessSession(harness=harness)
        state = session.get_state()
        assert state["model"] == model

    @pytest.mark.asyncio
    async def test_get_state_reflects_changes(self):
        """Test get_state reflects model changes and query count."""
        harness = make_mock_harness()
        harness.deep_agent.run_stream = MagicMock(
            return_value=async_iter([{"type": "text-delta", "delta": "ok"}])
        )

        session = HarnessSession(harness=harness)

        async for _ in session.query("test"):
            pass

        session.set_model("haiku")
        state = session.get_state()
        assert state["query_count"] == 1
        assert state["model"]["model"] == "claude-haiku-4-5-20251001"


# --- VelHarness.create_session() Integration Tests ---


class TestVelHarnessCreateSession:
    """Tests for VelHarness.create_session() integration."""

    @pytest.fixture
    def mock_agent(self):
        """Create a mock Vel Agent."""
        with patch("vel_harness.factory.Agent") as MockAgent:
            mock_instance = MagicMock()
            MockAgent.return_value = mock_instance
            yield MockAgent

    def test_create_session_default(self, mock_agent):
        """Test create_session with default session_id."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
        )
        session = harness.create_session()
        assert isinstance(session, HarnessSession)
        assert session.harness is harness
        assert session.session_id is not None

    def test_create_session_custom_id(self, mock_agent):
        """Test create_session with custom session_id."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
        )
        session = harness.create_session(session_id="custom-123")
        assert session.session_id == "custom-123"

    def test_multiple_sessions_independent(self, mock_agent):
        """Test multiple sessions have different IDs."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
        )
        s1 = harness.create_session()
        s2 = harness.create_session()
        assert s1.session_id != s2.session_id

    def test_session_shares_deep_agent(self, mock_agent):
        """Test session shares the harness's deep_agent."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
        )
        session = harness.create_session()
        # Session's model should reflect the harness's deep agent
        assert session.harness.deep_agent is harness.deep_agent
