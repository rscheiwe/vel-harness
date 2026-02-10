"""
Agent Registry

Manages typed agent configurations for subagent spawning.
Follows the Claude Code pattern of specialized agents.
"""

from typing import Any, Dict, List, Optional, Union

from .config import AgentConfig, AgentDefinition


# Default agent configurations following Claude Code patterns
# These use the existing prompt composition system
DEFAULT_AGENTS: Dict[str, AgentConfig] = {
    "default": AgentConfig(
        name="default",
        system_prompt="",  # Will be populated by registry
        tools=[
            "execute",          # Bash execution
            "read_file",        # File reading
            "write_file",       # File writing
            "edit_file",        # File editing
            "ls",               # Directory listing
            "glob",             # File pattern matching
            "grep",             # Content search
            "write_todos",      # Todo management
        ],
        max_turns=50,
        timeout=300.0,
        description="General-purpose task execution with all tools",
    ),
    "explore": AgentConfig(
        name="explore",
        system_prompt="",  # Will be populated by registry
        tools=[
            "read_file",        # File reading
            "ls",               # Directory listing
            "glob",             # File pattern matching
            "grep",             # Content search
            "execute",          # Bash (read-only operations)
        ],
        max_turns=30,
        timeout=180.0,
        description="Read-only codebase exploration and information gathering",
    ),
    "plan": AgentConfig(
        name="plan",
        system_prompt="",  # Will be populated by registry
        tools=[
            "read_file",        # File reading
            "ls",               # Directory listing
            "glob",             # File pattern matching
            "grep",             # Content search
            "write_todos",      # Todo/planning
        ],
        max_turns=20,
        timeout=180.0,
        description="Structured planning and task breakdown",
    ),
}


class AgentRegistry:
    """
    Registry of available subagent configurations.

    Provides typed agent lookup for the Task tool, allowing
    specialized agents (explore, plan, default) to be spawned
    with appropriate prompts and tool sets.

    This follows the Claude Code pattern where subagents have:
    - Fresh context (isolated from parent)
    - Agent-specific system prompts
    - Agent-specific tool sets

    Example:
        registry = AgentRegistry()
        config = registry.get("explore")
        # Use config.system_prompt, config.tools, config.max_turns
    """

    def __init__(
        self,
        custom_agents: Optional[Dict[str, Union[AgentConfig, AgentDefinition, Dict[str, Any]]]] = None,
        prompt_loader: Optional[Any] = None,
    ) -> None:
        """
        Initialize agent registry.

        Args:
            custom_agents: Additional agent configurations to register.
                           Accepts AgentConfig, AgentDefinition, or SDK-style dicts.
            prompt_loader: Optional prompt loader for system prompts
        """
        # Start with default agents
        self._agents: Dict[str, AgentConfig] = {}

        # Copy defaults and populate prompts
        for agent_id, config in DEFAULT_AGENTS.items():
            agent_config = AgentConfig(
                name=config.name,
                system_prompt=self._get_prompt_for_agent(config.name, prompt_loader),
                tools=list(config.tools),
                max_turns=config.max_turns,
                timeout=config.timeout,
                description=config.description,
                model=config.model,
            )
            self._agents[agent_id] = agent_config

        # Register custom agents
        if custom_agents:
            for agent_id, config in custom_agents.items():
                self.register(agent_id, config)

    def _get_prompt_for_agent(self, agent_type: str, prompt_loader: Optional[Any] = None) -> str:
        """
        Get system prompt for an agent type.

        Uses the existing prompt composition system if available,
        otherwise falls back to minimal prompts.

        Args:
            agent_type: Agent type name
            prompt_loader: Optional prompt loader

        Returns:
            System prompt string
        """
        # Try to use existing prompt composition
        try:
            from vel_harness.prompts import compose_agent_prompt, compose_system_prompt

            if agent_type == "explore":
                return compose_agent_prompt("explore")
            elif agent_type == "plan":
                return compose_agent_prompt("plan")
            else:  # default
                return compose_system_prompt()
        except ImportError:
            pass

        # Fallback minimal prompts
        fallback_prompts = {
            "default": (
                "You are a focused sub-agent spawned to complete a specific task.\n\n"
                "Your context is ISOLATED - you don't have access to the parent conversation.\n"
                "Everything you need should be in the task description provided.\n\n"
                "Guidelines:\n"
                "- Complete the task thoroughly\n"
                "- Return a clear, concise result\n"
                "- If you lack information, say so explicitly\n"
                "- Don't ask clarifying questions - work with what you have"
            ),
            "explore": (
                "You are an exploration agent. Your job is to gather information.\n\n"
                "You have READ-ONLY tools: read_file, ls, glob, grep, execute (for read operations)\n"
                "You CANNOT modify files.\n\n"
                "Guidelines:\n"
                "- Systematically explore the codebase\n"
                "- Build understanding of architecture and patterns\n"
                "- Report findings clearly and structured\n"
                "- Identify relevant files for the parent task"
            ),
            "plan": (
                "You are a planning agent. Your job is to create structured plans.\n\n"
                "Guidelines:\n"
                "- Break complex tasks into steps\n"
                "- Identify dependencies between steps\n"
                "- Consider edge cases and risks\n"
                "- Output a clear, actionable plan\n"
                "- Use write_todos to structure the plan"
            ),
        }

        return fallback_prompts.get(agent_type, fallback_prompts["default"])

    def get(self, agent_id: str) -> AgentConfig:
        """
        Get agent configuration by ID.

        Falls back to 'default' if agent_id not found.

        Args:
            agent_id: Agent identifier

        Returns:
            AgentConfig for the requested agent
        """
        if agent_id in self._agents:
            return self._agents[agent_id]

        # Fallback to default
        return self._agents.get("default", self._create_fallback_config())

    def _create_fallback_config(self) -> AgentConfig:
        """Create a minimal fallback config if somehow default is missing."""
        return AgentConfig(
            name="fallback",
            system_prompt="You are a helpful assistant. Complete the task provided.",
            tools=[],
            max_turns=10,
            description="Fallback agent",
        )

    def register(
        self,
        agent_id: str,
        config: Union[AgentConfig, AgentDefinition, Dict[str, Any]],
    ) -> None:
        """
        Register a new agent configuration.

        Accepts AgentConfig (native), AgentDefinition (SDK-compatible),
        or a dict (auto-converted to AgentDefinition then AgentConfig).

        Args:
            agent_id: Unique identifier for this agent
            config: Agent configuration in any supported format
        """
        if isinstance(config, AgentDefinition):
            config = config.to_agent_config(agent_id)
        elif isinstance(config, dict):
            config = AgentDefinition.from_dict(config).to_agent_config(agent_id)
        self._agents[agent_id] = config

    def unregister(self, agent_id: str) -> bool:
        """
        Remove an agent configuration.

        Args:
            agent_id: Agent to remove

        Returns:
            True if agent was found and removed
        """
        if agent_id in self._agents and agent_id not in DEFAULT_AGENTS:
            del self._agents[agent_id]
            return True
        return False

    def list_agents(self) -> List[str]:
        """List available agent IDs."""
        return list(self._agents.keys())

    def get_all(self) -> Dict[str, AgentConfig]:
        """Get all registered agent configurations."""
        return dict(self._agents)

    def get_descriptions(self) -> str:
        """
        Get formatted descriptions for all agents.

        Returns:
            Formatted string for tool description
        """
        lines = []
        for agent_id, config in self._agents.items():
            lines.append(f"- {agent_id}: {config.description}")
        return "\n".join(lines)

    def has_agent(self, agent_id: str) -> bool:
        """Check if an agent is registered."""
        return agent_id in self._agents

    def __contains__(self, agent_id: str) -> bool:
        """Support 'in' operator."""
        return self.has_agent(agent_id)

    def __len__(self) -> int:
        """Return number of registered agents."""
        return len(self._agents)

    def __repr__(self) -> str:
        return f"AgentRegistry(agents={list(self._agents.keys())})"
