"""
Deep Agent Factory

Creates fully-configured deep agents with all middleware components.

DEPRECATION NOTICE:
    The DeepAgent class and create_deep_agent function are deprecated.
    Use VelHarness instead for the recommended API.

    Old:
        agent = create_deep_agent(model=..., skill_dirs=...)
        result = await agent.run("Hello")

    New:
        from vel_harness import VelHarness
        harness = VelHarness(model=..., skill_dirs=...)
        result = await harness.run("Hello")
"""

import tempfile
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from vel import Agent, ToolSpec

from vel_harness.config import (
    DeepAgentConfig,
    ModelConfig,
    DatabaseConfig as DbConfig,
)
from vel_harness.middleware.base import BaseMiddleware
from vel_harness.middleware.planning import PlanningMiddleware
from vel_harness.middleware.filesystem import FilesystemMiddleware
from vel_harness.middleware.sandbox import SandboxMiddleware, SandboxFilesystemMiddleware
from vel_harness.middleware.database import DatabaseMiddleware
from vel_harness.middleware.skills import SkillsMiddleware
from vel_harness.middleware.subagents import SubagentsMiddleware
from vel_harness.middleware.context import (
    ContextManagementMiddleware,
    ContextConfig as CtxConfig,
)
from vel_harness.middleware.memory import MemoryMiddleware
from vel_harness.backends.database import DatabaseConfig, MockDatabaseBackend
from vel_harness.backends.composite import CompositeBackend, PersistentStoreBackend
from vel_harness.backends.state import StateFilesystemBackend
from vel_harness.backends.real import RealFilesystemBackend
from vel_harness.prompts import compose_system_prompt, compose_agent_prompt


class DeepAgent:
    """
    A fully-configured deep agent with all middleware capabilities.

    DEPRECATED: Use VelHarness instead for the recommended API.
    This class will be removed in v2.0.

    Combines:
    - Planning middleware (todo list)
    - Filesystem middleware (file operations)
    - Sandbox middleware (code execution)
    - Database middleware (SQL queries)
    - Skills middleware (procedural knowledge)
    - Subagents middleware (parallel research)
    """

    _deprecation_warned: bool = False

    def __init__(
        self,
        config: DeepAgentConfig,
        agent: Agent,
        middlewares: Dict[str, BaseMiddleware],
        _skip_deprecation: bool = False,
    ) -> None:
        """
        Initialize deep agent.

        Args:
            config: Agent configuration
            agent: Underlying vel Agent instance
            middlewares: Dictionary of middleware instances
            _skip_deprecation: Internal flag to skip warning (used by VelHarness)
        """
        # Issue deprecation warning once per class
        if not _skip_deprecation and not DeepAgent._deprecation_warned:
            warnings.warn(
                "DeepAgent is deprecated and will be removed in v2.0. "
                "Use VelHarness instead:\n"
                "  from vel_harness import VelHarness\n"
                "  harness = VelHarness(model=..., skill_dirs=...)",
                DeprecationWarning,
                stacklevel=2,
            )
            DeepAgent._deprecation_warned = True

        self._config = config
        self._agent = agent
        self._middlewares = middlewares
        self._checkpoint_manager = None

    @property
    def config(self) -> DeepAgentConfig:
        """Get agent configuration."""
        return self._config

    @property
    def agent(self) -> Agent:
        """Get underlying vel Agent."""
        return self._agent

    @property
    def middlewares(self) -> Dict[str, BaseMiddleware]:
        """Get all middleware instances."""
        return self._middlewares

    def get_middleware(self, name: str) -> Optional[BaseMiddleware]:
        """Get a specific middleware by name."""
        return self._middlewares.get(name)

    @property
    def planning(self) -> Optional[PlanningMiddleware]:
        """Get planning middleware."""
        return self._middlewares.get("planning")  # type: ignore

    @property
    def filesystem(self) -> Optional[Union[FilesystemMiddleware, SandboxFilesystemMiddleware]]:
        """Get filesystem middleware."""
        return self._middlewares.get("filesystem")  # type: ignore

    @property
    def sandbox(self) -> Optional[SandboxMiddleware]:
        """Get sandbox middleware."""
        return self._middlewares.get("sandbox")  # type: ignore

    @property
    def database(self) -> Optional[DatabaseMiddleware]:
        """Get database middleware."""
        return self._middlewares.get("database")  # type: ignore

    @property
    def skills(self) -> Optional[SkillsMiddleware]:
        """Get skills middleware."""
        return self._middlewares.get("skills")  # type: ignore

    @property
    def subagents(self) -> Optional[SubagentsMiddleware]:
        """Get subagents middleware."""
        return self._middlewares.get("subagents")  # type: ignore

    @property
    def context(self) -> Optional[ContextManagementMiddleware]:
        """Get context management middleware."""
        return self._middlewares.get("context")  # type: ignore

    @property
    def memory(self) -> Optional[MemoryMiddleware]:
        """Get memory middleware."""
        return self._middlewares.get("memory")  # type: ignore

    @property
    def checkpoint_manager(self) -> Optional[Any]:
        """Get checkpoint manager (None if not enabled)."""
        return self._checkpoint_manager

    def get_all_tools(self) -> List[ToolSpec]:
        """Get all tools from all middlewares."""
        tools = []
        for middleware in self._middlewares.values():
            tools.extend(middleware.get_tools())
        return tools

    def get_system_prompt(self) -> str:
        """Get combined system prompt from all middlewares."""
        segments = []

        # Base system prompt
        if self._config.system_prompt:
            segments.append(self._config.system_prompt)

        # Middleware segments
        for middleware in self._middlewares.values():
            segment = middleware.get_system_prompt_segment()
            if segment:
                segments.append(segment)

        return "\n\n".join(segments)

    def get_state(self) -> Dict[str, Any]:
        """Get complete agent state for persistence."""
        state: Dict[str, Any] = {
            "config": self._config.to_dict(),
            "middlewares": {},
        }

        for name, middleware in self._middlewares.items():
            state["middlewares"][name] = middleware.get_state()

        return state

    def load_state(self, state: Dict[str, Any]) -> None:
        """Load agent state from persistence."""
        if "middlewares" in state:
            for name, mw_state in state["middlewares"].items():
                if name in self._middlewares:
                    self._middlewares[name].load_state(mw_state)

    async def run(
        self,
        input_text: Union[str, List[Dict[str, Any]]],
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Run the agent with input.

        Args:
            input_text: User input - either a string or a list of content parts
                        for multimodal input (images + text)
            session_id: Optional session ID for persistence
            context: Optional additional context

        Returns:
            Agent response
        """
        # Process context for skill activation (text content only)
        if self.skills:
            if isinstance(input_text, str):
                self.skills.process_context(input_text)
            elif isinstance(input_text, list):
                text_parts = [p.get('text', '') for p in input_text if p.get('type') == 'text']
                self.skills.process_context(' '.join(text_parts))

        # Run underlying agent
        # Use 'message' key which vel expects (not 'text')
        return await self._agent.run(
            {"message": input_text, **(context or {})},
            session_id=session_id,
        )

    async def run_stream(
        self,
        input_text: Union[str, List[Dict[str, Any]]],
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        """
        Run the agent with streaming output.

        Args:
            input_text: User input - either a string or a list of content parts
                        for multimodal input (images + text)
            session_id: Optional session ID
            context: Optional additional context

        Yields:
            Stream events from the agent
        """
        # Process context for skill activation (text content only)
        if self.skills:
            if isinstance(input_text, str):
                self.skills.process_context(input_text)
            elif isinstance(input_text, list):
                # Extract text from content parts for skill processing
                text_parts = [p.get('text', '') for p in input_text if p.get('type') == 'text']
                self.skills.process_context(' '.join(text_parts))

        # Run underlying agent with streaming
        # Use 'message' key which vel expects (not 'text')
        async for event in self._agent.run_stream(
            {"message": input_text, **(context or {})},
            session_id=session_id,
        ):
            yield event


def create_deep_agent(
    config: Optional[Union[DeepAgentConfig, Dict[str, Any]]] = None,
    model: Optional[Union[ModelConfig, Dict[str, str]]] = None,
    skill_dirs: Optional[List[str]] = None,
    sandbox: Optional[bool] = None,
    database: Optional[bool] = None,
    system_prompt: Optional[str] = None,
    working_dir: Optional[str] = None,
    tool_approval_callback: Optional[Any] = None,
    hook_engine: Optional[Any] = None,
    checkpoint_manager: Optional[Any] = None,
    custom_tools: Optional[List[Any]] = None,
    _skip_deprecation: bool = False,
    **kwargs: Any,
) -> DeepAgent:
    """
    Factory function to create a deep agent.

    DEPRECATED: Use VelHarness instead:
        from vel_harness import VelHarness
        harness = VelHarness(model=..., skill_dirs=...)

    This function will be removed in v2.0.

    Args:
        config: Full configuration object or dict
        model: Model configuration override
        skill_dirs: Directories containing skills
        sandbox: Whether to enable sandboxed execution
        database: Whether to enable database access
        system_prompt: Custom system prompt
        working_dir: Working directory for sandbox
        _skip_deprecation: Internal flag to skip warning (used by VelHarness)
        **kwargs: Additional configuration overrides

    Returns:
        Configured DeepAgent instance

    Example:
        ```python
        # DEPRECATED - use VelHarness instead
        agent = create_deep_agent(
            model={"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
            skill_dirs=["./skills"],
            sandbox=True,
        )

        result = await agent.run("Analyze the sales data")
        ```
    """
    # Build configuration
    if isinstance(config, dict):
        agent_config = DeepAgentConfig.from_dict(config)
    elif config is not None:
        agent_config = config
    else:
        agent_config = DeepAgentConfig()

    # Apply overrides
    if model is not None:
        if isinstance(model, dict):
            agent_config.model = ModelConfig(**model)
        else:
            agent_config.model = model

    if skill_dirs is not None:
        agent_config.skills.skill_dirs = skill_dirs

    if system_prompt is not None:
        agent_config.system_prompt = system_prompt

    if working_dir is not None:
        agent_config.sandbox.working_dir = working_dir

    # Only override if explicitly specified
    if sandbox is not None:
        agent_config.sandbox.enabled = sandbox
    if database is not None:
        agent_config.database.enabled = database

    # Apply any additional kwargs
    for key, value in kwargs.items():
        if hasattr(agent_config, key):
            setattr(agent_config, key, value)

    # Create middlewares
    middlewares: Dict[str, BaseMiddleware] = {}
    all_tools: List[ToolSpec] = []

    # Planning middleware
    if agent_config.planning.enabled:
        planning = PlanningMiddleware()
        middlewares["planning"] = planning
        all_tools.extend(planning.get_tools())

    # Filesystem/Sandbox middleware
    if agent_config.filesystem.enabled:
        if agent_config.sandbox.enabled and agent_config.filesystem.use_sandbox:
            # Use sandbox filesystem (combines filesystem + execution)
            sandbox_fs = SandboxFilesystemMiddleware(
                working_dir=agent_config.sandbox.working_dir,
                network=agent_config.sandbox.network,
                timeout=agent_config.sandbox.timeout,
                fallback_unsandboxed=agent_config.sandbox.fallback_unsandboxed,
            )
            middlewares["filesystem"] = sandbox_fs
            all_tools.extend(sandbox_fs.get_tools())
        else:
            # Use real filesystem (no sandbox)
            real_backend = RealFilesystemBackend(base_path=working_dir)
            filesystem = FilesystemMiddleware(backend=real_backend)
            middlewares["filesystem"] = filesystem
            all_tools.extend(filesystem.get_tools())

            # Add separate sandbox if enabled (for code execution only)
            if agent_config.sandbox.enabled:
                sandbox_mw = SandboxMiddleware(
                    working_dir=agent_config.sandbox.working_dir,
                    network=agent_config.sandbox.network,
                    timeout=agent_config.sandbox.timeout,
                    fallback_unsandboxed=agent_config.sandbox.fallback_unsandboxed,
                )
                middlewares["sandbox"] = sandbox_mw
                all_tools.extend(sandbox_mw.get_tools())

    # Database middleware
    if agent_config.database.enabled:
        db_config = DatabaseConfig(
            host=agent_config.database.host,
            port=agent_config.database.port,
            database=agent_config.database.database,
            user=agent_config.database.user,
            password=agent_config.database.password,
            readonly=agent_config.database.readonly,
        )

        # Use mock backend for now (real backend requires connection)
        # In production, you'd connect to actual database
        mock_backend = MockDatabaseBackend(readonly=agent_config.database.readonly)
        database_mw = DatabaseMiddleware(
            backend=mock_backend,
            readonly=agent_config.database.readonly,
            max_rows=agent_config.database.max_rows,
            timeout=agent_config.database.timeout,
        )
        middlewares["database"] = database_mw
        all_tools.extend(database_mw.get_tools())

    # Skills middleware
    if agent_config.skills.enabled:
        skills = SkillsMiddleware(
            skill_dirs=agent_config.skills.skill_dirs,
            auto_activate=agent_config.skills.auto_activate,
            max_active_skills=agent_config.skills.max_active_skills,
        )
        middlewares["skills"] = skills
        all_tools.extend(skills.get_tools())

    # Subagents middleware
    if agent_config.subagents.enabled:
        subagents = SubagentsMiddleware(
            default_model=agent_config.subagents.default_model or agent_config.model.to_dict(),
            max_concurrent=agent_config.subagents.max_concurrent,
            max_turns=agent_config.subagents.max_turns,
            timeout=agent_config.subagents.timeout,
        )
        middlewares["subagents"] = subagents
        all_tools.extend(subagents.get_tools())

    # Memory middleware with composite backend
    filesystem_backend = None
    if agent_config.memory.enabled:
        # Create composite backend for memory routing
        # Get or create the base filesystem backend
        if "filesystem" in middlewares:
            fs_middleware = middlewares["filesystem"]
            if hasattr(fs_middleware, "_backend"):
                base_backend = fs_middleware._backend
            else:
                base_backend = StateFilesystemBackend()
        else:
            base_backend = StateFilesystemBackend()

        # Create persistent backend for /memories/
        persistent_backend = PersistentStoreBackend(
            base_path=agent_config.memory.persistent_base_path,
            agent_id=agent_config.name,
        )

        # Create composite backend
        filesystem_backend = CompositeBackend(
            default=base_backend,
            routes={"/memories/": persistent_backend},
        )

        # Create memory middleware
        memory_mw = MemoryMiddleware(
            memories_path=agent_config.memory.memories_path,
            agents_md_path=agent_config.memory.agents_md_path,
        )
        memory_mw.set_filesystem(filesystem_backend)
        middlewares["memory"] = memory_mw
        all_tools.extend(memory_mw.get_tools())

    # Context management middleware
    if agent_config.context.enabled:
        ctx_config = CtxConfig(
            truncate_threshold=agent_config.context.truncate_threshold,
            truncate_head_lines=agent_config.context.truncate_head_lines,
            truncate_tail_lines=agent_config.context.truncate_tail_lines,
            history_threshold=agent_config.context.history_threshold,
            storage_path=agent_config.context.storage_path,
            eviction_threshold=agent_config.context.eviction_threshold,
            summarization_threshold=agent_config.context.summarization_threshold,
            preserve_recent_messages=agent_config.context.preserve_recent_messages,
        )

        # Use the filesystem backend if available
        if filesystem_backend is None and "filesystem" in middlewares:
            fs_middleware = middlewares["filesystem"]
            if hasattr(fs_middleware, "_backend"):
                filesystem_backend = fs_middleware._backend

        context_mw = ContextManagementMiddleware(
            config=ctx_config,
            filesystem_backend=filesystem_backend,
            summarization_model=agent_config.subagents.default_model,
        )
        middlewares["context"] = context_mw
        # Context middleware doesn't add tools, but adds system prompt segment

    # Build system prompt
    prompt_segments = []

    # Use custom system prompt if provided, otherwise compose from modules
    if agent_config.system_prompt:
        prompt_segments.append(agent_config.system_prompt)
    else:
        # Compose system prompt from modular pieces
        # Determine which tools are enabled based on middlewares
        enabled_tools = []
        if "filesystem" in middlewares:
            enabled_tools.extend(["read_file", "write_file", "edit_file", "ls", "glob", "grep"])
        if "sandbox" in middlewares or (
            "filesystem" in middlewares and hasattr(middlewares["filesystem"], "_sandbox")
        ):
            enabled_tools.append("execute")
        if "planning" in middlewares:
            enabled_tools.extend(["write_todos", "read_todos"])

        base_prompt = compose_system_prompt(
            include_tools=enabled_tools if enabled_tools else None,
            working_dir=agent_config.sandbox.working_dir or working_dir,
            agent_name=agent_config.name,
        )
        prompt_segments.append(base_prompt)

    # Add middleware-specific prompt segments
    for middleware in middlewares.values():
        segment = middleware.get_system_prompt_segment()
        if segment:
            prompt_segments.append(segment)

    combined_prompt = "\n\n".join(prompt_segments) if prompt_segments else None

    # Reasoning: inject prompted reasoning prompt if mode is "prompted"
    reasoning_config = agent_config.reasoning
    if reasoning_config and reasoning_config.mode == "prompted":
        from vel_harness.reasoning import PROMPTED_REASONING_PROMPT

        prompt_to_inject = reasoning_config.prompt_template or PROMPTED_REASONING_PROMPT
        if combined_prompt:
            combined_prompt = prompt_to_inject + "\n\n" + combined_prompt
        else:
            combined_prompt = prompt_to_inject

    # Add custom tools (injected from VelHarness or direct callers)
    # These are added after middleware tools so they go through the same
    # wrapping pipeline (checkpointing, caching, retry, hooks)
    if custom_tools:
        for tool in custom_tools:
            if isinstance(tool, ToolSpec):
                all_tools.append(tool)
            elif callable(tool):
                # Wrap callable as ToolSpec
                all_tools.append(ToolSpec.from_function(tool))
            else:
                raise TypeError(
                    f"Custom tool must be a ToolSpec or callable, got {type(tool).__name__}"
                )

    # Wrap filesystem tools with checkpointing (innermost wrapper — records actual changes)
    if checkpoint_manager is not None and "filesystem" in middlewares:
        import asyncio as _asyncio

        from vel_harness.checkpoint import FileCheckpointManager

        fs_middleware = middlewares["filesystem"]
        fs_backend = getattr(fs_middleware, "_backend", None) or getattr(fs_middleware, "backend", None)

        _CHECKPOINT_TOOLS = {"write_file", "edit_file"}

        def _wrap_tool_with_checkpoint(
            tool: ToolSpec,
            cp_mgr: FileCheckpointManager,
            backend: Any,
        ) -> ToolSpec:
            """Wrap a filesystem tool to record changes for checkpoint/rewind."""
            original_handler = tool._handler

            async def checkpointed_handler(**kwargs: Any) -> Any:
                path = kwargs.get("path", "")

                # Capture current content before the change
                previous_content = None
                try:
                    result = backend.read_file(path, offset=0, limit=100000)
                    if isinstance(result, dict) and "content" in result:
                        previous_content = result["content"]
                except Exception:
                    pass  # File doesn't exist yet — previous_content stays None

                # Execute original tool
                if _asyncio.iscoroutinefunction(original_handler):
                    output = await original_handler(**kwargs)
                else:
                    output = original_handler(**kwargs)

                # Record the change (only if tool succeeded)
                if isinstance(output, dict) and "error" not in output:
                    action = "write" if tool.name == "write_file" else "edit"
                    new_content = kwargs.get("content", None)
                    cp_mgr.record_change(
                        path=path,
                        action=action,
                        previous_content=previous_content,
                        new_content=new_content,
                    )

                return output

            return ToolSpec.from_function(
                checkpointed_handler,
                name=tool.name,
                description=tool.description,
                input_schema=tool.input_schema,
                output_schema=tool.output_schema,
                category=getattr(tool, "category", None),
                tags=getattr(tool, "tags", None),
            )

        if fs_backend is not None:
            all_tools = [
                _wrap_tool_with_checkpoint(t, checkpoint_manager, fs_backend)
                if t.name in _CHECKPOINT_TOOLS
                else t
                for t in all_tools
            ]

    # Wrap tools with caching middleware (wrap pattern, not add)
    if agent_config.caching.enabled:
        from vel_harness.middleware.caching import (
            AnthropicPromptCachingMiddleware,
            CacheConfig as InternalCacheConfig,
            ToolCachingMiddleware,
        )

        prompt_cache_mw = AnthropicPromptCachingMiddleware(
            ttl_seconds=agent_config.caching.prompt_cache_ttl,
            enabled=agent_config.caching.prompt_cache_enabled,
        )
        internal_cache_config = InternalCacheConfig(
            prompt_cache_enabled=agent_config.caching.prompt_cache_enabled,
            prompt_cache_ttl=agent_config.caching.prompt_cache_ttl,
            tool_cache_enabled=agent_config.caching.tool_cache_enabled,
            tool_cache_ttl=agent_config.caching.tool_cache_ttl,
            cacheable_tools=set(agent_config.caching.cacheable_tools),
            max_cache_size=agent_config.caching.max_cache_size,
        )
        tool_cache_mw = ToolCachingMiddleware(config=internal_cache_config)

        # wrap_tool internally checks is_cacheable, so wrap all tools
        all_tools = [tool_cache_mw.wrap_tool(t) for t in all_tools]

    # Wrap tools with retry middleware (wrap pattern, not add)
    if agent_config.retry.enabled:
        from vel_harness.middleware.retry import create_retry_middleware

        retry_result = create_retry_middleware(
            max_retries=agent_config.retry.max_retries,
            backoff_base=agent_config.retry.backoff_base,
            use_circuit_breaker=agent_config.retry.use_circuit_breaker,
            circuit_failure_threshold=agent_config.retry.circuit_failure_threshold,
            circuit_reset_timeout=agent_config.retry.circuit_reset_timeout,
        )
        if isinstance(retry_result, tuple):
            retry_mw, circuit_mw = retry_result
            all_tools = [circuit_mw.wrap_tool(retry_mw.wrap_tool(t)) for t in all_tools]
        else:
            retry_mw = retry_result
            all_tools = [retry_mw.wrap_tool(t) for t in all_tools]

    # Auto-register sandbox enforcement hook if sandbox settings require it
    sandbox_needs_enforcement = (
        agent_config.sandbox.enabled
        and (
            agent_config.sandbox.excluded_commands
            or agent_config.sandbox.allowed_commands
            or agent_config.sandbox.network_allowed_hosts
        )
    )
    if sandbox_needs_enforcement:
        from vel_harness.hooks import (
            HookEngine as HE,
            create_sandbox_enforcement_hook,
        )

        sandbox_hook = create_sandbox_enforcement_hook(
            excluded_commands=agent_config.sandbox.excluded_commands,
            allowed_commands=agent_config.sandbox.allowed_commands,
            network_allowed_hosts=agent_config.sandbox.network_allowed_hosts,
            network_enabled=agent_config.sandbox.network,
        )
        if hook_engine is None:
            hook_engine = HE(hooks={"pre_tool_use": [sandbox_hook]})
        else:
            hook_engine.add_hooks("pre_tool_use", [sandbox_hook])

    # Wrap tools with hooks (outermost wrapper — runs before caching/retry)
    if hook_engine is not None:
        from vel_harness.hooks import (
            HookEngine,
            HookResult,
            PreToolUseEvent,
            PostToolUseEvent,
            PostToolUseFailureEvent,
        )

        def _wrap_tool_with_hooks(tool: ToolSpec, engine: HookEngine) -> ToolSpec:
            """Wrap a tool to invoke pre/post hooks around execution."""
            original_handler = tool._handler

            async def hooked_handler(**kwargs: Any) -> Any:
                # Pre-tool hook
                pre_event = PreToolUseEvent(
                    tool_name=tool.name,
                    tool_input=kwargs,
                )
                pre_result = await engine.run_pre_tool_hooks(pre_event)

                if pre_result.decision == "deny":
                    return {"error": f"Tool blocked by hook: {pre_result.reason or 'denied'}"}

                # Apply modified input if hook modified it
                effective_input = (
                    pre_result.updated_input if pre_result.decision == "modify" else kwargs
                )

                # Execute tool
                start_time = time.time()
                try:
                    if asyncio.iscoroutinefunction(original_handler):
                        result = await original_handler(**effective_input)
                    else:
                        result = original_handler(**effective_input)

                    # Post-tool hook (success)
                    duration_ms = (time.time() - start_time) * 1000
                    post_event = PostToolUseEvent(
                        tool_name=tool.name,
                        tool_input=effective_input,
                        tool_output=result,
                        duration_ms=duration_ms,
                    )
                    await engine.run_post_tool_hooks(post_event)

                    return result
                except Exception as e:
                    # Post-tool failure hook
                    duration_ms = (time.time() - start_time) * 1000
                    fail_event = PostToolUseFailureEvent(
                        tool_name=tool.name,
                        tool_input=effective_input,
                        error=str(e),
                        duration_ms=duration_ms,
                    )
                    await engine.run_post_tool_failure_hooks(fail_event)
                    raise

            # Create new ToolSpec with hooked handler, preserving original schema
            return ToolSpec.from_function(
                hooked_handler,
                name=tool.name,
                description=tool.description,
                input_schema=tool.input_schema,
                output_schema=tool.output_schema,
                category=getattr(tool, "category", None),
                tags=getattr(tool, "tags", None),
            )

        import asyncio
        import time

        all_tools = [_wrap_tool_with_hooks(t, hook_engine) for t in all_tools]

    # Build reasoning-specific Agent constructor args
    agent_kwargs: Dict[str, Any] = {}

    if reasoning_config and reasoning_config.mode == "native":
        # Native mode: pass thinking config via generation_config
        # Anthropic provider picks this up to enable extended thinking
        agent_kwargs["generation_config"] = {
            "thinking": {
                "type": "enabled",
                "budget_tokens": reasoning_config.budget_tokens or 10000,
            }
        }
    elif reasoning_config and reasoning_config.mode == "reflection":
        # Reflection mode: pass ThinkingConfig to vel's ReflectionController
        from vel.thinking import ThinkingConfig

        agent_kwargs["thinking"] = ThinkingConfig(
            mode="reflection",
            max_refinements=reasoning_config.max_refinements,
            confidence_threshold=reasoning_config.confidence_threshold,
            thinking_model=reasoning_config.thinking_model,
            thinking_tools=reasoning_config.thinking_tools,
        )

    # Create vel Agent
    agent = Agent(
        id=agent_config.name,
        model=agent_config.model.to_dict(),
        tools=all_tools,
        system_prompt=combined_prompt,  # Pass the system prompt for caching!
        policies={
            "max_steps": agent_config.max_turns,
            "retry": {"attempts": agent_config.retry_attempts},
        },
        tool_approval_callback=tool_approval_callback,
        **agent_kwargs,
    )

    deep_agent = DeepAgent(
        config=agent_config,
        agent=agent,
        middlewares=middlewares,
        _skip_deprecation=_skip_deprecation,
    )

    # Attach checkpoint manager if provided
    if checkpoint_manager is not None:
        deep_agent._checkpoint_manager = checkpoint_manager

    return deep_agent


def create_research_agent(
    skill_dirs: Optional[List[str]] = None,
    model: Optional[Dict[str, str]] = None,
    **kwargs: Any,
) -> DeepAgent:
    """
    Create a research-focused deep agent.

    Optimized for:
    - Deep research with subagents
    - Document analysis
    - Data gathering and synthesis

    Args:
        skill_dirs: Directories containing research skills
        model: Model configuration
        **kwargs: Additional configuration

    Returns:
        Research-focused DeepAgent
    """
    return create_deep_agent(
        model=model or {"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
        skill_dirs=skill_dirs or [],
        sandbox=True,
        database=False,
        system_prompt="""You are a research assistant capable of deep investigation.

Use subagents to research multiple topics in parallel. Synthesize findings
into clear, well-organized reports. Always cite sources and verify information.

When researching:
1. Break down complex topics into sub-questions
2. Spawn parallel subagents for independent research
3. Gather and verify information
4. Synthesize findings into coherent insights
""",
        **kwargs,
    )


def create_data_agent(
    database_config: Optional[Dict[str, Any]] = None,
    skill_dirs: Optional[List[str]] = None,
    model: Optional[Dict[str, str]] = None,
    **kwargs: Any,
) -> DeepAgent:
    """
    Create a data analysis deep agent.

    Optimized for:
    - SQL query execution
    - Data analysis with Python
    - Report generation

    Args:
        database_config: Database connection configuration
        skill_dirs: Directories containing data skills
        model: Model configuration
        **kwargs: Additional configuration

    Returns:
        Data-focused DeepAgent
    """
    config_dict: Dict[str, Any] = {
        "model": model or {"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
        "sandbox": {"enabled": True, "network": False},
        "database": database_config or {"enabled": True, "readonly": True},
        "skills": {"enabled": True, "skill_dirs": skill_dirs or []},
        "system_prompt": """You are a data analyst with access to databases and Python execution.

When analyzing data:
1. First explore the database schema
2. Write efficient SQL queries
3. Use Python for complex analysis
4. Create clear visualizations and summaries

Always explain your analysis process and findings clearly.
""",
    }

    return create_deep_agent(config=config_dict, **kwargs)


def create_coding_agent(
    working_dir: Optional[str] = None,
    skill_dirs: Optional[List[str]] = None,
    model: Optional[Dict[str, str]] = None,
    **kwargs: Any,
) -> DeepAgent:
    """
    Create a coding-focused deep agent.

    Optimized for:
    - Code writing and execution
    - File management
    - Testing and debugging

    Args:
        working_dir: Working directory for code execution
        skill_dirs: Directories containing coding skills
        model: Model configuration
        **kwargs: Additional configuration

    Returns:
        Coding-focused DeepAgent
    """
    return create_deep_agent(
        model=model or {"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
        skill_dirs=skill_dirs or [],
        sandbox=True,
        database=False,
        working_dir=working_dir or tempfile.mkdtemp(prefix="vel_coding_"),
        system_prompt="""You are a skilled software developer.

When writing code:
1. Plan your approach using the todo list
2. Write clean, well-documented code
3. Test your code by executing it
4. Iterate based on results

Follow best practices for the language you're using. Write tests when appropriate.
""",
        **kwargs,
    )
