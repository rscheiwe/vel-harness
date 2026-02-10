"""
Vel Harness Agent Registry

Provides typed agent configurations for subagent spawning.
Follows the Claude Code pattern of specialized agents (default, explore, plan).
"""

from .config import AgentConfig, AgentDefinition, MODEL_SHORTHAND_MAP
from .registry import AgentRegistry, DEFAULT_AGENTS

__all__ = [
    "AgentConfig",
    "AgentDefinition",
    "AgentRegistry",
    "DEFAULT_AGENTS",
    "MODEL_SHORTHAND_MAP",
]
