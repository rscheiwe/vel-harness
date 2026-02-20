"""
Tests for Fallback Model (WS6)

Tests the FallbackStreamWrapper including:
- Retryable status code detection
- Retryable error string detection
- Primary model success (no fallback)
- Fallback on retryable errors (429, 500, 502, 503, 529)
- Non-retryable errors pass through
- Fallback model swap and restore
- Max retries respected
- Non-streaming run() wrapper
- VelHarness integration with fallback_model param
- Config wiring (string shorthand, dict)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from vel_harness.fallback import FallbackStreamWrapper, RETRYABLE_STATUS_CODES
from vel_harness import VelHarness


# --- Helpers ---


def make_deep_agent(model_cfg=None):
    """Create a mock DeepAgent with configurable model_cfg."""
    agent = MagicMock()
    agent.agent = MagicMock()
    agent.agent.model_cfg = model_cfg or {"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"}
    return agent


async def async_iter(events):
    """Create an async iterator from a list of events."""
    for event in events:
        yield event


# --- Retryable Status Code Tests ---


class TestRetryableStatus:
    """Tests for is_retryable_status()."""

    def test_429_is_retryable(self):
        assert FallbackStreamWrapper.is_retryable_status(429) is True

    def test_500_is_retryable(self):
        assert FallbackStreamWrapper.is_retryable_status(500) is True

    def test_502_is_retryable(self):
        assert FallbackStreamWrapper.is_retryable_status(502) is True

    def test_503_is_retryable(self):
        assert FallbackStreamWrapper.is_retryable_status(503) is True

    def test_529_is_retryable(self):
        assert FallbackStreamWrapper.is_retryable_status(529) is True

    def test_400_not_retryable(self):
        assert FallbackStreamWrapper.is_retryable_status(400) is False

    def test_401_not_retryable(self):
        assert FallbackStreamWrapper.is_retryable_status(401) is False

    def test_403_not_retryable(self):
        assert FallbackStreamWrapper.is_retryable_status(403) is False

    def test_404_not_retryable(self):
        assert FallbackStreamWrapper.is_retryable_status(404) is False

    def test_200_not_retryable(self):
        assert FallbackStreamWrapper.is_retryable_status(200) is False

    def test_none_not_retryable(self):
        assert FallbackStreamWrapper.is_retryable_status(None) is False

    def test_retryable_set_contents(self):
        """Verify the exact set of retryable status codes."""
        assert RETRYABLE_STATUS_CODES == {429, 500, 502, 503, 529}


# --- Retryable Error String Tests ---


class TestRetryableError:
    """Tests for is_retryable_error()."""

    def test_rate_limit(self):
        assert FallbackStreamWrapper.is_retryable_error("Rate limit exceeded") is True

    def test_rate_limit_underscore(self):
        assert FallbackStreamWrapper.is_retryable_error("rate_limit_error") is True

    def test_overloaded(self):
        assert FallbackStreamWrapper.is_retryable_error("Model is overloaded") is True

    def test_too_many_requests(self):
        assert FallbackStreamWrapper.is_retryable_error("Too many requests") is True

    def test_service_unavailable(self):
        assert FallbackStreamWrapper.is_retryable_error("Service unavailable") is True

    def test_internal_server_error(self):
        assert FallbackStreamWrapper.is_retryable_error("Internal server error") is True

    def test_bad_gateway(self):
        assert FallbackStreamWrapper.is_retryable_error("Bad gateway") is True

    def test_gateway_timeout(self):
        assert FallbackStreamWrapper.is_retryable_error("Gateway timeout") is True

    def test_case_insensitive(self):
        assert FallbackStreamWrapper.is_retryable_error("RATE LIMIT exceeded") is True

    def test_non_retryable_error(self):
        assert FallbackStreamWrapper.is_retryable_error("Invalid API key") is False

    def test_empty_string(self):
        assert FallbackStreamWrapper.is_retryable_error("") is False

    def test_unrelated_error(self):
        assert FallbackStreamWrapper.is_retryable_error("JSON parse error") is False


# --- FallbackStreamWrapper Construction Tests ---


class TestFallbackConstruction:
    """Tests for FallbackStreamWrapper initialization."""

    def test_basic_construction(self):
        agent = make_deep_agent()
        fallback_model = {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"}
        wrapper = FallbackStreamWrapper(
            deep_agent=agent,
            fallback_model=fallback_model,
            max_retries=2,
        )
        assert wrapper._agent is agent
        assert wrapper._fallback_model is fallback_model
        assert wrapper._max_retries == 2

    def test_default_max_retries(self):
        agent = make_deep_agent()
        wrapper = FallbackStreamWrapper(
            deep_agent=agent,
            fallback_model={"provider": "anthropic", "model": "test"},
        )
        assert wrapper._max_retries == 1


# --- run_stream Tests ---


class TestRunStream:
    """Tests for FallbackStreamWrapper.run_stream()."""

    @pytest.mark.asyncio
    async def test_primary_success_no_fallback(self):
        """When primary model succeeds, events pass through without fallback."""
        agent = make_deep_agent()
        events = [
            {"type": "text-delta", "delta": "Hello "},
            {"type": "text-delta", "delta": "world"},
        ]
        agent.run_stream = MagicMock(return_value=async_iter(events))

        wrapper = FallbackStreamWrapper(
            deep_agent=agent,
            fallback_model={"provider": "anthropic", "model": "fallback"},
        )

        collected = []
        async for event in wrapper.run_stream(input_text="test"):
            collected.append(event)

        assert len(collected) == 2
        assert collected[0]["delta"] == "Hello "
        assert collected[1]["delta"] == "world"

    @pytest.mark.asyncio
    async def test_fallback_on_429(self):
        """Retryable 429 triggers fallback."""
        primary_model = {"provider": "anthropic", "model": "primary"}
        fallback_model = {"provider": "anthropic", "model": "fallback"}
        agent = make_deep_agent(model_cfg=primary_model)

        primary_events = [
            {"type": "error", "status_code": 429, "error": "Rate limit exceeded"},
        ]
        fallback_events = [
            {"type": "text-delta", "delta": "Fallback response"},
        ]

        call_count = 0

        def mock_run_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return async_iter(primary_events)
            return async_iter(fallback_events)

        agent.run_stream = mock_run_stream

        wrapper = FallbackStreamWrapper(
            deep_agent=agent,
            fallback_model=fallback_model,
        )

        collected = []
        async for event in wrapper.run_stream(input_text="test"):
            collected.append(event)

        assert len(collected) == 1
        assert collected[0]["delta"] == "Fallback response"
        # Model should be restored after fallback
        assert agent.agent.model_cfg == primary_model

    @pytest.mark.asyncio
    async def test_fallback_on_529(self):
        """Retryable 529 (overloaded) triggers fallback."""
        primary_model = {"provider": "anthropic", "model": "primary"}
        fallback_model = {"provider": "anthropic", "model": "fallback"}
        agent = make_deep_agent(model_cfg=primary_model)

        call_count = 0

        def mock_run_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return async_iter([
                    {"type": "error", "status_code": 529, "error": "Overloaded"},
                ])
            return async_iter([
                {"type": "text-delta", "delta": "OK"},
            ])

        agent.run_stream = mock_run_stream

        wrapper = FallbackStreamWrapper(
            deep_agent=agent,
            fallback_model=fallback_model,
        )

        collected = []
        async for event in wrapper.run_stream(input_text="test"):
            collected.append(event)

        assert len(collected) == 1
        assert collected[0]["delta"] == "OK"

    @pytest.mark.asyncio
    async def test_fallback_on_500(self):
        """Retryable 500 triggers fallback."""
        agent = make_deep_agent()
        call_count = 0

        def mock_run_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return async_iter([
                    {"type": "error", "status_code": 500, "error": "Internal server error"},
                ])
            return async_iter([
                {"type": "text-delta", "delta": "recovered"},
            ])

        agent.run_stream = mock_run_stream

        wrapper = FallbackStreamWrapper(
            deep_agent=agent,
            fallback_model={"provider": "anthropic", "model": "fallback"},
        )

        collected = []
        async for event in wrapper.run_stream(input_text="test"):
            collected.append(event)

        assert len(collected) == 1
        assert collected[0]["delta"] == "recovered"

    @pytest.mark.asyncio
    async def test_no_fallback_on_400(self):
        """Non-retryable 400 error passes through (no fallback)."""
        agent = make_deep_agent()
        agent.run_stream = MagicMock(return_value=async_iter([
            {"type": "error", "status_code": 400, "error": "Bad request"},
        ]))

        wrapper = FallbackStreamWrapper(
            deep_agent=agent,
            fallback_model={"provider": "anthropic", "model": "fallback"},
        )

        collected = []
        async for event in wrapper.run_stream(input_text="test"):
            collected.append(event)

        assert len(collected) == 1
        assert collected[0]["type"] == "error"
        assert collected[0]["status_code"] == 400

    @pytest.mark.asyncio
    async def test_no_fallback_on_401(self):
        """Non-retryable 401 error passes through (no fallback)."""
        agent = make_deep_agent()
        agent.run_stream = MagicMock(return_value=async_iter([
            {"type": "error", "status_code": 401, "error": "Unauthorized"},
        ]))

        wrapper = FallbackStreamWrapper(
            deep_agent=agent,
            fallback_model={"provider": "anthropic", "model": "fallback"},
        )

        collected = []
        async for event in wrapper.run_stream(input_text="test"):
            collected.append(event)

        assert len(collected) == 1
        assert collected[0]["status_code"] == 401

    @pytest.mark.asyncio
    async def test_fallback_on_error_string_pattern(self):
        """Retryable error string (no status code) triggers fallback."""
        agent = make_deep_agent()
        call_count = 0

        def mock_run_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return async_iter([
                    {"type": "error", "error": "rate limit exceeded"},
                ])
            return async_iter([
                {"type": "text-delta", "delta": "fallback ok"},
            ])

        agent.run_stream = mock_run_stream

        wrapper = FallbackStreamWrapper(
            deep_agent=agent,
            fallback_model={"provider": "anthropic", "model": "fallback"},
        )

        collected = []
        async for event in wrapper.run_stream(input_text="test"):
            collected.append(event)

        assert len(collected) == 1
        assert collected[0]["delta"] == "fallback ok"

    @pytest.mark.asyncio
    async def test_model_swap_and_restore(self):
        """Verify model is swapped for fallback and restored after."""
        primary_model = {"provider": "anthropic", "model": "primary"}
        fallback_model = {"provider": "anthropic", "model": "fallback"}
        agent = make_deep_agent(model_cfg=primary_model)

        models_during_calls = []

        def mock_run_stream(**kwargs):
            models_during_calls.append(dict(agent.agent.model_cfg))
            if len(models_during_calls) == 1:
                return async_iter([
                    {"type": "error", "status_code": 429, "error": "Rate limited"},
                ])
            return async_iter([
                {"type": "text-delta", "delta": "ok"},
            ])

        agent.run_stream = mock_run_stream

        wrapper = FallbackStreamWrapper(
            deep_agent=agent,
            fallback_model=fallback_model,
        )

        async for _ in wrapper.run_stream(input_text="test"):
            pass

        # First call used primary model
        assert models_during_calls[0] == primary_model
        # Second call used fallback model
        assert models_during_calls[1] == fallback_model
        # After completion, model is restored
        assert agent.agent.model_cfg == primary_model

    @pytest.mark.asyncio
    async def test_max_retries_respected(self):
        """All retries exhaust, then last error is yielded."""
        agent = make_deep_agent()

        def mock_run_stream(**kwargs):
            return async_iter([
                {"type": "error", "status_code": 429, "error": "Rate limited"},
            ])

        agent.run_stream = mock_run_stream

        wrapper = FallbackStreamWrapper(
            deep_agent=agent,
            fallback_model={"provider": "anthropic", "model": "fallback"},
            max_retries=3,
        )

        collected = []
        async for event in wrapper.run_stream(input_text="test"):
            collected.append(event)

        # Should get the final error after all retries exhausted
        assert len(collected) == 1
        assert collected[0]["type"] == "error"
        assert collected[0]["status_code"] == 429

    @pytest.mark.asyncio
    async def test_partial_events_before_error(self):
        """Partial primary events are discarded on retryable error; fallback output is used."""
        agent = make_deep_agent()
        call_count = 0

        def mock_run_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return async_iter([
                    {"type": "text-delta", "delta": "partial "},
                    {"type": "error", "status_code": 503, "error": "Service unavailable"},
                ])
            return async_iter([
                {"type": "text-delta", "delta": "full response"},
            ])

        agent.run_stream = mock_run_stream

        wrapper = FallbackStreamWrapper(
            deep_agent=agent,
            fallback_model={"provider": "anthropic", "model": "fallback"},
        )

        collected = []
        async for event in wrapper.run_stream(input_text="test"):
            collected.append(event)

        # Only fallback response should be emitted
        assert len(collected) == 1
        assert collected[0]["delta"] == "full response"

    @pytest.mark.asyncio
    async def test_non_dict_events_pass_through(self):
        """Non-dict events pass through without inspection."""
        agent = make_deep_agent()
        agent.run_stream = MagicMock(return_value=async_iter([
            "string-event",
            42,
            {"type": "text-delta", "delta": "ok"},
        ]))

        wrapper = FallbackStreamWrapper(
            deep_agent=agent,
            fallback_model={"provider": "anthropic", "model": "fallback"},
        )

        collected = []
        async for event in wrapper.run_stream(input_text="test"):
            collected.append(event)

        assert collected == ["string-event", 42, {"type": "text-delta", "delta": "ok"}]

    @pytest.mark.asyncio
    async def test_fallback_also_fails_retryable(self):
        """When fallback also gets retryable error, retries continue."""
        agent = make_deep_agent()
        call_count = 0

        def mock_run_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return async_iter([
                    {"type": "error", "status_code": 429, "error": "Rate limited"},
                ])
            return async_iter([
                {"type": "text-delta", "delta": "third attempt ok"},
            ])

        agent.run_stream = mock_run_stream

        wrapper = FallbackStreamWrapper(
            deep_agent=agent,
            fallback_model={"provider": "anthropic", "model": "fallback"},
            max_retries=3,
        )

        collected = []
        async for event in wrapper.run_stream(input_text="test"):
            collected.append(event)

        assert len(collected) == 1
        assert collected[0]["delta"] == "third attempt ok"

    @pytest.mark.asyncio
    async def test_fallback_non_retryable_error(self):
        """When fallback gets non-retryable error, it passes through."""
        agent = make_deep_agent()
        call_count = 0

        def mock_run_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return async_iter([
                    {"type": "error", "status_code": 429, "error": "Rate limited"},
                ])
            return async_iter([
                {"type": "error", "status_code": 400, "error": "Bad input"},
            ])

        agent.run_stream = mock_run_stream

        wrapper = FallbackStreamWrapper(
            deep_agent=agent,
            fallback_model={"provider": "anthropic", "model": "fallback"},
        )

        collected = []
        async for event in wrapper.run_stream(input_text="test"):
            collected.append(event)

        assert len(collected) == 1
        assert collected[0]["status_code"] == 400
        assert collected[0]["error"] == "Bad input"

    @pytest.mark.asyncio
    async def test_kwargs_passed_through(self):
        """session_id and context are passed to run_stream."""
        agent = make_deep_agent()
        call_kwargs = []

        def mock_run_stream(**kwargs):
            call_kwargs.append(kwargs)
            return async_iter([
                {"type": "text-delta", "delta": "ok"},
            ])

        agent.run_stream = mock_run_stream

        wrapper = FallbackStreamWrapper(
            deep_agent=agent,
            fallback_model={"provider": "anthropic", "model": "fallback"},
        )

        async for _ in wrapper.run_stream(
            input_text="hello",
            session_id="sess-1",
            context={"key": "val"},
        ):
            pass

        assert call_kwargs[0]["input_text"] == "hello"
        assert call_kwargs[0]["session_id"] == "sess-1"
        assert call_kwargs[0]["context"] == {"key": "val"}

    @pytest.mark.asyncio
    async def test_model_restored_on_fallback_success(self):
        """Model is restored even when fallback succeeds."""
        primary_model = {"provider": "anthropic", "model": "primary"}
        fallback_model = {"provider": "anthropic", "model": "fallback"}
        agent = make_deep_agent(model_cfg=primary_model)
        call_count = 0

        def mock_run_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return async_iter([
                    {"type": "error", "status_code": 502, "error": "Bad gateway"},
                ])
            return async_iter([
                {"type": "text-delta", "delta": "ok"},
            ])

        agent.run_stream = mock_run_stream

        wrapper = FallbackStreamWrapper(
            deep_agent=agent,
            fallback_model=fallback_model,
        )

        async for _ in wrapper.run_stream(input_text="test"):
            pass

        assert agent.agent.model_cfg == primary_model

    @pytest.mark.asyncio
    async def test_model_restored_on_all_retries_exhausted(self):
        """Model is restored even when all retries are exhausted."""
        primary_model = {"provider": "anthropic", "model": "primary"}
        fallback_model = {"provider": "anthropic", "model": "fallback"}
        agent = make_deep_agent(model_cfg=primary_model)

        def mock_run_stream(**kwargs):
            return async_iter([
                {"type": "error", "status_code": 429, "error": "Rate limited"},
            ])

        agent.run_stream = mock_run_stream

        wrapper = FallbackStreamWrapper(
            deep_agent=agent,
            fallback_model=fallback_model,
            max_retries=2,
        )

        async for _ in wrapper.run_stream(input_text="test"):
            pass

        assert agent.agent.model_cfg == primary_model


# --- run() (non-streaming) Tests ---


class TestRun:
    """Tests for FallbackStreamWrapper.run()."""

    @pytest.mark.asyncio
    async def test_run_collects_text_deltas(self):
        """run() collects text-delta events into content string."""
        agent = make_deep_agent()
        agent.run_stream = MagicMock(return_value=async_iter([
            {"type": "text-delta", "delta": "Hello "},
            {"type": "text-delta", "delta": "world"},
        ]))

        wrapper = FallbackStreamWrapper(
            deep_agent=agent,
            fallback_model={"provider": "anthropic", "model": "fallback"},
        )

        result = await wrapper.run(input_text="test")
        assert result == {"content": "Hello world"}

    @pytest.mark.asyncio
    async def test_run_returns_error_on_non_retryable(self):
        """run() returns error dict for non-retryable errors."""
        agent = make_deep_agent()
        agent.run_stream = MagicMock(return_value=async_iter([
            {"type": "error", "status_code": 400, "error": "Bad request"},
        ]))

        wrapper = FallbackStreamWrapper(
            deep_agent=agent,
            fallback_model={"provider": "anthropic", "model": "fallback"},
        )

        result = await wrapper.run(input_text="test")
        assert result["type"] == "error"
        assert result["status_code"] == 400

    @pytest.mark.asyncio
    async def test_run_with_fallback(self):
        """run() triggers fallback and collects text from fallback model."""
        agent = make_deep_agent()
        call_count = 0

        def mock_run_stream(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return async_iter([
                    {"type": "error", "status_code": 429, "error": "Rate limited"},
                ])
            return async_iter([
                {"type": "text-delta", "delta": "Fallback "},
                {"type": "text-delta", "delta": "response"},
            ])

        agent.run_stream = mock_run_stream

        wrapper = FallbackStreamWrapper(
            deep_agent=agent,
            fallback_model={"provider": "anthropic", "model": "fallback"},
        )

        result = await wrapper.run(input_text="test")
        assert result == {"content": "Fallback response"}

    @pytest.mark.asyncio
    async def test_run_returns_last_event_if_no_text(self):
        """run() returns last event if no text-delta events."""
        agent = make_deep_agent()
        agent.run_stream = MagicMock(return_value=async_iter([
            {"type": "tool-call", "name": "read_file"},
            {"type": "step-end"},
        ]))

        wrapper = FallbackStreamWrapper(
            deep_agent=agent,
            fallback_model={"provider": "anthropic", "model": "fallback"},
        )

        result = await wrapper.run(input_text="test")
        assert result == {"type": "step-end"}

    @pytest.mark.asyncio
    async def test_run_returns_none_for_empty_stream(self):
        """run() returns None for empty stream."""
        agent = make_deep_agent()
        agent.run_stream = MagicMock(return_value=async_iter([]))

        wrapper = FallbackStreamWrapper(
            deep_agent=agent,
            fallback_model={"provider": "anthropic", "model": "fallback"},
        )

        result = await wrapper.run(input_text="test")
        assert result is None


# --- VelHarness Integration Tests ---


class TestVelHarnessIntegration:
    """Tests for fallback model through VelHarness."""

    @pytest.fixture
    def mock_agent(self):
        """Create a mock Vel Agent."""
        with patch("vel_harness.factory.Agent") as MockAgent:
            mock_instance = MagicMock()
            MockAgent.return_value = mock_instance
            yield MockAgent

    def test_fallback_model_with_string_shorthand(self, mock_agent):
        """Test VelHarness with string shorthand fallback_model."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            fallback_model="haiku",
        )
        assert harness.fallback_wrapper is not None
        assert harness._fallback_model == {
            "provider": "anthropic",
            "model": "claude-haiku-4-5-20251001",
        }

    def test_fallback_model_with_dict(self, mock_agent):
        """Test VelHarness with dict fallback_model."""
        fb_model = {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"}
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            fallback_model=fb_model,
        )
        assert harness.fallback_wrapper is not None
        assert harness._fallback_model == fb_model

    def test_no_fallback_by_default(self, mock_agent):
        """Test VelHarness has no fallback wrapper by default."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
        )
        assert harness.fallback_wrapper is None

    def test_max_fallback_retries(self, mock_agent):
        """Test max_fallback_retries is passed through."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            fallback_model="haiku",
            max_fallback_retries=3,
        )
        assert harness.fallback_wrapper._max_retries == 3

    def test_fallback_config_in_deep_agent_config(self, mock_agent):
        """Test fallback model is wired into DeepAgentConfig."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            fallback_model="haiku",
            max_fallback_retries=2,
        )
        assert harness.config.fallback_model == {
            "provider": "anthropic",
            "model": "claude-haiku-4-5-20251001",
        }
        assert harness.config.max_fallback_retries == 2

    def test_fallback_sonnet_shorthand(self, mock_agent):
        """Test 'sonnet' shorthand resolves correctly."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            fallback_model="sonnet",
        )
        assert harness._fallback_model == {
            "provider": "anthropic",
            "model": "claude-sonnet-4-5-20250929",
        }

    def test_fallback_opus_shorthand(self, mock_agent):
        """Test 'opus' shorthand resolves correctly."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            fallback_model="opus",
        )
        assert harness._fallback_model == {
            "provider": "anthropic",
            "model": "claude-opus-4-6",
        }

    def test_fallback_wrapper_wraps_deep_agent(self, mock_agent):
        """Test fallback wrapper references the correct deep agent."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            fallback_model="haiku",
        )
        assert harness.fallback_wrapper._agent is harness.deep_agent
