"""
Agent Configuration

Dataclass for typed agent configurations used by AgentRegistry.

Includes both:
- AgentConfig: Internal agent configuration (vel-harness native)
- AgentDefinition: Agent SDK-compatible definition with model shorthand
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


@dataclass
class AgentConfig:
    """
    Configuration for a subagent type.

    Used by AgentRegistry to define agent behaviors including
    system prompt, available tools, and execution limits.

    Attributes:
        name: Unique identifier for this agent type
        system_prompt: System prompt for this agent (or callable returning one)
        tools: List of tool names this agent can use
        max_turns: Maximum tool-use iterations
        timeout: Execution timeout in seconds
        description: Human-readable description for documentation
        model: Optional model override (uses default if None)
    """

    name: str
    system_prompt: str
    tools: List[str] = field(default_factory=list)
    max_turns: int = 50
    timeout: float = 300.0
    description: str = ""
    model: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "system_prompt": self.system_prompt[:200] + "..." if len(self.system_prompt) > 200 else self.system_prompt,
            "tools": self.tools,
            "max_turns": self.max_turns,
            "timeout": self.timeout,
            "description": self.description,
            "model": self.model,
        }

    def __repr__(self) -> str:
        return (
            f"AgentConfig(name={self.name!r}, tools={self.tools}, "
            f"max_turns={self.max_turns}, description={self.description!r})"
        )


# Model shorthand map for Agent SDK compatibility
MODEL_SHORTHAND_MAP: Dict[str, Dict[str, str]] = {
    "sonnet": {"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
    "opus": {"provider": "anthropic", "model": "claude-opus-4-6"},
    "haiku": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
}


@dataclass
class AgentDefinition:
    """Agent SDK-compatible agent definition.

    This provides the same API shape as the Claude Agent SDK's agent
    definitions, with model shorthand support and automatic conversion
    to the internal AgentConfig format.

    Args:
        description: Human-readable description of what this agent does
        prompt: System prompt for the agent (maps to AgentConfig.system_prompt)
        tools: List of tool names this agent can use
        model: Model shorthand ("sonnet", "opus", "haiku", "inherit") or
               full model ID string, or None to inherit parent model
        max_turns: Maximum tool-use iterations
        timeout: Execution timeout in seconds

    Example:
        # Agent SDK style
        definition = AgentDefinition(
            description="Research agent",
            prompt="You are a research assistant...",
            tools=["read_file", "grep", "glob"],
            model="haiku",
        )

        # Convert to internal config
        config = definition.to_agent_config("researcher")

        # Or register directly with registry
        registry.register("researcher", definition)
    """

    description: str = ""
    prompt: str = ""
    tools: List[str] = field(default_factory=list)
    model: Optional[str] = None
    max_turns: int = 50
    timeout: float = 300.0

    def to_agent_config(self, name: str) -> AgentConfig:
        """Convert to internal AgentConfig.

        Args:
            name: Agent name/identifier

        Returns:
            AgentConfig with resolved model configuration
        """
        return AgentConfig(
            name=name,
            description=self.description,
            system_prompt=self.prompt,
            tools=list(self.tools),
            model=self._resolve_model(self.model),
            max_turns=self.max_turns,
            timeout=self.timeout,
        )

    @staticmethod
    def _resolve_model(model: Optional[str]) -> Optional[Dict[str, Any]]:
        """Resolve shorthand model names to full config.

        Args:
            model: One of:
                - None or "inherit": Use parent agent's model
                - "sonnet", "opus", "haiku": Shorthand for Claude models
                - Full model ID string: Treated as Anthropic model

        Returns:
            Model config dict or None (inherit)
        """
        if model is None or model == "inherit":
            return None
        if model in MODEL_SHORTHAND_MAP:
            return dict(MODEL_SHORTHAND_MAP[model])
        # Full model ID — assume Anthropic provider
        return {"provider": "anthropic", "model": model}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentDefinition":
        """Create from dictionary.

        Args:
            data: Dict with AgentDefinition fields

        Returns:
            AgentDefinition instance
        """
        return cls(
            description=data.get("description", ""),
            prompt=data.get("prompt", ""),
            tools=data.get("tools", []),
            model=data.get("model"),
            max_turns=data.get("max_turns", 50),
            timeout=data.get("timeout", 300.0),
        )

    @classmethod
    def from_value(
        cls, value: Union["AgentDefinition", AgentConfig, Dict[str, Any]]
    ) -> "AgentDefinition":
        """Create from various input formats.

        Args:
            value: AgentDefinition, AgentConfig, or dict

        Returns:
            AgentDefinition instance
        """
        if isinstance(value, cls):
            return value
        if isinstance(value, AgentConfig):
            return cls(
                description=value.description,
                prompt=value.system_prompt,
                tools=list(value.tools),
                model=None,  # AgentConfig.model is already a dict, can't reverse
                max_turns=value.max_turns,
                timeout=value.timeout,
            )
        if isinstance(value, dict):
            return cls.from_dict(value)
        return cls()

    def __repr__(self) -> str:
        return (
            f"AgentDefinition(description={self.description!r}, "
            f"tools={self.tools}, model={self.model!r})"
        )
