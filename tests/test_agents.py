"""
Tests for Agent Registry

Tests the AgentConfig and AgentRegistry classes for typed subagent spawning.
"""

import pytest
from vel_harness.agents import AgentConfig, AgentRegistry, DEFAULT_AGENTS


class TestAgentConfig:
    """Tests for AgentConfig dataclass."""

    def test_basic_creation(self):
        """Test creating a basic AgentConfig."""
        config = AgentConfig(
            name="test-agent",
            system_prompt="You are a test agent.",
            tools=["read_file", "grep"],
            max_turns=20,
        )

        assert config.name == "test-agent"
        assert config.system_prompt == "You are a test agent."
        assert config.tools == ["read_file", "grep"]
        assert config.max_turns == 20

    def test_defaults(self):
        """Test AgentConfig default values."""
        config = AgentConfig(
            name="minimal",
            system_prompt="Minimal prompt",
        )

        assert config.tools == []
        assert config.max_turns == 50
        assert config.timeout == 300.0
        assert config.description == ""
        assert config.model is None

    def test_to_dict(self):
        """Test converting AgentConfig to dictionary."""
        config = AgentConfig(
            name="test",
            system_prompt="Short prompt",
            tools=["tool1"],
            max_turns=10,
            description="A test agent",
        )

        d = config.to_dict()

        assert d["name"] == "test"
        assert d["tools"] == ["tool1"]
        assert d["max_turns"] == 10
        assert d["description"] == "A test agent"

    def test_long_prompt_truncation(self):
        """Test that long prompts are truncated in to_dict."""
        long_prompt = "x" * 500
        config = AgentConfig(name="test", system_prompt=long_prompt)

        d = config.to_dict()

        assert len(d["system_prompt"]) == 203  # 200 + "..."
        assert d["system_prompt"].endswith("...")


class TestAgentRegistry:
    """Tests for AgentRegistry."""

    def test_default_agents_exist(self):
        """Test that default agents are registered."""
        registry = AgentRegistry()

        assert "default" in registry
        assert "explore" in registry
        assert "plan" in registry

    def test_default_agent_configs(self):
        """Test default agent configurations."""
        registry = AgentRegistry()

        default_config = registry.get("default")
        assert default_config.name == "default"
        assert "read_file" in default_config.tools
        assert "write_file" in default_config.tools
        assert default_config.max_turns == 50

        explore_config = registry.get("explore")
        assert explore_config.name == "explore"
        assert "read_file" in explore_config.tools
        assert "glob" in explore_config.tools
        assert explore_config.max_turns == 30

        plan_config = registry.get("plan")
        assert plan_config.name == "plan"
        assert "write_todos" in plan_config.tools
        assert plan_config.max_turns == 20

    def test_get_unknown_returns_default(self):
        """Test that getting unknown agent returns default."""
        registry = AgentRegistry()

        config = registry.get("nonexistent")

        assert config.name == "default"

    def test_register_custom_agent(self):
        """Test registering a custom agent."""
        registry = AgentRegistry()

        custom_config = AgentConfig(
            name="custom-agent",
            system_prompt="Custom prompt",
            tools=["custom_tool"],
            max_turns=5,
        )

        registry.register("custom", custom_config)

        assert "custom" in registry
        retrieved = registry.get("custom")
        assert retrieved.name == "custom-agent"
        assert retrieved.max_turns == 5

    def test_custom_agents_in_constructor(self):
        """Test passing custom agents to constructor."""
        custom = {
            "my-agent": AgentConfig(
                name="my-agent",
                system_prompt="My agent prompt",
                tools=["tool1"],
            )
        }

        registry = AgentRegistry(custom_agents=custom)

        assert "my-agent" in registry
        assert registry.get("my-agent").name == "my-agent"

    def test_list_agents(self):
        """Test listing available agents."""
        registry = AgentRegistry()

        agents = registry.list_agents()

        assert "default" in agents
        assert "explore" in agents
        assert "plan" in agents

    def test_get_descriptions(self):
        """Test getting agent descriptions."""
        registry = AgentRegistry()

        descriptions = registry.get_descriptions()

        assert "default:" in descriptions
        assert "explore:" in descriptions
        assert "plan:" in descriptions

    def test_unregister_custom_agent(self):
        """Test unregistering a custom agent."""
        registry = AgentRegistry()

        registry.register("temp", AgentConfig(
            name="temp",
            system_prompt="Temporary",
        ))

        assert "temp" in registry
        result = registry.unregister("temp")
        assert result is True
        assert "temp" not in registry

    def test_cannot_unregister_default_agent(self):
        """Test that default agents cannot be unregistered."""
        registry = AgentRegistry()

        result = registry.unregister("default")

        assert result is False
        assert "default" in registry

    def test_has_agent(self):
        """Test has_agent method."""
        registry = AgentRegistry()

        assert registry.has_agent("default") is True
        assert registry.has_agent("nonexistent") is False

    def test_len(self):
        """Test __len__ method."""
        registry = AgentRegistry()

        assert len(registry) >= 3  # At least default, explore, plan

    def test_get_all(self):
        """Test get_all method."""
        registry = AgentRegistry()

        all_agents = registry.get_all()

        assert isinstance(all_agents, dict)
        assert "default" in all_agents
        assert isinstance(all_agents["default"], AgentConfig)


class TestDefaultAgents:
    """Tests for DEFAULT_AGENTS constant."""

    def test_default_agents_defined(self):
        """Test that DEFAULT_AGENTS is defined correctly."""
        assert "default" in DEFAULT_AGENTS
        assert "explore" in DEFAULT_AGENTS
        assert "plan" in DEFAULT_AGENTS

    def test_explore_is_read_only(self):
        """Test that explore agent has read-only tools."""
        explore = DEFAULT_AGENTS["explore"]

        # Should have read tools
        assert "read_file" in explore.tools
        assert "glob" in explore.tools
        assert "grep" in explore.tools

        # Should NOT have write tools
        assert "write_file" not in explore.tools
        assert "edit_file" not in explore.tools

    def test_plan_has_planning_tools(self):
        """Test that plan agent has planning tools."""
        plan = DEFAULT_AGENTS["plan"]

        assert "write_todos" in plan.tools
