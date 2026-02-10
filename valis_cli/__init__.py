"""
Valis CLI

A terminal-based interface for the Valis deep agent framework.
Built on Textual for a rich TUI experience.
"""

__version__ = "0.1.0"

from valis_cli.agent import AgentRunner, EventType, create_cli_agent, run_single_turn
from valis_cli.config import Config, get_config, init_project

__all__ = [
    "__version__",
    "AgentRunner",
    "Config",
    "EventType",
    "create_cli_agent",
    "get_config",
    "init_project",
    "run_single_turn",
]
