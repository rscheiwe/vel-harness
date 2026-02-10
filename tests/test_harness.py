"""
Tests for VelHarness

Tests the primary API for vel-harness.
"""

import pytest
import warnings
from unittest.mock import AsyncMock, MagicMock, patch

from vel_harness import (
    VelHarness,
    create_harness,
    create_research_harness,
    create_coding_harness,
    AgentConfig,
    AgentRegistry,
)


class TestVelHarnessInit:
    """Tests for VelHarness initialization."""

    @pytest.fixture
    def mock_agent(self):
        """Create a mock Vel Agent."""
        with patch("vel_harness.factory.Agent") as MockAgent:
            mock_instance = MagicMock()
            mock_instance.run = AsyncMock(return_value=MagicMock(content="test response"))
            mock_instance.run_stream = AsyncMock()
            MockAgent.return_value = mock_instance
            yield MockAgent

    def test_basic_init(self, mock_agent):
        """Test basic VelHarness initialization."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
        )

        assert harness.model["provider"] == "anthropic"
        assert harness.model["model"] == "claude-sonnet-4-5-20250929"
        assert harness.agent_registry is not None

    def test_init_with_skill_dirs(self, mock_agent, tmp_path):
        """Test initialization with skill directories."""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()

        harness = VelHarness(
            model={"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
            skill_dirs=[str(skill_dir)],
        )

        assert harness._skill_dirs == [str(skill_dir)]

    def test_init_with_custom_agents(self, mock_agent):
        """Test initialization with custom agent types."""
        custom_agents = {
            "my-agent": AgentConfig(
                name="my-agent",
                system_prompt="Custom agent",
                tools=["tool1"],
                max_turns=10,
            )
        }

        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            custom_agents=custom_agents,
        )

        assert "my-agent" in harness.agent_registry

    def test_default_agents_available(self, mock_agent):
        """Test that default agents are available."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
        )

        agent_types = harness.list_agent_types()

        assert "default" in agent_types
        assert "explore" in agent_types
        assert "plan" in agent_types


class TestVelHarnessRegistry:
    """Tests for VelHarness agent registry integration."""

    @pytest.fixture
    def mock_agent(self):
        """Create a mock Vel Agent."""
        with patch("vel_harness.factory.Agent") as MockAgent:
            mock_instance = MagicMock()
            MockAgent.return_value = mock_instance
            yield MockAgent

    def test_register_agent(self, mock_agent):
        """Test registering a custom agent."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
        )

        harness.register_agent(
            "custom",
            AgentConfig(name="custom", system_prompt="Custom", tools=[]),
        )

        assert "custom" in harness.list_agent_types()

    def test_agent_registry_property(self, mock_agent):
        """Test agent_registry property."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
        )

        assert isinstance(harness.agent_registry, AgentRegistry)


class TestCreateHarnessFactories:
    """Tests for harness factory functions."""

    @pytest.fixture
    def mock_agent(self):
        """Create a mock Vel Agent."""
        with patch("vel_harness.factory.Agent") as MockAgent:
            mock_instance = MagicMock()
            MockAgent.return_value = mock_instance
            yield MockAgent

    def test_create_harness_defaults(self, mock_agent):
        """Test create_harness with defaults."""
        harness = create_harness()

        assert harness.model["provider"] == "anthropic"
        assert "claude-sonnet" in harness.model["model"]

    def test_create_harness_custom_model(self, mock_agent):
        """Test create_harness with custom model."""
        harness = create_harness(
            model={"provider": "openai", "model": "gpt-4o"},
        )

        assert harness.model["provider"] == "openai"
        assert harness.model["model"] == "gpt-4o"

    def test_create_research_harness(self, mock_agent):
        """Test create_research_harness."""
        harness = create_research_harness()

        assert harness is not None
        # Research harness should have subagents enabled
        assert harness.config.subagents.enabled is True

    def test_create_coding_harness(self, mock_agent, tmp_path):
        """Test create_coding_harness."""
        harness = create_coding_harness(
            working_directory=str(tmp_path),
        )

        assert harness is not None
        assert harness.config.sandbox.enabled is True


class TestDeprecationWarnings:
    """Tests for deprecation warnings."""

    def test_deep_agent_deprecation_warning(self):
        """Test that DeepAgent raises deprecation warning."""
        from vel_harness.factory import DeepAgent

        # Reset the class-level flag
        DeepAgent._deprecation_warned = False

        with pytest.warns(DeprecationWarning, match="DeepAgent is deprecated"):
            with patch("vel_harness.factory.Agent"):
                from vel_harness.config import DeepAgentConfig
                config = DeepAgentConfig()
                # This should trigger the warning
                agent = DeepAgent(
                    config=config,
                    agent=MagicMock(),
                    middlewares={},
                )

    def test_vel_harness_no_deprecation_warning(self):
        """Test that VelHarness doesn't trigger deprecation warning."""
        from vel_harness.factory import DeepAgent

        # Reset the class-level flag
        DeepAgent._deprecation_warned = False

        with patch("vel_harness.factory.Agent"):
            # VelHarness should not trigger deprecation warning
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                harness = VelHarness(
                    model={"provider": "anthropic", "model": "test"},
                )

                # Filter for DeprecationWarning specifically about DeepAgent
                deprecation_warnings = [
                    x for x in w
                    if issubclass(x.category, DeprecationWarning)
                    and "DeepAgent" in str(x.message)
                ]
                assert len(deprecation_warnings) == 0
