"""
Reset Command

Resets the current session or clears state.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from valis_cli.commands.base import Command, CommandResult


class ResetCommand(Command):
    """Reset session state."""

    name = "reset"
    description = "Reset the current session"
    usage = "/reset [--hard]"

    async def execute(
        self,
        args: list[str],
        context: Dict[str, Any],
    ) -> CommandResult:
        """
        Execute reset command.

        Args:
            args: Command arguments
            context: Execution context with agent, config, etc.

        Returns:
            CommandResult with status
        """
        hard_reset = "--hard" in args

        agent = context.get("agent")
        if agent is None:
            return CommandResult(
                success=False,
                message="No agent available",
            )

        # Reset session
        agent.reset_session()

        if hard_reset:
            # Also clear any cached state
            config = context.get("config")
            if config and config.session_file.exists():
                config.session_file.unlink()

            return CommandResult(
                success=True,
                message="Session and cached state cleared",
            )

        return CommandResult(
            success=True,
            message="Session reset. Starting fresh conversation.",
        )
