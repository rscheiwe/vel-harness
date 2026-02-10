"""
Copy Command

Copy message content to clipboard.
"""

from typing import Any, Dict

from valis_cli.commands.base import Command, CommandResult


class CopyCommand(Command):
    """Copy the last assistant response to clipboard."""

    name = "copy"
    description = "Copy last assistant response to clipboard"
    usage = "/copy"
    aliases = ["cp"]

    async def execute(
        self,
        args: list[str],
        context: Dict[str, Any],
    ) -> CommandResult:
        """Execute the copy command."""
        app = context.get("app")
        if not app:
            return CommandResult(success=False, message="App context not available")

        from valis_cli.widgets.chat import ChatDisplay

        try:
            chat = app.query_one("#chat-display", ChatDisplay)
            content = chat.get_last_assistant_message()

            if content:
                app.copy_to_clipboard(content)
                # Truncate preview for display
                preview = content[:50] + "..." if len(content) > 50 else content
                preview = preview.replace("\n", " ")
                return CommandResult(
                    success=True,
                    message=f"Copied to clipboard: {preview}",
                )
            else:
                return CommandResult(
                    success=False,
                    message="No assistant message to copy",
                )
        except Exception as e:
            return CommandResult(success=False, message=f"Copy failed: {e}")
