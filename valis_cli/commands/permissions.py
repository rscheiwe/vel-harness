"""
Permission Commands

Commands for managing tool permissions.
"""

from typing import Any, Dict

from valis_cli.commands.base import Command, CommandResult, register_command


class AllowCommand(Command):
    """Grant permission for a tool."""

    name = "allow"
    description = "Grant permanent permission for a tool"
    usage = "/allow <tool_name>"
    aliases = ["permit"]

    async def execute(
        self,
        args: list[str],
        context: Dict[str, Any],
    ) -> CommandResult:
        if not args:
            return CommandResult(
                success=False,
                message="Usage: /allow <tool_name>\n\nExample: /allow read_file",
            )

        tool_name = args[0]
        agent = context.get("agent")
        config = context.get("config")

        if agent and config:
            # Grant permission and save to settings.local.json
            agent.grant_permission(tool_name, {}, always=True)
            return CommandResult(
                success=True,
                message=f"Permission granted for '{tool_name}'. Saved to .valis/settings.local.json",
            )

        return CommandResult(
            success=False,
            message="Unable to save permission - agent not initialized",
        )


class DenyCommand(Command):
    """Deny permission for a tool."""

    name = "deny"
    description = "Deny a tool from being used"
    usage = "/deny <tool_name>"
    aliases = ["block"]

    async def execute(
        self,
        args: list[str],
        context: Dict[str, Any],
    ) -> CommandResult:
        if not args:
            return CommandResult(
                success=False,
                message="Usage: /deny <tool_name>\n\nExample: /deny execute",
            )

        tool_name = args[0]
        agent = context.get("agent")
        config = context.get("config")

        if agent and config:
            # Deny permission and save to settings.local.json
            agent.deny_permission(tool_name, {}, always=True)
            return CommandResult(
                success=True,
                message=f"Permission denied for '{tool_name}'. Saved to .valis/settings.local.json",
            )

        return CommandResult(
            success=False,
            message="Unable to save permission - agent not initialized",
        )


class PermissionsCommand(Command):
    """Show current permissions."""

    name = "permissions"
    description = "Show current tool permissions"
    usage = "/permissions"
    aliases = ["perms"]

    async def execute(
        self,
        args: list[str],
        context: Dict[str, Any],
    ) -> CommandResult:
        agent = context.get("agent")

        if agent and hasattr(agent, "permissions"):
            perms = agent.permissions
            lines = ["Current Permissions:", ""]

            if perms.allow:
                lines.append("Allowed:")
                for p in perms.allow:
                    lines.append(f"  + {p}")

            if perms.deny:
                lines.append("\nDenied:")
                for p in perms.deny:
                    lines.append(f"  - {p}")

            if not perms.allow and not perms.deny:
                lines.append("No custom permissions set.")
                lines.append("Tools will prompt for approval on first use.")

            return CommandResult(
                success=True,
                message="\n".join(lines),
            )

        return CommandResult(
            success=False,
            message="Unable to read permissions - agent not initialized",
        )


# Register commands
register_command(AllowCommand())
register_command(DenyCommand())
register_command(PermissionsCommand())
