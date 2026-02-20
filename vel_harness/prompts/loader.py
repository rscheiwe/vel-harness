"""
Prompt Loader

Config-driven prompt loading with support for both custom and Piebald prompts.

The loader follows the user's decision:
- tool_descriptions: "piebald" (battle-tested Claude Code descriptions)
- subagent_prompts: "piebald" (designed for specific agent types)
- main_system: "custom" (chat-app appropriate, not CLI-focused)
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Optional

# Import custom prompts
from vel_harness.prompts import (
    compose_system_prompt,
    compose_agent_prompt,
    EXPLORE_AGENT_PROMPT,
    PLAN_AGENT_PROMPT,
)


class PromptSource(Enum):
    """Source for prompt content."""
    PIEBALD = "piebald"
    CUSTOM = "custom"


@dataclass
class PromptConfig:
    """
    Configuration for prompt sourcing.

    Attributes:
        tool_descriptions: Source for tool descriptions ("piebald" or "custom")
        subagent_prompts: Source for subagent prompts ("piebald" or "custom")
        main_system: Source for main system prompt ("piebald" or "custom")
    """
    tool_descriptions: PromptSource = PromptSource.PIEBALD
    subagent_prompts: PromptSource = PromptSource.PIEBALD
    main_system: PromptSource = PromptSource.CUSTOM

    # Cache for loaded prompts
    _cache: Dict[str, str] = field(default_factory=dict, repr=False)


class PromptLoader:
    """
    Config-driven prompt loader.

    Supports loading prompts from either:
    - Piebald-AI (Claude Code system prompts)
    - Custom prompts (vel_harness/prompts/)

    Example:
        loader = PromptLoader()
        explore_prompt = loader.get_subagent_prompt("explore")
        bash_description = loader.get_tool_description("bash")
    """

    # Mapping of tool names to Piebald file names
    PIEBALD_TOOL_MAP = {
        "bash": "tool-description-bash",
        "execute": "tool-description-bash",
        "read_file": "tool-description-readfile",
        "write_file": "tool-description-write",
        "edit_file": "tool-description-edit",
        "glob": "tool-description-glob",
        "grep": "tool-description-grep",
        "write_todos": "tool-description-todowrite",
        "todo": "tool-description-todowrite",
        "task": "tool-description-task",
        "spawn_subagent": "tool-description-task",
        "skill": "tool-description-skill",
        "activate_skill": "tool-description-skill",
    }

    # Mapping of agent types to Piebald file names
    PIEBALD_AGENT_MAP = {
        "explore": "agent-prompt-explore",
        "plan": "agent-prompt-plan-mode-enhanced",
        "discover": "agent-prompt-explore",
        "implement": "agent-prompt-task-tool",
        "verify": "agent-prompt-task-tool",
        "critic": "agent-prompt-task-tool",
        "task": "agent-prompt-task-tool",
        "default": "agent-prompt-task-tool",
    }

    def __init__(self, config: Optional[PromptConfig] = None) -> None:
        """
        Initialize prompt loader.

        Args:
            config: Prompt configuration (uses defaults if None)
        """
        self._config = config or PromptConfig()
        self._cache: Dict[str, str] = {}

    @property
    def config(self) -> PromptConfig:
        """Get prompt configuration."""
        return self._config

    def _load_piebald_prompt(self, name: str) -> str:
        """Load a prompt from Piebald directory."""
        try:
            from vel_harness.prompts.piebald import load_prompt
            return load_prompt(name)
        except FileNotFoundError as e:
            # Provide helpful error message
            raise FileNotFoundError(
                f"Piebald prompt '{name}' not found. "
                "Run 'python scripts/fetch_piebald_prompts.py' to download prompts."
            ) from e

    def get_tool_description(self, tool_name: str) -> str:
        """
        Get tool description.

        Args:
            tool_name: Tool name (e.g., "bash", "read_file")

        Returns:
            Tool description string
        """
        cache_key = f"tool:{tool_name}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        if self._config.tool_descriptions == PromptSource.PIEBALD:
            piebald_name = self.PIEBALD_TOOL_MAP.get(tool_name)
            if piebald_name:
                try:
                    description = self._load_piebald_prompt(piebald_name)
                    self._cache[cache_key] = description
                    return description
                except FileNotFoundError:
                    pass  # Fall through to custom

        # Custom/fallback - use short descriptions
        # These are already in the tool implementations
        description = self._get_custom_tool_description(tool_name)
        self._cache[cache_key] = description
        return description

    def _get_custom_tool_description(self, tool_name: str) -> str:
        """Get custom tool description."""
        # These are brief descriptions used when Piebald not available
        descriptions = {
            "bash": "Execute a shell command and return the output.",
            "execute": "Execute a shell command and return the output.",
            "read_file": "Read file contents with optional offset and limit.",
            "write_file": "Write content to a file, creating directories if needed.",
            "edit_file": "Replace exact string in file (must be unique).",
            "glob": "Find files matching a glob pattern.",
            "grep": "Search file contents using regex pattern.",
            "write_todos": "Update the todo list for task tracking.",
            "task": "Spawn a subagent to handle a task independently.",
            "skill": "Load a skill to get specialized knowledge.",
        }
        return descriptions.get(tool_name, f"Execute {tool_name} operation.")

    def get_subagent_prompt(self, agent_type: str) -> str:
        """
        Get system prompt for a subagent type.

        Args:
            agent_type: Agent type ("explore", "plan", "default")

        Returns:
            System prompt string
        """
        cache_key = f"agent:{agent_type}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        if self._config.subagent_prompts == PromptSource.PIEBALD:
            piebald_name = self.PIEBALD_AGENT_MAP.get(agent_type)
            if piebald_name:
                try:
                    prompt = self._load_piebald_prompt(piebald_name)
                    self._cache[cache_key] = prompt
                    return prompt
                except FileNotFoundError:
                    pass  # Fall through to custom

        # Custom prompts from vel_harness/prompts/
        prompt = compose_agent_prompt(agent_type)
        self._cache[cache_key] = prompt
        return prompt

    def get_system_prompt(
        self,
        working_dir: Optional[str] = None,
        platform: Optional[str] = None,
        agent_name: str = "Vel",
    ) -> str:
        """
        Get main system prompt.

        Args:
            working_dir: Working directory for context
            platform: Platform identifier
            agent_name: Agent name

        Returns:
            System prompt string
        """
        cache_key = f"system:{working_dir}:{platform}:{agent_name}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        if self._config.main_system == PromptSource.PIEBALD:
            try:
                prompt = self._load_piebald_prompt("system-prompt-main-system-prompt")
                # Note: Piebald prompt is CLI-focused, may need adaptation
                self._cache[cache_key] = prompt
                return prompt
            except FileNotFoundError:
                pass  # Fall through to custom

        # Custom prompts - chat-app appropriate
        prompt = compose_system_prompt(
            working_dir=working_dir,
            platform=platform,
            agent_name=agent_name,
        )
        self._cache[cache_key] = prompt
        return prompt

    def clear_cache(self) -> None:
        """Clear the prompt cache."""
        self._cache.clear()

    def has_piebald_prompts(self) -> bool:
        """Check if Piebald prompts are available."""
        try:
            from vel_harness.prompts.piebald import has_prompts
            return has_prompts()
        except ImportError:
            return False


# Default loader instance
_default_loader: Optional[PromptLoader] = None


def get_default_loader() -> PromptLoader:
    """Get the default prompt loader instance."""
    global _default_loader
    if _default_loader is None:
        _default_loader = PromptLoader()
    return _default_loader


def get_tool_description(tool_name: str) -> str:
    """Get tool description using default loader."""
    return get_default_loader().get_tool_description(tool_name)


def get_subagent_prompt(agent_type: str) -> str:
    """Get subagent prompt using default loader."""
    return get_default_loader().get_subagent_prompt(agent_type)


def get_system_prompt(**kwargs) -> str:
    """Get system prompt using default loader."""
    return get_default_loader().get_system_prompt(**kwargs)
