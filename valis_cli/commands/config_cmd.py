"""
Config Command

View and modify configuration.
"""

from typing import Any, Dict

from valis_cli.commands.base import Command, CommandResult


class ConfigCommand(Command):
    """View and modify configuration."""

    name = "config"
    description = "View or modify configuration"
    usage = "/config [key] [value]"

    async def execute(
        self,
        args: list[str],
        context: Dict[str, Any],
    ) -> CommandResult:
        """
        Execute config command.

        /config - Show all config
        /config key - Show specific key
        /config key value - Set key to value
        """
        config = context.get("config")
        if config is None:
            return CommandResult(
                success=False,
                message="No configuration available",
            )

        if not args:
            # Show all config
            config_dict = config.to_dict()
            lines = ["Configuration:", ""]

            for key, value in config_dict.items():
                if isinstance(value, dict):
                    lines.append(f"  {key}:")
                    for k, v in value.items():
                        lines.append(f"    {k}: {v}")
                else:
                    lines.append(f"  {key}: {value}")

            return CommandResult(
                success=True,
                message="\n".join(lines),
                data=config_dict,
            )

        key = args[0]

        if len(args) == 1:
            # Show specific key
            config_dict = config.to_dict()
            if key in config_dict:
                value = config_dict[key]
                if isinstance(value, dict):
                    lines = [f"{key}:"]
                    for k, v in value.items():
                        lines.append(f"  {k}: {v}")
                    return CommandResult(
                        success=True,
                        message="\n".join(lines),
                        data={key: value},
                    )
                return CommandResult(
                    success=True,
                    message=f"{key}: {value}",
                    data={key: value},
                )
            return CommandResult(
                success=False,
                message=f"Unknown config key: {key}",
            )

        # Set value
        value = " ".join(args[1:])

        # Handle known keys
        if key == "model":
            config.model.model = value
        elif key == "provider":
            config.model.provider = value
        elif key == "sandbox":
            config.sandbox_enabled = value.lower() in ("true", "1", "yes")
        elif key == "show_thinking":
            config.show_thinking = value.lower() in ("true", "1", "yes")
        elif key == "show_tool_calls":
            config.show_tool_calls = value.lower() in ("true", "1", "yes")
        elif key == "compact":
            config.compact_mode = value.lower() in ("true", "1", "yes")
        else:
            return CommandResult(
                success=False,
                message=f"Cannot set config key: {key}",
            )

        # Save config
        config.save()

        return CommandResult(
            success=True,
            message=f"Set {key} = {value}",
        )


class ModelCommand(Command):
    """Switch model."""

    name = "model"
    description = "Switch the active model"
    usage = "/model [provider/model]"

    async def execute(
        self,
        args: list[str],
        context: Dict[str, Any],
    ) -> CommandResult:
        """Execute model command."""
        config = context.get("config")
        if config is None:
            return CommandResult(
                success=False,
                message="No configuration available",
            )

        if not args:
            return CommandResult(
                success=True,
                message=f"Current model: {config.model.provider}/{config.model.model}",
            )

        model_spec = args[0]

        if "/" in model_spec:
            provider, model = model_spec.split("/", 1)
            config.model.provider = provider
            config.model.model = model
        else:
            # Just model name, keep provider
            config.model.model = model_spec

        config.save()

        return CommandResult(
            success=True,
            message=f"Switched to: {config.model.provider}/{config.model.model}",
        )
