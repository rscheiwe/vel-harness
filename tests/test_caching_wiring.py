"""
Tests for Caching and Retry Middleware Wiring

Tests that CachingConfig and RetryConfig are properly:
- Created with correct defaults
- Parsed from dicts and bools
- Serialized to dicts
- Wired into the factory pipeline (tools get wrapped)
- Exposed in the VelHarness constructor
"""

import pytest
from unittest.mock import MagicMock, patch

from vel import ToolSpec

from vel_harness.config import (
    CachingConfig,
    RetryConfig,
    DeepAgentConfig,
)
from vel_harness.factory import create_deep_agent, DeepAgent
from vel_harness import VelHarness


# --- Config Dataclass Tests ---


class TestCachingConfigDataclass:
    """Tests for CachingConfig at harness config level."""

    def test_default_values(self):
        """Test CachingConfig defaults to disabled."""
        config = CachingConfig()

        assert config.enabled is False
        assert config.prompt_cache_enabled is True
        assert config.prompt_cache_ttl == 300
        assert config.tool_cache_enabled is True
        assert config.tool_cache_ttl == 60
        assert "list_tables" in config.cacheable_tools
        assert "web_search" in config.cacheable_tools
        assert config.max_cache_size == 100

    def test_custom_values(self):
        """Test CachingConfig with custom values."""
        config = CachingConfig(
            enabled=True,
            prompt_cache_ttl=600,
            tool_cache_ttl=120,
            cacheable_tools=["my_tool"],
            max_cache_size=50,
        )

        assert config.enabled is True
        assert config.prompt_cache_ttl == 600
        assert config.tool_cache_ttl == 120
        assert config.cacheable_tools == ["my_tool"]
        assert config.max_cache_size == 50


class TestRetryConfigDataclass:
    """Tests for RetryConfig at harness config level."""

    def test_default_values(self):
        """Test RetryConfig defaults to disabled."""
        config = RetryConfig()

        assert config.enabled is False
        assert config.max_retries == 2
        assert config.backoff_base == 1.0
        assert config.backoff_multiplier == 2.0
        assert config.use_circuit_breaker is False
        assert config.circuit_failure_threshold == 5
        assert config.circuit_reset_timeout == 60.0

    def test_custom_values(self):
        """Test RetryConfig with custom values."""
        config = RetryConfig(
            enabled=True,
            max_retries=5,
            use_circuit_breaker=True,
            circuit_failure_threshold=10,
        )

        assert config.enabled is True
        assert config.max_retries == 5
        assert config.use_circuit_breaker is True
        assert config.circuit_failure_threshold == 10


# --- DeepAgentConfig Integration ---


class TestDeepAgentConfigCachingRetry:
    """Tests for CachingConfig and RetryConfig in DeepAgentConfig."""

    def test_default_config_has_caching_retry(self):
        """Test that DeepAgentConfig includes caching and retry with defaults."""
        config = DeepAgentConfig()

        assert config.caching.enabled is False
        assert config.retry.enabled is False

    def test_from_dict_caching_dict(self):
        """Test from_dict with caching as dict."""
        config = DeepAgentConfig.from_dict({
            "caching": {
                "enabled": True,
                "prompt_cache_ttl": 600,
                "tool_cache_ttl": 120,
                "cacheable_tools": ["custom_tool"],
                "max_cache_size": 50,
            },
        })

        assert config.caching.enabled is True
        assert config.caching.prompt_cache_ttl == 600
        assert config.caching.tool_cache_ttl == 120
        assert config.caching.cacheable_tools == ["custom_tool"]
        assert config.caching.max_cache_size == 50

    def test_from_dict_caching_bool(self):
        """Test from_dict with caching as bool shorthand."""
        config = DeepAgentConfig.from_dict({"caching": True})

        assert config.caching.enabled is True
        # Other fields should be defaults
        assert config.caching.prompt_cache_ttl == 300

    def test_from_dict_retry_dict(self):
        """Test from_dict with retry as dict."""
        config = DeepAgentConfig.from_dict({
            "retry": {
                "enabled": True,
                "max_retries": 5,
                "backoff_base": 2.0,
                "use_circuit_breaker": True,
                "circuit_failure_threshold": 10,
                "circuit_reset_timeout": 120.0,
            },
        })

        assert config.retry.enabled is True
        assert config.retry.max_retries == 5
        assert config.retry.backoff_base == 2.0
        assert config.retry.use_circuit_breaker is True
        assert config.retry.circuit_failure_threshold == 10
        assert config.retry.circuit_reset_timeout == 120.0

    def test_from_dict_retry_bool(self):
        """Test from_dict with retry as bool shorthand."""
        config = DeepAgentConfig.from_dict({"retry": True})

        assert config.retry.enabled is True
        assert config.retry.max_retries == 2  # default

    def test_to_dict_includes_caching_retry(self):
        """Test to_dict includes caching and retry sections."""
        config = DeepAgentConfig()
        d = config.to_dict()

        assert "caching" in d
        assert d["caching"]["enabled"] is False
        assert "prompt_cache_ttl" in d["caching"]
        assert "cacheable_tools" in d["caching"]

        assert "retry" in d
        assert d["retry"]["enabled"] is False
        assert "max_retries" in d["retry"]
        assert "use_circuit_breaker" in d["retry"]

    def test_round_trip(self):
        """Test from_dict -> to_dict round trip preserves values."""
        original = {
            "caching": {
                "enabled": True,
                "prompt_cache_ttl": 600,
                "tool_cache_ttl": 120,
                "cacheable_tools": ["my_tool"],
                "max_cache_size": 50,
            },
            "retry": {
                "enabled": True,
                "max_retries": 3,
                "use_circuit_breaker": True,
            },
        }

        config = DeepAgentConfig.from_dict(original)
        d = config.to_dict()

        assert d["caching"]["enabled"] is True
        assert d["caching"]["prompt_cache_ttl"] == 600
        assert d["caching"]["cacheable_tools"] == ["my_tool"]
        assert d["retry"]["enabled"] is True
        assert d["retry"]["max_retries"] == 3
        assert d["retry"]["use_circuit_breaker"] is True


# --- Factory Wiring Tests ---


class TestFactoryCachingWiring:
    """Tests that factory properly wires caching middleware."""

    def test_caching_disabled_by_default(self):
        """Test that caching is disabled by default."""
        config = DeepAgentConfig()
        assert config.caching.enabled is False

    def test_caching_enabled_no_errors(self):
        """Test that enabling caching doesn't error during agent creation."""
        agent = create_deep_agent(config={
            "caching": {"enabled": True},
        })

        assert agent.config.caching.enabled is True
        # Tools should still exist after wrapping
        tool_names = [t.name for t in agent.get_all_tools()]
        assert len(tool_names) > 0

    def test_caching_wraps_cacheable_tools(self):
        """Test that cacheable tools get wrapped with caching."""
        agent = create_deep_agent(config={
            "caching": {
                "enabled": True,
                "cacheable_tools": ["list_skills"],
            },
        })

        # Tools should still exist in the agent (accessible via get_all_tools)
        tool_names = [t.name for t in agent.get_all_tools()]
        assert "list_skills" in tool_names

    def test_caching_config_propagates(self):
        """Test that harness config values are set correctly."""
        config = DeepAgentConfig.from_dict({
            "caching": {
                "enabled": True,
                "tool_cache_ttl": 120,
                "cacheable_tools": ["my_custom_tool"],
                "max_cache_size": 25,
            },
        })

        assert config.caching.tool_cache_ttl == 120
        assert "my_custom_tool" in config.caching.cacheable_tools
        assert config.caching.max_cache_size == 25


class TestFactoryRetryWiring:
    """Tests that factory properly wires retry middleware."""

    def test_retry_disabled_by_default(self):
        """Test that retry is disabled by default."""
        config = DeepAgentConfig()
        assert config.retry.enabled is False

    def test_retry_enabled_no_errors(self):
        """Test that enabling retry doesn't error during agent creation."""
        agent = create_deep_agent(config={
            "retry": {"enabled": True},
        })

        assert agent.config.retry.enabled is True

    def test_retry_with_circuit_breaker_config(self):
        """Test circuit breaker config when enabled."""
        config = DeepAgentConfig.from_dict({
            "retry": {
                "enabled": True,
                "use_circuit_breaker": True,
            },
        })

        assert config.retry.use_circuit_breaker is True

    def test_retry_with_circuit_breaker_no_errors(self):
        """Test that retry + circuit breaker doesn't error during creation."""
        agent = create_deep_agent(config={
            "retry": {
                "enabled": True,
                "use_circuit_breaker": True,
            },
        })

        assert agent.config.retry.enabled is True
        assert agent.config.retry.use_circuit_breaker is True

    def test_retry_tools_still_exist(self):
        """Test that tools still exist after retry wrapping."""
        agent = create_deep_agent(config={
            "retry": {"enabled": True},
        })

        tool_names = [t.name for t in agent.get_all_tools()]
        # Core tools should still be present
        assert "write_todos" in tool_names
        assert "read_file" in tool_names


class TestFactoryCachingAndRetryTogether:
    """Tests that caching and retry work together."""

    def test_both_enabled(self):
        """Test both caching and retry enabled simultaneously."""
        agent = create_deep_agent(config={
            "caching": {"enabled": True},
            "retry": {"enabled": True},
        })

        assert agent.config.caching.enabled is True
        assert agent.config.retry.enabled is True
        # Tools should still exist
        tool_names = [t.name for t in agent.get_all_tools()]
        assert len(tool_names) > 0

    def test_both_with_circuit_breaker(self):
        """Test caching + retry + circuit breaker all enabled."""
        agent = create_deep_agent(config={
            "caching": {"enabled": True},
            "retry": {
                "enabled": True,
                "use_circuit_breaker": True,
            },
        })

        assert agent.config.caching.enabled is True
        assert agent.config.retry.enabled is True
        assert agent.config.retry.use_circuit_breaker is True

    def test_tools_preserved_with_both(self):
        """Test that all tools are preserved when both are enabled."""
        # Create agent without caching/retry first
        baseline = create_deep_agent()
        baseline_tool_names = sorted(t.name for t in baseline.get_all_tools())

        # Create agent with both enabled
        wrapped = create_deep_agent(config={
            "caching": {"enabled": True},
            "retry": {"enabled": True},
        })
        wrapped_tool_names = sorted(t.name for t in wrapped.get_all_tools())

        # Same tools should exist (wrapping doesn't add/remove tools)
        assert baseline_tool_names == wrapped_tool_names


# --- VelHarness Integration Tests ---


class TestVelHarnessCachingRetry:
    """Tests for caching/retry through VelHarness constructor."""

    @pytest.fixture
    def mock_agent(self):
        """Create a mock Vel Agent."""
        with patch("vel_harness.factory.Agent") as MockAgent:
            mock_instance = MagicMock()
            mock_instance.run = MagicMock()
            mock_instance.run_stream = MagicMock()
            MockAgent.return_value = mock_instance
            yield MockAgent

    def test_caching_false_by_default(self, mock_agent):
        """Test VelHarness defaults caching to False."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
        )

        assert harness.config.caching.enabled is False

    def test_retry_false_by_default(self, mock_agent):
        """Test VelHarness defaults retry to False."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
        )

        assert harness.config.retry.enabled is False

    def test_caching_true(self, mock_agent):
        """Test VelHarness with caching=True."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            caching=True,
        )

        assert harness.config.caching.enabled is True

    def test_retry_true(self, mock_agent):
        """Test VelHarness with retry=True."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            retry=True,
        )

        assert harness.config.retry.enabled is True

    def test_both_true(self, mock_agent):
        """Test VelHarness with both caching and retry enabled."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            caching=True,
            retry=True,
        )

        assert harness.config.caching.enabled is True
        assert harness.config.retry.enabled is True
