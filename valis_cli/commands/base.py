"""
Command Base Classes

Base classes for slash commands.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CommandResult:
    """Result of command execution."""

    success: bool
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    should_exit: bool = False


class Command(ABC):
    """Base class for slash commands."""

    name: str = ""
    description: str = ""
    usage: str = ""
    aliases: List[str] = []

    @abstractmethod
    async def execute(
        self,
        args: list[str],
        context: Dict[str, Any],
    ) -> CommandResult:
        """
        Execute the command.

        Args:
            args: Command arguments
            context: Execution context

        Returns:
            CommandResult with status and output
        """
        pass

    def get_help(self) -> str:
        """Get help text for this command."""
        lines = [
            f"/{self.name} - {self.description}",
            "",
            f"Usage: {self.usage}",
        ]
        if self.aliases:
            lines.append(f"Aliases: {', '.join(self.aliases)}")
        return "\n".join(lines)


class CommandRegistry:
    """Registry for slash commands."""

    def __init__(self):
        self._commands: Dict[str, Command] = {}
        self._aliases: Dict[str, str] = {}

    def register(self, command: Command) -> None:
        """Register a command."""
        self._commands[command.name] = command
        for alias in getattr(command, "aliases", []):
            self._aliases[alias] = command.name

    def get(self, name: str) -> Optional[Command]:
        """Get a command by name or alias."""
        if name in self._commands:
            return self._commands[name]
        if name in self._aliases:
            return self._commands[self._aliases[name]]
        return None

    def list_commands(self) -> List[Command]:
        """List all registered commands."""
        return list(self._commands.values())

    def get_help(self) -> str:
        """Get help text for all commands."""
        lines = ["Available Commands:", ""]
        for cmd in sorted(self._commands.values(), key=lambda c: c.name):
            lines.append(f"  /{cmd.name:12} - {cmd.description}")
        return "\n".join(lines)


# Global registry
_registry = CommandRegistry()


def get_registry() -> CommandRegistry:
    """Get the global command registry."""
    return _registry


def register_command(command: Command) -> None:
    """Register a command in the global registry."""
    _registry.register(command)
