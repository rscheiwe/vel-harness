"""
Tests for Context Management Middleware

Two-phase context management:
- Phase 1: Truncation (immediate) - content stays in context but shortened
- Phase 2: Historical offload (after response) - content moves out via ctx-zip
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from vel_harness.middleware.context import (
    ContextManagementMiddleware,
    ContextConfig,
    CompressionEvent,
    create_context_middleware,
)
from vel_harness.backends.state import StateFilesystemBackend


class TestContextConfig:
    """Test ContextConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = ContextConfig()
        assert config.truncate_threshold == 25_000
        assert config.truncate_head_lines == 50
        assert config.truncate_tail_lines == 20
        assert config.history_threshold == 8_000
        assert config.eviction_threshold == 0.85
        assert config.summarization_threshold == 0.95
        assert config.preserve_recent_messages == 20
        assert "claude-sonnet-4-5-20250929" in config.model_context_windows
        assert "write_todos" in config.tools_excluded_from_compression

    def test_custom_values(self):
        """Test custom configuration values."""
        config = ContextConfig(
            truncate_threshold=10_000,
            truncate_head_lines=30,
            truncate_tail_lines=10,
            eviction_threshold=0.75,
        )
        assert config.truncate_threshold == 10_000
        assert config.truncate_head_lines == 30
        assert config.truncate_tail_lines == 10
        assert config.eviction_threshold == 0.75


class TestContextManagementMiddleware:
    """Test ContextManagementMiddleware class."""

    @pytest.fixture
    def filesystem(self):
        """Create a test filesystem backend."""
        return StateFilesystemBackend()

    @pytest.fixture
    def middleware(self, filesystem):
        """Create middleware with filesystem."""
        return ContextManagementMiddleware(
            filesystem_backend=filesystem,
        )

    @pytest.fixture
    def middleware_no_fs(self):
        """Create middleware without filesystem."""
        return ContextManagementMiddleware()

    def test_init_default(self):
        """Test initialization with defaults."""
        mw = ContextManagementMiddleware()
        assert mw.config is not None
        assert mw.filesystem is None
        assert mw.summarization_model is None
        assert len(mw.compression_log) == 0

    def test_init_with_config(self, filesystem):
        """Test initialization with custom config."""
        config = ContextConfig(truncate_threshold=5000)
        mw = ContextManagementMiddleware(
            config=config,
            filesystem_backend=filesystem,
        )
        assert mw.config.truncate_threshold == 5000
        assert mw.filesystem is filesystem

    def test_get_model_context_window_exact(self, middleware):
        """Test exact model name matching."""
        window = middleware.get_model_context_window("claude-sonnet-4-5-20250929")
        assert window == 200_000

    def test_get_model_context_window_prefix(self, middleware):
        """Test prefix model name matching."""
        window = middleware.get_model_context_window("gpt-4o-2024-01")
        assert window == 128_000

    def test_get_model_context_window_unknown(self, middleware):
        """Test unknown model defaults to 100K."""
        window = middleware.get_model_context_window("unknown-model")
        assert window == 100_000

    def test_estimate_tokens_fallback(self, middleware):
        """Test token estimation with fallback heuristic."""
        # Regular text ~3.8 chars per token
        text = "a" * 380
        tokens = middleware._fallback_estimate(text)
        assert tokens == 100

    def test_estimate_message_tokens(self, middleware):
        """Test message token estimation."""
        messages = [
            {"role": "user", "content": "a" * 380},
            {"role": "assistant", "content": "b" * 760},
        ]
        tokens = middleware.estimate_message_tokens(messages)
        # Using fallback: 380/3.8 + 760/3.8 = 100 + 200 = 300
        assert tokens == 300

    def test_estimate_message_tokens_with_list_content(self, middleware):
        """Test message token estimation with list content."""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "a" * 400},
                ],
            }
        ]
        tokens = middleware.estimate_message_tokens(messages)
        assert tokens > 0


class TestPhase1Truncation:
    """Test Phase 1: Truncation of massive tool results."""

    @pytest.fixture
    def filesystem(self):
        return StateFilesystemBackend()

    @pytest.fixture
    def middleware(self, filesystem):
        # Set low threshold for testing
        config = ContextConfig(
            truncate_threshold=100,  # ~380 chars
            truncate_head_lines=3,
            truncate_tail_lines=2,
        )
        return ContextManagementMiddleware(
            config=config,
            filesystem_backend=filesystem,
        )

    def test_small_result_passthrough(self, middleware):
        """Test that small results pass through unchanged."""
        content = "small result"
        result = middleware.process_tool_result(content, "read_file", "call123")
        assert result == content
        assert len(middleware.compression_log) == 0

    def test_large_result_truncated(self, middleware):
        """Test that large results are truncated."""
        # Create content with many lines
        lines = [f"line {i}" for i in range(100)]
        content = "\n".join(lines)

        result = middleware.process_tool_result(content, "grep", "call123")

        # Should have head + tail + truncation message
        assert "line 0" in result
        assert "line 1" in result
        assert "line 2" in result
        assert "line 98" in result
        assert "line 99" in result
        assert "lines truncated" in result

        # Should log compression event
        assert len(middleware.compression_log) == 1
        event = middleware.compression_log[0]
        assert event.compression_type == "truncate"
        assert event.tool_name == "grep"

    def test_excluded_tools_not_truncated(self, middleware):
        """Test that excluded tools are never truncated."""
        content = "x" * 10000  # Very large
        result = middleware.process_tool_result(content, "write_todos", "call123")
        assert result == content
        assert len(middleware.compression_log) == 0


class TestTier2ToolInputEviction:
    """Test Tier 2: Tool input eviction."""

    @pytest.fixture
    def middleware(self):
        config = ContextConfig(eviction_threshold=0.5)  # 50% for testing
        return ContextManagementMiddleware(config=config)

    def test_should_evict_under_threshold(self, middleware):
        """Test no eviction under threshold."""
        # Small messages, well under threshold
        messages = [{"role": "user", "content": "hello"}]
        assert not middleware.should_evict_tool_inputs(messages, "claude-sonnet-4-5-20250929")

    def test_should_evict_over_threshold(self, middleware):
        """Test eviction over threshold."""
        # Create messages that exceed 50% of 200K context
        large_content = "x" * 500_000  # ~130K tokens
        messages = [{"role": "user", "content": large_content}]
        assert middleware.should_evict_tool_inputs(messages, "claude-sonnet-4-5-20250929")

    def test_evict_tool_inputs(self, middleware):
        """Test evicting tool inputs."""
        messages = [
            {"role": "user", "content": "write a file"},
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool-call",
                        "toolName": "write_file",
                        "args": {
                            "path": "/test.txt",
                            "content": "very long content here" * 100,
                        },
                    }
                ],
            },
            {"role": "user", "content": "thanks"},
        ]

        evicted = middleware.evict_tool_inputs(messages)

        # Check that write_file args were evicted
        assert len(evicted) == 3
        tool_call = evicted[1]["content"][0]
        assert tool_call["args"]["_evicted"] is True
        assert tool_call["args"]["path"] == "/test.txt"
        assert "content" not in tool_call["args"]

    def test_evict_preserves_other_tools(self, middleware):
        """Test that non-file tools are preserved."""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool-call",
                        "toolName": "web_search",
                        "args": {"query": "test"},
                    }
                ],
            }
        ]

        evicted = middleware.evict_tool_inputs(messages)

        # web_search should be unchanged
        tool_call = evicted[0]["content"][0]
        assert "_evicted" not in tool_call["args"]
        assert tool_call["args"]["query"] == "test"


class TestTier3ConversationSummarization:
    """Test Tier 3: Conversation summarization."""

    @pytest.fixture
    def filesystem(self):
        return StateFilesystemBackend()

    @pytest.fixture
    def middleware(self, filesystem):
        config = ContextConfig(
            summarization_threshold=0.5,
            preserve_recent_messages=5,
        )
        return ContextManagementMiddleware(
            config=config,
            filesystem_backend=filesystem,
        )

    def test_should_summarize_under_threshold(self, middleware):
        """Test no summarization under threshold."""
        messages = [{"role": "user", "content": "hello"}]
        assert not middleware.should_summarize(messages, "claude-sonnet-4-5-20250929")

    def test_should_summarize_over_threshold(self, middleware):
        """Test summarization over threshold."""
        # Create messages that exceed 50% of 200K context
        large_content = "x" * 500_000
        messages = [{"role": "user", "content": large_content}]
        assert middleware.should_summarize(messages, "claude-sonnet-4-5-20250929")

    @pytest.mark.asyncio
    async def test_summarize_conversation(self, middleware, filesystem):
        """Test conversation summarization."""
        # Create 10 messages
        messages = [
            {"role": "user", "content": f"Message {i}"}
            for i in range(10)
        ]

        result = await middleware.summarize_conversation(messages, "test-session")

        # Should have summary + 5 recent messages
        assert len(result) == 6
        assert result[0]["role"] == "system"
        assert "[Conversation Summary]" in result[0]["content"]

        # Check recent messages preserved
        assert result[-1]["content"] == "Message 9"

    @pytest.mark.asyncio
    async def test_summarize_saves_transcript(self, middleware, filesystem):
        """Test that summarization saves transcript."""
        messages = [
            {"role": "user", "content": f"Message {i}"}
            for i in range(10)
        ]

        result = await middleware.summarize_conversation(messages, "test-session")

        # Check transcript path in summary
        summary = result[0]["content"]
        assert "/context/transcripts/" in summary

    @pytest.mark.asyncio
    async def test_summarize_short_conversation(self, middleware):
        """Test that short conversations are not summarized."""
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]

        result = await middleware.summarize_conversation(messages, "test-session")

        # Should return unchanged
        assert len(result) == 2
        assert result == messages

    def test_extract_summary_heuristic(self, middleware):
        """Test heuristic summary extraction."""
        messages = [
            {"role": "user", "content": "Please analyze the data"},
            {
                "role": "assistant",
                "content": [
                    {"type": "tool-call", "toolName": "read_file"},
                    {"type": "tool-call", "toolName": "execute_sql"},
                ],
            },
            {"role": "user", "content": "Now summarize it"},
        ]

        summary = middleware._extract_summary_heuristic(messages)

        assert "## Tools Used" in summary
        assert "read_file" in summary
        assert "execute_sql" in summary
        assert "## User Requests" in summary


class TestMainProcessing:
    """Test main processing functions."""

    @pytest.fixture
    def filesystem(self):
        return StateFilesystemBackend()

    @pytest.fixture
    def middleware(self, filesystem):
        config = ContextConfig(
            truncate_threshold=100,  # ~380 chars
        )
        return ContextManagementMiddleware(
            config=config,
            filesystem_backend=filesystem,
        )

    @pytest.mark.asyncio
    async def test_process_messages(self, middleware):
        """Test full message processing."""
        messages = [{"role": "user", "content": "hello"}]

        result = await middleware.process_messages(
            messages, "claude-sonnet-4-5-20250929", "test-session"
        )

        # Should return unchanged for small messages
        assert result == messages

    def test_process_tool_result_small(self, middleware):
        """Test small tool result passthrough."""
        content = "small result"
        result = middleware.process_tool_result(content, "grep", "call123")
        assert result == content

    def test_process_tool_result_large(self, middleware, filesystem):
        """Test large tool result truncation."""
        # Create content that exceeds threshold
        lines = [f"line {i}" for i in range(100)]
        content = "\n".join(lines)

        result = middleware.process_tool_result(content, "grep", "call123")

        assert "lines truncated" in result
        assert len(middleware.compression_log) == 1

    def test_get_system_prompt_segment(self, middleware):
        """Test system prompt segment."""
        prompt = middleware.get_system_prompt_segment()

        assert "Context Management" in prompt
        assert "Truncation" in prompt
        assert "Context Pressure" in prompt

    def test_get_context_stats(self, middleware):
        """Test context statistics."""
        messages = [{"role": "user", "content": "a" * 3800}]  # ~1000 tokens

        stats = middleware.get_context_stats(messages, "claude-sonnet-4-5-20250929")

        assert stats["current_tokens"] == 1000
        assert stats["max_tokens"] == 200_000
        assert stats["usage_percent"] == 0.5
        assert stats["eviction_threshold_percent"] == 85.0
        assert not stats["will_evict"]
        assert not stats["will_summarize"]


class TestCompressionEvent:
    """Test CompressionEvent dataclass."""

    def test_compression_event_creation(self):
        """Test creating a compression event."""
        event = CompressionEvent(
            tool_name="grep",
            original_tokens=50000,
            result_tokens=5000,
            compression_type="truncate",
        )
        assert event.tool_name == "grep"
        assert event.original_tokens == 50000
        assert event.result_tokens == 5000
        assert event.compression_type == "truncate"
        assert event.timestamp is not None


class TestFactoryFunction:
    """Test create_context_middleware factory."""

    def test_create_with_defaults(self):
        """Test creation with defaults."""
        mw = create_context_middleware()
        assert mw.config is not None
        assert mw.filesystem is None

    def test_create_with_filesystem(self):
        """Test creation with filesystem."""
        fs = StateFilesystemBackend()
        mw = create_context_middleware(filesystem_backend=fs)
        assert mw.filesystem is fs

    def test_create_with_config(self):
        """Test creation with custom config."""
        config = ContextConfig(truncate_threshold=5000)
        mw = create_context_middleware(config=config)
        assert mw.config.truncate_threshold == 5000

    def test_create_with_summarization_model(self):
        """Test creation with summarization model."""
        model = {"provider": "anthropic", "model": "claude-haiku"}
        mw = create_context_middleware(summarization_model=model)
        assert mw.summarization_model == model
