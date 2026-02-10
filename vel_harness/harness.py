"""
VelHarness - Claude Code-style agent harness built on Vel runtime.

This is the primary API for vel-harness, providing Claude Code-like capabilities
for deployment in containerized environments (Kubernetes).

Features:
- Skills system with tool_result injection (preserves prompt caching)
- Subagent spawning with typed agents (default, explore, plan)
- Planning tools (TodoWrite)
- Context management with compaction
- Vercel AI SDK V5 streaming via Vel

Example:
    harness = VelHarness(
        model={"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
        skill_dirs=["./skills"],
    )

    result = await harness.run("Analyze the codebase", session_id="user-123")

    # Or with streaming
    async for event in harness.run_stream("Write a function", session_id="user-123"):
        print(event)
"""

from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Union

from vel_harness.agents import AgentConfig, AgentDefinition, AgentRegistry
from vel_harness.approval import ApprovalManager, PendingApproval
from vel_harness.config import DeepAgentConfig, ModelConfig, SandboxConfig
from vel_harness.checkpoint import FileCheckpointManager
from vel_harness.factory import DeepAgent, create_deep_agent
from vel_harness.fallback import FallbackStreamWrapper
from vel_harness.hooks import HookEngine, HookMatcher
from vel_harness.middleware.skills import SkillInjectionMode
from vel_harness.reasoning import ReasoningConfig
from vel_harness.session import HarnessSession


class VelHarness:
    """
    Claude Code-style agent harness built on Vel runtime.

    This class provides the PRD-specified API for vel-harness, combining:
    - Vel for streaming/protocol translation
    - Claude Code patterns (skills, subagents, planning)
    - Skills as tool_result (for prompt caching economics)
    - Typed subagent spawning (explore, plan, default)

    Key Design Decisions:
    - System prompt is STATIC (preserves Anthropic prompt caching)
    - Skills injected as tool_result (not system prompt)
    - Append-only message history (never edit, for cache efficiency)
    - Pure Python agent loop (no CLI dependency, Kubernetes compatible)
    """

    def __init__(
        self,
        model: Dict[str, Any],
        tools: Optional[List[Any]] = None,
        skill_dirs: Optional[List[Union[str, Path]]] = None,
        custom_agents: Optional[Dict[str, Union[AgentConfig, AgentDefinition, Dict[str, Any]]]] = None,
        system_prompt: Optional[str] = None,
        max_turns: int = 100,
        working_directory: Optional[Union[str, Path]] = None,
        sandbox: Union[bool, Dict[str, Any], SandboxConfig] = True,
        database: bool = False,
        planning: bool = True,
        memory: bool = False,
        caching: bool = False,
        retry: bool = False,
        hooks: Optional[Dict[str, List[HookMatcher]]] = None,
        reasoning: Optional[Union[str, Dict[str, Any], ReasoningConfig]] = None,
        fallback_model: Optional[Union[str, Dict[str, Any]]] = None,
        max_fallback_retries: int = 1,
        tool_approval_callback: Optional[Any] = None,
    ) -> None:
        """
        Initialize the harness.

        Args:
            model: Model configuration dict with keys:
                   - provider: "anthropic" (or "openai", "google")
                   - model: Model name (e.g., "claude-sonnet-4-5-20250929")
                   - api_key: Optional API key (defaults to env var)
            tools: Custom tools to add to the agent. Each item can be:
                   - ToolSpec: A vel ToolSpec instance
                   - Callable: A function (auto-wrapped via ToolSpec.from_function())
                   Custom tools go through the full middleware pipeline
                   (hooks, caching, retry, checkpointing).
            skill_dirs: Directories containing SKILL.md files
            custom_agents: Additional subagent configurations. Accepts:
                   - AgentConfig: Internal format
                   - AgentDefinition: Agent SDK-compatible format
                   - Dict: Auto-converted via AgentDefinition.from_dict()
            system_prompt: Override default system prompt (use sparingly - breaks caching)
            max_turns: Maximum tool-use iterations
            working_directory: Base directory for file operations
            sandbox: Sandbox configuration. Accepts:
                   - bool: Enable/disable sandbox (True by default)
                   - Dict: Full sandbox config (excluded_commands, allowed_commands, etc.)
                   - SandboxConfig: Instance with all settings
            database: Enable database access
            planning: Enable planning/todo tools
            memory: Enable memory middleware
            caching: Enable tool/prompt caching middleware
            retry: Enable tool retry with backoff middleware
            hooks: Control hooks for tool execution. Dict mapping event names
                   to lists of HookMatchers. Supported events:
                   - "pre_tool_use": Can block/modify tool calls
                   - "post_tool_use": Informational after success
                   - "post_tool_use_failure": Informational after failure
            reasoning: Reasoning configuration. Accepts:
                   - String shorthand: "native", "reflection", "prompted", "none"
                   - Dict with config fields
                   - ReasoningConfig instance
            fallback_model: Fallback model for automatic retry on retryable errors
                   (429, 500, 502, 503, 529). Accepts:
                   - String shorthand: "sonnet", "opus", "haiku"
                   - Dict: Full model config ({"provider": ..., "model": ...})
            max_fallback_retries: Max retry attempts with fallback model (default 1)
            tool_approval_callback: Optional callback for tool approval
        """
        self._model = model
        self._custom_tools = tools or []
        self._skill_dirs = [
            str(d) if isinstance(d, Path) else d
            for d in (skill_dirs or [])
        ]
        self._custom_agents = custom_agents or {}
        self._system_prompt = system_prompt
        self._max_turns = max_turns
        self._working_directory = str(working_directory) if working_directory else None

        # Create approval manager for parallel tool approvals
        self._approval_manager = ApprovalManager()

        # Wrap the callback to use the approval manager
        if tool_approval_callback is not None:
            self._tool_approval_callback = self._wrap_approval_callback()
        else:
            self._tool_approval_callback = None

        # Create hook engine if hooks provided
        self._hook_engine: Optional[HookEngine] = None
        if hooks:
            self._hook_engine = HookEngine(hooks=hooks)

        # Resolve reasoning config
        self._reasoning_config: Optional[ReasoningConfig] = None
        if reasoning is not None:
            self._reasoning_config = ReasoningConfig.from_value(reasoning)

        # Resolve fallback model config
        self._fallback_model: Optional[Dict[str, Any]] = None
        self._max_fallback_retries = max_fallback_retries
        if fallback_model is not None:
            if isinstance(fallback_model, str):
                self._fallback_model = AgentDefinition._resolve_model(fallback_model)
            else:
                self._fallback_model = fallback_model

        # Create agent registry with custom agents
        self._agent_registry = AgentRegistry(custom_agents=self._custom_agents)

        # Build configuration
        self._config = self._build_config(
            sandbox=sandbox,
            database=database,
            planning=planning,
            memory=memory,
            caching=caching,
            retry=retry,
        )

        # Create the underlying DeepAgent
        self._deep_agent = self._create_agent()

        # Create fallback wrapper if fallback model is configured
        self._fallback_wrapper: Optional[FallbackStreamWrapper] = None
        if self._fallback_model is not None:
            self._fallback_wrapper = FallbackStreamWrapper(
                deep_agent=self._deep_agent,
                fallback_model=self._fallback_model,
                max_retries=self._max_fallback_retries,
            )

        # Inject agent registry into subagents middleware
        if self._deep_agent.subagents:
            self._deep_agent.subagents._agent_registry = self._agent_registry
            self._deep_agent.subagents.spawner.agent_registry = self._agent_registry

    def _build_config(
        self,
        sandbox: Union[bool, Dict[str, Any], SandboxConfig],
        database: bool,
        planning: bool,
        memory: bool,
        caching: bool = False,
        retry: bool = False,
    ) -> DeepAgentConfig:
        """Build DeepAgentConfig from parameters.

        Key design decision:
        - Filesystem has REAL access (not sandboxed) - needed for skills, file ops
        - Sandbox is ONLY for code execution (execute, execute_python)

        This matches the CLI behavior where the agent can read/write files
        in the OS but code execution is sandboxed for safety.
        """
        # Resolve sandbox config
        if isinstance(sandbox, bool):
            sandbox_dict: Union[bool, Dict[str, Any]] = {
                "enabled": sandbox,
                "working_dir": self._working_directory,
            }
        elif isinstance(sandbox, SandboxConfig):
            sandbox_dict = {
                "enabled": sandbox.enabled,
                "working_dir": sandbox.working_dir or self._working_directory,
                "network": sandbox.network,
                "timeout": sandbox.timeout,
                "allowed_paths": sandbox.allowed_paths,
                "fallback_unsandboxed": sandbox.fallback_unsandboxed,
                "auto_allow_execute_if_sandboxed": sandbox.auto_allow_execute_if_sandboxed,
                "excluded_commands": sandbox.excluded_commands,
                "allowed_commands": sandbox.allowed_commands,
                "network_allowed_hosts": sandbox.network_allowed_hosts,
                "max_output_size": sandbox.max_output_size,
            }
        else:
            # Dict — pass through, inject working_dir if not set
            sandbox_dict = dict(sandbox)
            if "working_dir" not in sandbox_dict:
                sandbox_dict["working_dir"] = self._working_directory

        config_dict = {
            "name": "vel-harness",
            "model": self._model,
            "max_turns": self._max_turns,
            "sandbox": sandbox_dict,
            "database": {"enabled": database},
            "planning": {"enabled": planning},
            "memory": {"enabled": memory},
            "skills": {
                "enabled": bool(self._skill_dirs),
                "skill_dirs": self._skill_dirs,
                "auto_activate": False,  # We use tool_result injection
            },
            "subagents": {
                "enabled": True,
                "default_model": self._model,
                "max_concurrent": 5,
                "max_turns": 50,
            },
            "filesystem": {
                "enabled": True,
                "use_sandbox": False,  # REAL filesystem access, not sandboxed
            },
            "caching": {"enabled": caching},
            "retry": {"enabled": retry},
        }

        if self._system_prompt:
            config_dict["system_prompt"] = self._system_prompt

        # Wire reasoning config (already resolved from string/dict/ReasoningConfig)
        if self._reasoning_config is not None:
            config_dict["reasoning"] = self._reasoning_config

        # Wire fallback model config
        if self._fallback_model is not None:
            config_dict["fallback_model"] = self._fallback_model
            config_dict["max_fallback_retries"] = self._max_fallback_retries

        return DeepAgentConfig.from_dict(config_dict)

    def _create_agent(self) -> DeepAgent:
        """Create the underlying DeepAgent with tool_result skill injection."""
        # Only pass working_dir to factory if the sandbox config doesn't already
        # have one — the factory's working_dir param overrides config.sandbox.working_dir
        factory_working_dir = self._working_directory
        if self._config.sandbox.working_dir:
            factory_working_dir = None  # Let config.sandbox.working_dir take effect

        # Create checkpoint manager for filesystem change tracking
        self._checkpoint_manager = FileCheckpointManager()

        deep_agent = create_deep_agent(
            config=self._config,
            working_dir=factory_working_dir,
            tool_approval_callback=self._tool_approval_callback,
            hook_engine=self._hook_engine,
            checkpoint_manager=self._checkpoint_manager,
            custom_tools=self._custom_tools or None,
            _skip_deprecation=True,  # VelHarness is the new API, don't warn
        )

        # Configure skills middleware for tool_result injection
        if deep_agent.skills:
            deep_agent.skills._injection_mode = SkillInjectionMode.TOOL_RESULT

        return deep_agent

    def _wrap_approval_callback(self) -> Callable:
        """Wrap the approval callback to use the ApprovalManager for parallel support."""
        async def wrapped_callback(
            tool_name: str,
            args: Dict[str, Any],
            tool_call_id: str = "",
        ) -> bool:
            return await self._approval_manager.request_approval(tool_name, args)
        return wrapped_callback

    @property
    def approval_manager(self) -> ApprovalManager:
        """Get the approval manager for parallel tool approvals."""
        return self._approval_manager

    @property
    def hook_engine(self) -> Optional[HookEngine]:
        """Get the hook engine (None if no hooks configured)."""
        return self._hook_engine

    @property
    def reasoning_config(self) -> Optional[ReasoningConfig]:
        """Get the reasoning config (None if no reasoning configured)."""
        return self._reasoning_config

    @property
    def fallback_wrapper(self) -> Optional[FallbackStreamWrapper]:
        """Get the fallback wrapper (None if no fallback configured)."""
        return self._fallback_wrapper

    @property
    def checkpoint_manager(self) -> FileCheckpointManager:
        """Get the checkpoint manager for filesystem change tracking."""
        return self._checkpoint_manager

    @property
    def model(self) -> Dict[str, Any]:
        """Get model configuration."""
        return self._model

    @property
    def agent_registry(self) -> AgentRegistry:
        """Get the agent registry."""
        return self._agent_registry

    @property
    def deep_agent(self) -> DeepAgent:
        """Get the underlying DeepAgent."""
        return self._deep_agent

    @property
    def config(self) -> DeepAgentConfig:
        """Get the configuration."""
        return self._config

    async def run(
        self,
        message: str,
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Run agent (non-streaming).

        Args:
            message: User message
            session_id: Session ID for context continuity
            context: Optional additional context

        Returns:
            Agent's final response text
        """
        session_id = session_id or "default"

        # Use fallback wrapper if configured
        if self._fallback_wrapper is not None:
            response = await self._fallback_wrapper.run(
                input_text=message,
                session_id=session_id,
                context=context,
            )
        else:
            response = await self._deep_agent.run(
                input_text=message,
                session_id=session_id,
                context=context,
            )

        # Extract text from response
        if hasattr(response, "content"):
            return response.content
        if isinstance(response, dict) and "content" in response:
            return response["content"]
        return str(response)

    async def run_stream(
        self,
        message: str,
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Run agent with streaming.

        Yields Vercel AI SDK V5 protocol events.

        Args:
            message: User message
            session_id: Session ID for context continuity
            context: Optional additional context

        Yields:
            Event dicts (text-delta, tool-input-*, etc.)
        """
        session_id = session_id or "default"

        # Use fallback wrapper if configured
        if self._fallback_wrapper is not None:
            async for event in self._fallback_wrapper.run_stream(
                input_text=message,
                session_id=session_id,
                context=context,
            ):
                yield event
        else:
            async for event in self._deep_agent.run_stream(
                input_text=message,
                session_id=session_id,
                context=context,
            ):
                yield event

    def register_agent(
        self,
        agent_id: str,
        config: Union[AgentConfig, AgentDefinition, Dict[str, Any]],
    ) -> None:
        """
        Register a custom agent type.

        Args:
            agent_id: Unique identifier for this agent type
            config: Agent configuration (AgentConfig, AgentDefinition, or dict)
        """
        self._agent_registry.register(agent_id, config)

    def list_agent_types(self) -> List[str]:
        """List available agent types."""
        return self._agent_registry.list_agents()

    def get_state(self) -> Dict[str, Any]:
        """Get harness state for persistence."""
        return self._deep_agent.get_state()

    def load_state(self, state: Dict[str, Any]) -> None:
        """Load harness state from persistence."""
        self._deep_agent.load_state(state)

    def create_session(
        self, session_id: Optional[str] = None
    ) -> HarnessSession:
        """Create an interactive session with mid-conversation controls.

        Sessions provide a persistent context with support for model switching,
        interrupt, and reasoning changes between queries.

        Args:
            session_id: Session ID for context continuity (auto-generated if not provided)

        Returns:
            HarnessSession instance (use as async context manager)

        Example:
            async with harness.create_session("user-123") as session:
                async for event in session.query("Hello"):
                    print(event)
                session.set_model("opus")
                async for event in session.query("Now do something complex"):
                    print(event)
        """
        return HarnessSession(harness=self, session_id=session_id)


# Convenience factory functions


def create_harness(
    model: Optional[Dict[str, Any]] = None,
    skill_dirs: Optional[List[str]] = None,
    **kwargs: Any,
) -> VelHarness:
    """
    Create a VelHarness with sensible defaults.

    Args:
        model: Model configuration (defaults to Claude Sonnet)
        skill_dirs: Skill directories
        **kwargs: Additional VelHarness options

    Returns:
        Configured VelHarness instance
    """
    default_model = {
        "provider": "anthropic",
        "model": "claude-sonnet-4-5-20250929",
    }

    return VelHarness(
        model=model or default_model,
        skill_dirs=skill_dirs,
        **kwargs,
    )


def create_research_harness(
    skill_dirs: Optional[List[str]] = None,
    **kwargs: Any,
) -> VelHarness:
    """Create a research-focused harness."""
    return create_harness(
        skill_dirs=skill_dirs,
        sandbox=True,
        database=False,
        system_prompt="""You are a research assistant capable of deep investigation.

Use subagents to research multiple topics in parallel:
- Use agent="explore" for codebase exploration
- Use agent="plan" for structured planning
- Use agent="default" for general task execution

Synthesize findings into clear, well-organized reports.
""",
        **kwargs,
    )


def create_coding_harness(
    working_directory: Optional[str] = None,
    skill_dirs: Optional[List[str]] = None,
    **kwargs: Any,
) -> VelHarness:
    """Create a coding-focused harness."""
    return create_harness(
        working_directory=working_directory,
        skill_dirs=skill_dirs,
        sandbox=True,
        database=False,
        planning=True,
        system_prompt="""You are a skilled software developer.

When writing code:
1. Plan your approach using the todo list
2. Use agent="explore" to investigate the codebase
3. Write clean, well-documented code
4. Test your code by executing it

Follow best practices for the language you're using.
""",
        **kwargs,
    )
