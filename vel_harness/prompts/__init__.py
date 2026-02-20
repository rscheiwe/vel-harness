"""
Vel Harness Prompt System

Modular prompts for robust agent behavior.
Adapted from Piebald claude-code-system-prompts.
"""

from typing import List, Optional

# Core prompts
from .core.base import BASE_SYSTEM_PROMPT, get_base_prompt
from .core.tone import TONE_PROMPT
from .core.tasks import DOING_TASKS_PROMPT

# Tool prompts
from .tools.bash import BASH_TOOL_PROMPT
from .tools.filesystem import (
    READ_TOOL_PROMPT,
    WRITE_TOOL_PROMPT,
    EDIT_TOOL_PROMPT,
    LS_TOOL_PROMPT,
    GLOB_TOOL_PROMPT,
    GREP_TOOL_PROMPT,
)
from .tools.todo import TODO_WRITE_PROMPT

# Agent prompts
from .agents.explore import EXPLORE_AGENT_PROMPT
from .agents.plan import PLAN_AGENT_PROMPT
from .agents.discover import DISCOVER_AGENT_PROMPT
from .agents.implement import IMPLEMENT_AGENT_PROMPT
from .agents.verify import VERIFY_AGENT_PROMPT
from .agents.critic import CRITIC_AGENT_PROMPT

# Utility prompts (P1)
from .utilities import COMPACTION_PROMPT

# Reminders (P2)
from .reminders import get_active_reminders, inject_reminders


def compose_system_prompt(
    include_tools: Optional[List[str]] = None,
    custom_sections: Optional[List[str]] = None,
    working_dir: Optional[str] = None,
    platform: Optional[str] = None,
    agent_name: str = "Vel",
) -> str:
    """
    Compose a complete system prompt from modular pieces.

    Args:
        include_tools: List of tool names to include prompts for.
                      None = include all.
        custom_sections: Additional prompt sections to append.
        working_dir: Working directory for base prompt.
        platform: Platform identifier for base prompt.
        agent_name: Agent name for base prompt.

    Returns:
        Complete system prompt string.
    """
    # Start with core prompts
    sections = [
        get_base_prompt(
            agent_name=agent_name,
            working_dir=working_dir,
            platform=platform,
        ),
        TONE_PROMPT,
        DOING_TASKS_PROMPT,
    ]

    # Tool prompts mapping
    tool_prompts = {
        "execute": BASH_TOOL_PROMPT,
        "read_file": READ_TOOL_PROMPT,
        "write_file": WRITE_TOOL_PROMPT,
        "edit_file": EDIT_TOOL_PROMPT,
        "ls": LS_TOOL_PROMPT,
        "glob": GLOB_TOOL_PROMPT,
        "grep": GREP_TOOL_PROMPT,
        "write_todos": TODO_WRITE_PROMPT,
        "read_todos": TODO_WRITE_PROMPT,  # Same prompt for both
    }

    # Determine which tools to include
    if include_tools is None:
        include_tools = list(tool_prompts.keys())

    # Add tool prompts (deduplicated)
    added_prompts = set()
    for tool_name in include_tools:
        if tool_name in tool_prompts:
            prompt = tool_prompts[tool_name]
            if prompt not in added_prompts:
                sections.append(prompt)
                added_prompts.add(prompt)

    # Custom sections
    if custom_sections:
        sections.extend(custom_sections)

    return "\n\n".join(sections)


def compose_agent_prompt(
    agent_type: str,
    working_dir: Optional[str] = None,
    platform: Optional[str] = None,
) -> str:
    """
    Get the system prompt for a specific agent type.

    Args:
        agent_type: One of "explore", "plan"
        working_dir: Working directory for base prompt.
        platform: Platform identifier for base prompt.

    Returns:
        Agent-specific system prompt.
    """
    agent_prompts = {
        "explore": EXPLORE_AGENT_PROMPT,
        "plan": PLAN_AGENT_PROMPT,
        "discover": DISCOVER_AGENT_PROMPT,
        "implement": IMPLEMENT_AGENT_PROMPT,
        "verify": VERIFY_AGENT_PROMPT,
        "critic": CRITIC_AGENT_PROMPT,
    }

    # Tool subsets for each agent type
    agent_tools = {
        "explore": ["read_file", "ls", "glob", "grep", "execute"],
        "plan": ["read_file", "ls", "glob", "grep", "write_todos", "read_todos"],
        "discover": ["read_file", "ls", "glob", "grep", "execute"],
        "implement": ["read_file", "write_file", "edit_file", "ls", "glob", "grep", "execute"],
        "verify": ["read_file", "ls", "glob", "grep", "execute"],
        "critic": ["read_file", "ls", "glob", "grep", "execute", "write_todos"],
    }

    # Compose base prompt with appropriate tool subset
    base = compose_system_prompt(
        include_tools=agent_tools.get(agent_type, None),
        working_dir=working_dir,
        platform=platform,
    )

    # Add agent-specific prompt
    agent_specific = agent_prompts.get(agent_type, "")

    if agent_specific:
        return f"{base}\n\n{agent_specific}"
    return base


# Convenience exports
__all__ = [
    # Composition functions
    "compose_system_prompt",
    "compose_agent_prompt",
    "get_active_reminders",
    "inject_reminders",

    # Core prompts
    "BASE_SYSTEM_PROMPT",
    "get_base_prompt",
    "TONE_PROMPT",
    "DOING_TASKS_PROMPT",

    # Tool prompts
    "BASH_TOOL_PROMPT",
    "READ_TOOL_PROMPT",
    "WRITE_TOOL_PROMPT",
    "EDIT_TOOL_PROMPT",
    "LS_TOOL_PROMPT",
    "GLOB_TOOL_PROMPT",
    "GREP_TOOL_PROMPT",
    "TODO_WRITE_PROMPT",

    # Agent prompts
    "EXPLORE_AGENT_PROMPT",
    "PLAN_AGENT_PROMPT",
    "DISCOVER_AGENT_PROMPT",
    "IMPLEMENT_AGENT_PROMPT",
    "VERIFY_AGENT_PROMPT",
    "CRITIC_AGENT_PROMPT",

    # Utility prompts
    "COMPACTION_PROMPT",
]
