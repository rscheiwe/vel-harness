"""
Help Command

Display help information.
"""

from typing import Any, Dict

from valis_cli.commands.base import Command, CommandResult, get_registry


class HelpCommand(Command):
    """Display help information."""

    name = "help"
    description = "Show help information"
    usage = "/help [command]"
    aliases = ["h", "?"]

    async def execute(
        self,
        args: list[str],
        context: Dict[str, Any],
    ) -> CommandResult:
        """Execute help command."""
        registry = get_registry()

        if args:
            # Help for specific command
            cmd_name = args[0].lstrip("/")
            cmd = registry.get(cmd_name)
            if cmd:
                return CommandResult(
                    success=True,
                    message=cmd.get_help(),
                )
            return CommandResult(
                success=False,
                message=f"Unknown command: {cmd_name}",
            )

        # General help
        help_text = registry.get_help()
        help_text += "\n\nType /help <command> for more information."

        return CommandResult(
            success=True,
            message=help_text,
        )


class ExitCommand(Command):
    """Exit the CLI."""

    name = "exit"
    description = "Exit the CLI"
    usage = "/exit"
    aliases = ["quit", "q"]

    async def execute(
        self,
        args: list[str],
        context: Dict[str, Any],
    ) -> CommandResult:
        """Execute exit command."""
        return CommandResult(
            success=True,
            message="Goodbye!",
            should_exit=True,
        )


class ClearCommand(Command):
    """Clear the screen."""

    name = "clear"
    description = "Clear the chat display"
    usage = "/clear"
    aliases = ["cls"]

    async def execute(
        self,
        args: list[str],
        context: Dict[str, Any],
    ) -> CommandResult:
        """Execute clear command."""
        # The TUI will handle the actual clearing
        return CommandResult(
            success=True,
            message="",
            data={"action": "clear"},
        )
