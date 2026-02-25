"""
Factory Tests

Tests for deep agent factory and configuration.
"""

import tempfile
from pathlib import Path

import pytest

from vel_harness.config import (
    DeepAgentConfig,
    ModelConfig,
    SandboxConfig,
    DatabaseConfig,
    SkillsConfig,
    SubagentsConfig,
    PlanningConfig,
    FilesystemConfig,
)
from vel_harness.factory import (
    DeepAgent,
    _apply_tool_input_rewriters,
    _is_tool_output_failure,
    create_deep_agent,
    create_research_agent,
    create_data_agent,
    create_coding_agent,
)


# Configuration Tests


class TestModelConfig:
    """Tests for ModelConfig."""

    def test_default_config(self) -> None:
        """Test default model configuration."""
        config = ModelConfig()

        assert config.provider == "anthropic"
        assert config.model == "claude-sonnet-4-5-20250929"
        assert config.temperature is None
        assert config.max_tokens is None

    def test_custom_config(self) -> None:
        """Test custom model configuration."""
        config = ModelConfig(
            provider="openai",
            model="gpt-4",
            temperature=0.7,
            max_tokens=4096,
        )

        assert config.provider == "openai"
        assert config.model == "gpt-4"
        assert config.temperature == 0.7
        assert config.max_tokens == 4096

    def test_to_dict(self) -> None:
        """Test converting to dictionary."""
        config = ModelConfig(
            provider="anthropic",
            model="claude-sonnet-4-5-20250929",
            temperature=0.5,
        )

        d = config.to_dict()

        assert d["provider"] == "anthropic"
        assert d["model"] == "claude-sonnet-4-5-20250929"
        assert d["temperature"] == 0.5


def test_apply_tool_input_rewriters_applies_in_order() -> None:
    def first(_tool: str, kwargs: dict[str, object], _wd: object) -> dict[str, object]:
        out = dict(kwargs)
        out["first"] = True
        return out

    def second(_tool: str, kwargs: dict[str, object], _wd: object) -> tuple[dict[str, object], str]:
        out = dict(kwargs)
        out["second"] = True
        return out, "normalized-input"

    out, reasons = _apply_tool_input_rewriters(
        tool_name="execute_python",
        kwargs={"code": "print(1)"},
        working_dir="/tmp",
        rewriters=[first, second],
    )
    assert out.get("first") is True
    assert out.get("second") is True
    assert reasons == ["normalized-input"]


def test_apply_tool_input_rewriters_ignores_none() -> None:
    out, reasons = _apply_tool_input_rewriters(
        tool_name="execute_python",
        kwargs={"code": "print(1)"},
        working_dir="/tmp",
        rewriters=[lambda *_: None],
    )
    assert out == {"code": "print(1)"}
    assert reasons == []


def test_is_tool_output_failure_uses_exit_code_and_success() -> None:
    failed, error, error_type = _is_tool_output_failure(
        {"exit_code": 1, "success": False, "stderr": "Traceback"}
    )
    assert failed is True
    assert "Traceback" in error
    assert error_type == "ToolOutputStderr"


class TestDeepAgentConfig:
    """Tests for DeepAgentConfig."""

    def test_default_config(self) -> None:
        """Test default configuration."""
        config = DeepAgentConfig()

        assert config.name == "deep-agent"
        assert config.planning.enabled is True
        assert config.filesystem.enabled is True
        assert config.sandbox.enabled is True
        assert config.database.enabled is False
        assert config.skills.enabled is True
        assert config.subagents.enabled is True

    def test_from_dict_minimal(self) -> None:
        """Test creating config from minimal dict."""
        config = DeepAgentConfig.from_dict({
            "name": "my-agent",
        })

        assert config.name == "my-agent"
        assert config.planning.enabled is True  # default

    def test_from_dict_full(self) -> None:
        """Test creating config from full dict."""
        config = DeepAgentConfig.from_dict({
            "name": "custom-agent",
            "model": {
                "provider": "openai",
                "model": "gpt-4",
            },
            "planning": {"enabled": False},
            "sandbox": {
                "enabled": True,
                "network": True,
                "timeout": 60,
            },
            "database": {
                "enabled": True,
                "readonly": False,
            },
            "skills": {
                "enabled": True,
                "skill_dirs": ["/path/to/skills"],
                "auto_activate": False,
            },
            "subagents": {
                "enabled": True,
                "max_concurrent": 3,
            },
        })

        assert config.name == "custom-agent"
        assert config.model.provider == "openai"
        assert config.planning.enabled is False
        assert config.sandbox.network is True
        assert config.sandbox.timeout == 60
        assert config.database.enabled is True
        assert config.database.readonly is False
        assert config.skills.skill_dirs == ["/path/to/skills"]
        assert config.skills.auto_activate is False
        assert config.subagents.max_concurrent == 3

    def test_from_dict_bool_shortcuts(self) -> None:
        """Test boolean shortcuts for middleware config."""
        config = DeepAgentConfig.from_dict({
            "planning": False,
            "database": True,
        })

        assert config.planning.enabled is False
        assert config.database.enabled is True

    def test_to_dict(self) -> None:
        """Test converting config to dict."""
        config = DeepAgentConfig(name="test-agent")
        d = config.to_dict()

        assert d["name"] == "test-agent"
        assert "model" in d
        assert "planning" in d
        assert "sandbox" in d


# Factory Tests


class TestCreateDeepAgent:
    """Tests for create_deep_agent factory."""

    def test_create_default_agent(self) -> None:
        """Test creating agent with defaults."""
        agent = create_deep_agent()

        assert isinstance(agent, DeepAgent)
        assert agent.config.name == "deep-agent"
        assert "planning" in agent.middlewares
        assert "filesystem" in agent.middlewares

    def test_create_with_model(self) -> None:
        """Test creating agent with custom model."""
        agent = create_deep_agent(
            model={"provider": "openai", "model": "gpt-4"},
        )

        assert agent.config.model.provider == "openai"
        assert agent.config.model.model == "gpt-4"

    def test_create_with_model_config(self) -> None:
        """Test creating agent with ModelConfig."""
        agent = create_deep_agent(
            model=ModelConfig(provider="anthropic", model="claude-opus-4-20250514"),
        )

        assert agent.config.model.model == "claude-opus-4-20250514"

    def test_create_with_sandbox_disabled(self) -> None:
        """Test creating agent without sandbox."""
        agent = create_deep_agent(sandbox=False)

        assert agent.config.sandbox.enabled is False
        # Should have regular filesystem, not sandbox
        assert "filesystem" in agent.middlewares

    def test_create_with_database(self) -> None:
        """Test creating agent with database enabled."""
        agent = create_deep_agent(database=True)

        assert agent.config.database.enabled is True
        assert "database" in agent.middlewares

    def test_create_with_config_dict(self) -> None:
        """Test creating agent from config dict."""
        agent = create_deep_agent(config={
            "name": "custom-agent",
            "max_turns": 100,
            "planning": {"enabled": True},
        })

        assert agent.config.name == "custom-agent"
        assert agent.config.max_turns == 100

    def test_create_with_config_object(self) -> None:
        """Test creating agent from config object."""
        config = DeepAgentConfig(
            name="config-agent",
            system_prompt="You are helpful.",
        )

        agent = create_deep_agent(config=config)

        assert agent.config.name == "config-agent"
        assert agent.config.system_prompt == "You are helpful."

    def test_create_with_skill_dirs(self) -> None:
        """Test creating agent with skill directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = create_deep_agent(skill_dirs=[tmpdir])

            assert agent.config.skills.skill_dirs == [tmpdir]
            assert "skills" in agent.middlewares


class TestDeepAgent:
    """Tests for DeepAgent class."""

    def test_get_all_tools(self) -> None:
        """Test getting all tools from middlewares."""
        agent = create_deep_agent()
        tools = agent.get_all_tools()

        assert len(tools) > 0
        tool_names = [t.name for t in tools]

        # Should have planning tools
        assert "write_todos" in tool_names

        # Should have filesystem tools
        assert "read_file" in tool_names
        assert "write_file" in tool_names

    def test_get_system_prompt(self) -> None:
        """Test getting combined system prompt."""
        agent = create_deep_agent(
            system_prompt="Custom base prompt.",
        )

        prompt = agent.get_system_prompt()

        assert "Custom base prompt." in prompt
        # Should include middleware segments
        assert "Planning" in prompt or "Todo" in prompt

    def test_get_middleware(self) -> None:
        """Test getting specific middleware."""
        agent = create_deep_agent()

        planning = agent.get_middleware("planning")
        assert planning is not None

        nonexistent = agent.get_middleware("nonexistent")
        assert nonexistent is None

    def test_middleware_properties(self) -> None:
        """Test middleware property accessors."""
        agent = create_deep_agent(database=True)

        assert agent.planning is not None
        assert agent.filesystem is not None
        assert agent.skills is not None
        assert agent.subagents is not None
        assert agent.database is not None

    def test_get_state(self) -> None:
        """Test getting agent state."""
        agent = create_deep_agent()
        state = agent.get_state()

        assert "config" in state
        assert "middlewares" in state
        assert "planning" in state["middlewares"]

    def test_load_state(self) -> None:
        """Test loading agent state."""
        agent = create_deep_agent()

        # Modify planning state
        if agent.planning:
            agent.planning.todo_list._items = []  # Clear todos

        # Save state
        state = agent.get_state()

        # Create new agent and load state
        new_agent = create_deep_agent()
        new_agent.load_state(state)

        # States should match
        assert new_agent.get_state()["middlewares"]["planning"] == state["middlewares"]["planning"]


class TestSpecializedAgents:
    """Tests for specialized agent factories."""

    def test_create_research_agent(self) -> None:
        """Test creating research agent."""
        agent = create_research_agent()

        assert isinstance(agent, DeepAgent)
        assert "research" in agent.config.system_prompt.lower()
        assert "subagents" in agent.middlewares

    def test_create_research_agent_with_skills(self) -> None:
        """Test research agent with skill directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = create_research_agent(skill_dirs=[tmpdir])

            assert agent.config.skills.skill_dirs == [tmpdir]

    def test_create_data_agent(self) -> None:
        """Test creating data agent."""
        agent = create_data_agent()

        assert isinstance(agent, DeepAgent)
        assert "data" in agent.config.system_prompt.lower()
        assert agent.config.database.enabled is True
        assert "database" in agent.middlewares

    def test_create_coding_agent(self) -> None:
        """Test creating coding agent."""
        agent = create_coding_agent()

        assert isinstance(agent, DeepAgent)
        assert "code" in agent.config.system_prompt.lower() or "developer" in agent.config.system_prompt.lower()
        assert agent.config.sandbox.enabled is True

    def test_create_coding_agent_with_working_dir(self) -> None:
        """Test coding agent with custom working directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = create_coding_agent(working_dir=tmpdir)

            assert agent.config.sandbox.working_dir == tmpdir


# Integration Tests


class TestFactoryIntegration:
    """Integration tests for agent factory."""

    def test_full_agent_creation(self) -> None:
        """Test creating a fully configured agent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create skill file
            skill_path = Path(tmpdir) / "test_skill.md"
            skill_path.write_text("""---
name: Test Skill
description: A test skill
triggers:
  - test
---

# Test Instructions

Do the test thing.
""")

            agent = create_deep_agent(
                config={
                    "name": "full-test-agent",
                    "model": {"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
                    "planning": {"enabled": True},
                    "sandbox": {"enabled": True, "timeout": 60},
                    "database": {"enabled": True, "readonly": True},
                    "skills": {"enabled": True, "skill_dirs": [tmpdir]},
                    "subagents": {"enabled": True, "max_concurrent": 3},
                },
                system_prompt="You are a test agent.",
            )

            # Verify all components
            assert agent.config.name == "full-test-agent"
            assert agent.planning is not None
            assert agent.filesystem is not None
            assert agent.database is not None
            assert agent.skills is not None
            assert agent.subagents is not None

            # Verify tools are available
            tools = agent.get_all_tools()
            tool_names = [t.name for t in tools]

            assert "write_todos" in tool_names
            assert "read_file" in tool_names
            assert "sql_query" in tool_names
            assert "list_skills" in tool_names
            assert "spawn_subagent" in tool_names

            # Verify system prompt
            prompt = agent.get_system_prompt()
            assert "You are a test agent" in prompt

    def test_agent_tool_categories(self) -> None:
        """Test that agent tools have proper categories."""
        agent = create_deep_agent(database=True)
        tools = agent.get_all_tools()

        categories = set(t.category for t in tools)

        assert "planning" in categories
        assert "filesystem" in categories
        assert "database" in categories
        assert "skills" in categories
        assert "subagents" in categories
