"""
Tests for Agent Definition (WS5)

Tests the Agent SDK-compatible AgentDefinition including:
- AgentDefinition creation and defaults
- to_agent_config() conversion
- Model shorthand resolution (sonnet/opus/haiku/inherit)
- Full model ID passthrough
- from_dict() and from_value() factories
- AgentRegistry accepts both AgentConfig and AgentDefinition
- AgentRegistry accepts raw dicts (SDK-style)
- VelHarness integration with Agent SDK-style agent dicts
"""

import pytest
from unittest.mock import MagicMock, patch

from vel_harness.agents import (
    AgentConfig,
    AgentDefinition,
    AgentRegistry,
    MODEL_SHORTHAND_MAP,
)
from vel_harness import VelHarness


# --- AgentDefinition Tests ---


class TestAgentDefinition:
    """Tests for AgentDefinition dataclass."""

    def test_default_values(self):
        """Test default AgentDefinition values."""
        defn = AgentDefinition()
        assert defn.description == ""
        assert defn.prompt == ""
        assert defn.tools == []
        assert defn.model is None
        assert defn.max_turns == 50
        assert defn.timeout == 300.0

    def test_custom_values(self):
        """Test AgentDefinition with custom values."""
        defn = AgentDefinition(
            description="Research agent",
            prompt="You are a research assistant.",
            tools=["read_file", "grep", "glob"],
            model="haiku",
            max_turns=20,
            timeout=120.0,
        )
        assert defn.description == "Research agent"
        assert defn.prompt == "You are a research assistant."
        assert defn.tools == ["read_file", "grep", "glob"]
        assert defn.model == "haiku"
        assert defn.max_turns == 20
        assert defn.timeout == 120.0

    def test_repr(self):
        """Test string representation."""
        defn = AgentDefinition(
            description="Test",
            tools=["read_file"],
            model="sonnet",
        )
        r = repr(defn)
        assert "Test" in r
        assert "read_file" in r
        assert "sonnet" in r


# --- Model Shorthand Resolution Tests ---


class TestModelShorthandResolution:
    """Tests for AgentDefinition._resolve_model()."""

    def test_sonnet_shorthand(self):
        """Test 'sonnet' resolves to claude-sonnet model."""
        result = AgentDefinition._resolve_model("sonnet")
        assert result == {"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"}

    def test_opus_shorthand(self):
        """Test 'opus' resolves to claude-opus model."""
        result = AgentDefinition._resolve_model("opus")
        assert result == {"provider": "anthropic", "model": "claude-opus-4-6"}

    def test_haiku_shorthand(self):
        """Test 'haiku' resolves to claude-haiku model."""
        result = AgentDefinition._resolve_model("haiku")
        assert result == {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"}

    def test_inherit_returns_none(self):
        """Test 'inherit' returns None (use parent model)."""
        result = AgentDefinition._resolve_model("inherit")
        assert result is None

    def test_none_returns_none(self):
        """Test None returns None (use parent model)."""
        result = AgentDefinition._resolve_model(None)
        assert result is None

    def test_full_model_id(self):
        """Test full model ID passed through."""
        result = AgentDefinition._resolve_model("claude-3-5-sonnet-20241022")
        assert result == {"provider": "anthropic", "model": "claude-3-5-sonnet-20241022"}

    def test_custom_model_string(self):
        """Test custom model string treated as model ID."""
        result = AgentDefinition._resolve_model("my-custom-model")
        assert result == {"provider": "anthropic", "model": "my-custom-model"}

    def test_model_shorthand_map_not_mutated(self):
        """Test _resolve_model returns a new dict, not a reference."""
        result = AgentDefinition._resolve_model("sonnet")
        result["extra"] = "test"
        # Original should not be modified
        assert "extra" not in MODEL_SHORTHAND_MAP["sonnet"]


# --- to_agent_config Tests ---


class TestToAgentConfig:
    """Tests for AgentDefinition.to_agent_config()."""

    def test_basic_conversion(self):
        """Test basic conversion to AgentConfig."""
        defn = AgentDefinition(
            description="Explorer",
            prompt="You explore code.",
            tools=["read_file", "grep"],
            model="haiku",
            max_turns=30,
            timeout=120.0,
        )
        config = defn.to_agent_config("explorer")

        assert isinstance(config, AgentConfig)
        assert config.name == "explorer"
        assert config.description == "Explorer"
        assert config.system_prompt == "You explore code."
        assert config.tools == ["read_file", "grep"]
        assert config.model == {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"}
        assert config.max_turns == 30
        assert config.timeout == 120.0

    def test_inherit_model(self):
        """Test conversion with inherit model."""
        defn = AgentDefinition(model="inherit")
        config = defn.to_agent_config("test")
        assert config.model is None

    def test_none_model(self):
        """Test conversion with None model."""
        defn = AgentDefinition(model=None)
        config = defn.to_agent_config("test")
        assert config.model is None

    def test_tools_are_copied(self):
        """Test tools list is copied (not a reference)."""
        defn = AgentDefinition(tools=["read_file"])
        config = defn.to_agent_config("test")
        config.tools.append("extra")
        assert "extra" not in defn.tools


# --- from_dict Tests ---


class TestFromDict:
    """Tests for AgentDefinition.from_dict()."""

    def test_from_dict_full(self):
        """Test from_dict with all fields."""
        defn = AgentDefinition.from_dict({
            "description": "Planner",
            "prompt": "You make plans.",
            "tools": ["write_todos"],
            "model": "opus",
            "max_turns": 10,
            "timeout": 60.0,
        })
        assert defn.description == "Planner"
        assert defn.prompt == "You make plans."
        assert defn.tools == ["write_todos"]
        assert defn.model == "opus"
        assert defn.max_turns == 10
        assert defn.timeout == 60.0

    def test_from_dict_minimal(self):
        """Test from_dict with minimal fields."""
        defn = AgentDefinition.from_dict({})
        assert defn.description == ""
        assert defn.prompt == ""
        assert defn.tools == []
        assert defn.model is None
        assert defn.max_turns == 50

    def test_from_dict_partial(self):
        """Test from_dict with some fields."""
        defn = AgentDefinition.from_dict({
            "description": "Helper",
            "model": "sonnet",
        })
        assert defn.description == "Helper"
        assert defn.model == "sonnet"
        assert defn.tools == []  # Default


# --- from_value Tests ---


class TestFromValue:
    """Tests for AgentDefinition.from_value()."""

    def test_from_agent_definition(self):
        """Test passthrough of AgentDefinition instance."""
        original = AgentDefinition(description="Test")
        result = AgentDefinition.from_value(original)
        assert result is original

    def test_from_agent_config(self):
        """Test conversion from AgentConfig."""
        config = AgentConfig(
            name="test",
            system_prompt="Test prompt",
            tools=["read_file"],
            description="Test agent",
        )
        defn = AgentDefinition.from_value(config)
        assert defn.description == "Test agent"
        assert defn.prompt == "Test prompt"
        assert defn.tools == ["read_file"]

    def test_from_dict(self):
        """Test conversion from dict."""
        defn = AgentDefinition.from_value({
            "description": "Dict agent",
            "model": "haiku",
        })
        assert defn.description == "Dict agent"
        assert defn.model == "haiku"


# --- AgentRegistry Tests ---


class TestAgentRegistryBothFormats:
    """Tests for AgentRegistry accepting both formats."""

    def test_register_agent_config(self):
        """Test registering an AgentConfig."""
        registry = AgentRegistry()
        config = AgentConfig(
            name="custom",
            system_prompt="Custom agent",
            tools=["read_file"],
            description="Custom agent",
        )
        registry.register("custom", config)
        assert registry.has_agent("custom")
        result = registry.get("custom")
        assert result.name == "custom"

    def test_register_agent_definition(self):
        """Test registering an AgentDefinition (auto-converted)."""
        registry = AgentRegistry()
        defn = AgentDefinition(
            description="SDK agent",
            prompt="You are an SDK agent.",
            tools=["grep"],
            model="haiku",
        )
        registry.register("sdk-agent", defn)
        assert registry.has_agent("sdk-agent")

        result = registry.get("sdk-agent")
        assert isinstance(result, AgentConfig)
        assert result.name == "sdk-agent"
        assert result.description == "SDK agent"
        assert result.system_prompt == "You are an SDK agent."
        assert result.model == {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"}

    def test_register_dict(self):
        """Test registering a raw dict (SDK-style)."""
        registry = AgentRegistry()
        registry.register("dict-agent", {
            "description": "Dict agent",
            "prompt": "You are from a dict.",
            "tools": ["read_file", "glob"],
            "model": "sonnet",
        })
        assert registry.has_agent("dict-agent")

        result = registry.get("dict-agent")
        assert isinstance(result, AgentConfig)
        assert result.name == "dict-agent"
        assert result.description == "Dict agent"

    def test_custom_agents_in_constructor_with_definitions(self):
        """Test passing AgentDefinitions in constructor."""
        custom = {
            "researcher": AgentDefinition(
                description="Research agent",
                prompt="Research things.",
                model="haiku",
            ),
        }
        registry = AgentRegistry(custom_agents=custom)
        assert registry.has_agent("researcher")
        result = registry.get("researcher")
        assert result.model == {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"}

    def test_custom_agents_in_constructor_with_dicts(self):
        """Test passing SDK-style dicts in constructor."""
        custom = {
            "analyzer": {
                "description": "Analysis agent",
                "prompt": "Analyze code.",
                "tools": ["read_file", "grep"],
                "model": "opus",
            },
        }
        registry = AgentRegistry(custom_agents=custom)
        assert registry.has_agent("analyzer")
        result = registry.get("analyzer")
        assert result.model == {"provider": "anthropic", "model": "claude-opus-4-6"}

    def test_default_agents_still_exist(self):
        """Test default agents are preserved with custom agents."""
        registry = AgentRegistry(custom_agents={
            "custom": AgentDefinition(description="Custom"),
        })
        assert registry.has_agent("default")
        assert registry.has_agent("explore")
        assert registry.has_agent("plan")
        assert registry.has_agent("custom")

    def test_mixed_formats(self):
        """Test mixing AgentConfig, AgentDefinition, and dicts."""
        custom = {
            "config-agent": AgentConfig(
                name="config-agent",
                system_prompt="Config agent",
                description="From config",
            ),
            "defn-agent": AgentDefinition(
                description="From definition",
                prompt="Definition agent",
                model="haiku",
            ),
            "dict-agent": {
                "description": "From dict",
                "prompt": "Dict agent",
                "model": "sonnet",
            },
        }
        registry = AgentRegistry(custom_agents=custom)
        assert registry.has_agent("config-agent")
        assert registry.has_agent("defn-agent")
        assert registry.has_agent("dict-agent")
        assert len(registry) == 10  # 7 default + 3 custom


# --- VelHarness Integration Tests ---


class TestVelHarnessAgentDefinition:
    """Tests for AgentDefinition through VelHarness."""

    @pytest.fixture
    def mock_agent(self):
        """Create a mock Vel Agent."""
        with patch("vel_harness.factory.Agent") as MockAgent:
            mock_instance = MagicMock()
            MockAgent.return_value = mock_instance
            yield MockAgent

    def test_with_agent_definitions(self, mock_agent):
        """Test VelHarness with AgentDefinition custom agents."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            custom_agents={
                "researcher": AgentDefinition(
                    description="Research agent",
                    prompt="Research code.",
                    tools=["read_file", "grep"],
                    model="haiku",
                ),
            },
        )
        assert "researcher" in harness.agent_registry
        config = harness.agent_registry.get("researcher")
        assert config.model == {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"}

    def test_with_sdk_style_dicts(self, mock_agent):
        """Test VelHarness with SDK-style agent dicts."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            custom_agents={
                "planner": {
                    "description": "Planning agent",
                    "prompt": "Create plans.",
                    "model": "opus",
                },
            },
        )
        assert "planner" in harness.agent_registry
        config = harness.agent_registry.get("planner")
        assert config.model == {"provider": "anthropic", "model": "claude-opus-4-6"}

    def test_register_agent_with_definition(self, mock_agent):
        """Test harness.register_agent with AgentDefinition."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
        )
        harness.register_agent("new-agent", AgentDefinition(
            description="New agent",
            prompt="Do new things.",
            model="sonnet",
        ))
        assert "new-agent" in harness.agent_registry

    def test_register_agent_with_dict(self, mock_agent):
        """Test harness.register_agent with dict."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
        )
        harness.register_agent("dict-agent", {
            "description": "Dict agent",
            "prompt": "From dict.",
        })
        assert "dict-agent" in harness.agent_registry

    def test_backwards_compat_agent_config(self, mock_agent):
        """Test backwards compatibility with AgentConfig."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            custom_agents={
                "legacy": AgentConfig(
                    name="legacy",
                    system_prompt="Legacy agent",
                    description="From AgentConfig",
                ),
            },
        )
        assert "legacy" in harness.agent_registry
        config = harness.agent_registry.get("legacy")
        assert config.system_prompt == "Legacy agent"
