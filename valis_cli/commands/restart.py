"""
Restart Command

Restarts the Valis CLI process to pick up code changes.
"""

import atexit
import os
import sys
from typing import Any, Dict, List

from valis_cli.commands.base import Command, CommandResult

# Global flag to track if restart was requested
_restart_requested = False


def _do_restart() -> None:
    """Perform the actual restart via exec."""
    global _restart_requested
    if _restart_requested:
        # Re-exec the current process
        os.execv(sys.executable, [sys.executable] + sys.argv)


# Register the restart handler
atexit.register(_do_restart)


class RestartCommand(Command):
    """Restart the CLI process."""

    name = "restart"
    description = "Restart Valis CLI (useful for picking up code changes)"
    aliases = ["r"]

    async def execute(
        self,
        args: List[str],
        context: Dict[str, Any],
    ) -> CommandResult:
        """Execute restart."""
        global _restart_requested
        app = context.get("app")

        # Set flag so atexit handler will restart
        _restart_requested = True

        if app:
            app.exit()

        # No message - we're exiting immediately
        return CommandResult(success=True)
