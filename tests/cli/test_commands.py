"""
Tests for valis_cli.commands
"""

import tempfile
from pathlib import Path

import pytest

from valis_cli.commands import (
    CommandResult,
    get_registry,
)
from valis_cli.commands.base import Command, CommandRegistry
from valis_cli.commands.help import ClearCommand, ExitCommand, HelpCommand
from valis_cli.commands.reset import ResetCommand
from valis_cli.commands.skills import SkillsCommand
from valis_cli.config import Config


class TestCommandResult:
    """Tests for CommandResult."""

    def test_success_result(self):
        """Test successful command result."""
        result = CommandResult(success=True, message="Done")
        assert result.success is True
        assert result.message == "Done"
        assert result.should_exit is False

    def test_failure_result(self):
        """Test failed command result."""
        result = CommandResult(success=False, message="Error")
        assert result.success is False
        assert result.message == "Error"

    def test_exit_result(self):
        """Test result that triggers exit."""
        result = CommandResult(success=True, should_exit=True)
        assert result.should_exit is True


class TestCommandRegistry:
    """Tests for CommandRegistry."""

    def test_register_command(self):
        """Test registering a command."""
        registry = CommandRegistry()

        class TestCommand(Command):
            name = "test"
            description = "Test command"
            usage = "/test"

            async def execute(self, args, context):
                return CommandResult(success=True)

        registry.register(TestCommand())
        assert registry.get("test") is not None

    def test_get_by_alias(self):
        """Test getting command by alias."""
        registry = CommandRegistry()

        class TestCommand(Command):
            name = "test"
            aliases = ["t", "tst"]

            async def execute(self, args, context):
                return CommandResult(success=True)

        registry.register(TestCommand())
        assert registry.get("t") is not None
        assert registry.get("tst") is not None

    def test_list_commands(self):
        """Test listing all commands."""
        registry = CommandRegistry()

        class Cmd1(Command):
            name = "cmd1"

            async def execute(self, args, context):
                return CommandResult(success=True)

        class Cmd2(Command):
            name = "cmd2"

            async def execute(self, args, context):
                return CommandResult(success=True)

        registry.register(Cmd1())
        registry.register(Cmd2())

        commands = registry.list_commands()
        assert len(commands) == 2


class TestHelpCommand:
    """Tests for HelpCommand."""

    @pytest.mark.asyncio
    async def test_general_help(self):
        """Test general help output."""
        cmd = HelpCommand()
        result = await cmd.execute([], {})
        assert result.success is True
        assert "Available Commands" in result.message

    @pytest.mark.asyncio
    async def test_specific_help(self):
        """Test help for specific command."""
        cmd = HelpCommand()
        result = await cmd.execute(["exit"], {})
        assert result.success is True
        assert "exit" in result.message.lower()

    @pytest.mark.asyncio
    async def test_unknown_command_help(self):
        """Test help for unknown command."""
        cmd = HelpCommand()
        result = await cmd.execute(["nonexistent"], {})
        assert result.success is False


class TestExitCommand:
    """Tests for ExitCommand."""

    @pytest.mark.asyncio
    async def test_exit_sets_flag(self):
        """Test exit command sets should_exit flag."""
        cmd = ExitCommand()
        result = await cmd.execute([], {})
        assert result.success is True
        assert result.should_exit is True


class TestClearCommand:
    """Tests for ClearCommand."""

    @pytest.mark.asyncio
    async def test_clear_returns_action(self):
        """Test clear command returns clear action."""
        cmd = ClearCommand()
        result = await cmd.execute([], {})
        assert result.success is True
        assert result.data.get("action") == "clear"


class TestResetCommand:
    """Tests for ResetCommand."""

    @pytest.mark.asyncio
    async def test_reset_without_agent(self):
        """Test reset fails without agent."""
        cmd = ResetCommand()
        result = await cmd.execute([], {})
        assert result.success is False
        assert "No agent" in result.message

    @pytest.mark.asyncio
    async def test_reset_with_mock_agent(self):
        """Test reset with mock agent."""

        class MockAgent:
            reset_called = False

            def reset_session(self):
                self.reset_called = True

        agent = MockAgent()
        cmd = ResetCommand()
        result = await cmd.execute([], {"agent": agent})
        assert result.success is True
        assert agent.reset_called is True


class TestSkillsCommand:
    """Tests for SkillsCommand."""

    @pytest.mark.asyncio
    async def test_skills_without_config(self):
        """Test skills fails without config."""
        cmd = SkillsCommand()
        result = await cmd.execute([], {})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_skills_empty(self):
        """Test skills with no skills found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(global_dir=Path(tmpdir))
            config.ensure_dirs()

            cmd = SkillsCommand()
            result = await cmd.execute([], {"config": config})
            assert result.success is True
            assert "No skills found" in result.message

    @pytest.mark.asyncio
    async def test_skills_found(self):
        """Test skills with skills present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            global_dir = Path(tmpdir)
            skills_dir = global_dir / "skills"
            skills_dir.mkdir(parents=True)

            # Create a skill file
            (skills_dir / "test_skill.py").write_text("# Test skill")

            config = Config(global_dir=global_dir)

            cmd = SkillsCommand()
            result = await cmd.execute([], {"config": config})
            assert result.success is True
            assert "test_skill" in result.message


class TestGlobalRegistry:
    """Tests for global command registry."""

    def test_registry_has_builtin_commands(self):
        """Test global registry has built-in commands."""
        registry = get_registry()
        assert registry.get("help") is not None
        assert registry.get("exit") is not None
        assert registry.get("clear") is not None
        assert registry.get("reset") is not None
        assert registry.get("skills") is not None
        assert registry.get("config") is not None
        assert registry.get("model") is not None

    def test_registry_aliases_work(self):
        """Test command aliases in global registry."""
        registry = get_registry()
        assert registry.get("h") is not None  # alias for help
        assert registry.get("q") is not None  # alias for quit/exit
        assert registry.get("?") is not None  # alias for help
