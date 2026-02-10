"""
Valis CLI Commands

Slash command implementations.
"""

from valis_cli.commands.base import (
    Command,
    CommandRegistry,
    CommandResult,
    get_registry,
    register_command,
)
from valis_cli.commands.config_cmd import ConfigCommand, ModelCommand
from valis_cli.commands.copy import CopyCommand
from valis_cli.commands.help import ClearCommand, ExitCommand, HelpCommand
from valis_cli.commands.reset import ResetCommand
from valis_cli.commands.restart import RestartCommand
from valis_cli.commands.skills import SkillInfoCommand, SkillsCommand
from valis_cli.commands.permissions import AllowCommand, DenyCommand, PermissionsCommand
from valis_cli.commands.tokens import TokensCommand


def register_all_commands() -> None:
    """Register all built-in commands."""
    commands = [
        HelpCommand(),
        ExitCommand(),
        ClearCommand(),
        CopyCommand(),
        ResetCommand(),
        RestartCommand(),
        SkillsCommand(),
        SkillInfoCommand(),
        ConfigCommand(),
        ModelCommand(),
        AllowCommand(),
        DenyCommand(),
        PermissionsCommand(),
        TokensCommand(),
    ]
    for cmd in commands:
        register_command(cmd)


# Auto-register on import
register_all_commands()


__all__ = [
    "Command",
    "CommandRegistry",
    "CommandResult",
    "get_registry",
    "register_command",
    "register_all_commands",
]
