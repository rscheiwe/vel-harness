"""
Subagent Spawner

Provides parallel subagent spawning for deep research and complex tasks.
Integrates with AgentRegistry for typed agent configurations.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from vel import Agent

if TYPE_CHECKING:
    from vel_harness.agents.registry import AgentRegistry


class SubagentStatus(Enum):
    """Status of a subagent."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SubagentResult:
    """Result from a subagent execution."""

    id: str
    task: str
    status: SubagentStatus
    result: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    messages: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def duration_seconds(self) -> Optional[float]:
        """Get execution duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "task": self.task,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class SubagentConfig:
    """Configuration for spawning subagents."""

    model: Optional[Dict[str, str]] = None
    system_prompt: Optional[str] = None
    tools: Optional[List[Any]] = None
    max_turns: int = 10
    timeout: float = 300.0  # 5 minutes default


class SubagentSpawner:
    """
    Manages spawning and execution of parallel subagents.

    Subagents are independent agent instances that can:
    - Execute research tasks in parallel
    - Have their own tools and context
    - Report results back to the parent agent

    Integrates with AgentRegistry for typed agent configurations:
    - "default": General-purpose task execution
    - "explore": Read-only codebase exploration
    - "plan": Structured planning and task breakdown
    """

    def __init__(
        self,
        default_config: Optional[SubagentConfig] = None,
        max_concurrent: int = 5,
        on_result: Optional[Callable[[SubagentResult], None]] = None,
        agent_registry: Optional["AgentRegistry"] = None,
    ) -> None:
        """
        Initialize subagent spawner.

        Args:
            default_config: Default configuration for subagents
            max_concurrent: Maximum concurrent subagents
            on_result: Callback when a subagent completes
            agent_registry: Registry of typed agent configurations
        """
        self._default_config = default_config or SubagentConfig()
        self._max_concurrent = max_concurrent
        self._on_result = on_result
        self._agent_registry = agent_registry

        self._active: Dict[str, asyncio.Task[SubagentResult]] = {}
        self._results: Dict[str, SubagentResult] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)

    @property
    def active_count(self) -> int:
        """Get number of active subagents."""
        return len(self._active)

    @property
    def results(self) -> List[SubagentResult]:
        """Get all completed results."""
        return list(self._results.values())

    @property
    def agent_registry(self) -> Optional["AgentRegistry"]:
        """Get the agent registry."""
        return self._agent_registry

    @agent_registry.setter
    def agent_registry(self, registry: "AgentRegistry") -> None:
        """Set the agent registry."""
        self._agent_registry = registry

    def list_agent_types(self) -> List[str]:
        """List available agent types from registry."""
        if self._agent_registry:
            return self._agent_registry.list_agents()
        return ["default"]

    def _generate_id(self) -> str:
        """Generate a unique subagent ID."""
        return f"subagent_{uuid.uuid4().hex[:8]}"

    def _resolve_tools(
        self,
        allowed_tool_names: Optional[List[str]],
        default_tools: Optional[List[Any]],
    ) -> List[Any]:
        """Resolve tool instances for a subagent, optionally filtered by name."""
        tools = list(default_tools or [])
        if not allowed_tool_names:
            return tools

        allowed = set(allowed_tool_names)
        return [t for t in tools if getattr(t, "name", None) in allowed]

    async def _run_subagent(
        self,
        subagent_id: str,
        task: str,
        config: SubagentConfig,
    ) -> SubagentResult:
        """
        Run a single subagent.

        Args:
            subagent_id: Unique ID for this subagent
            task: Task description
            config: Subagent configuration

        Returns:
            SubagentResult with execution outcome
        """
        result = SubagentResult(
            id=subagent_id,
            task=task,
            status=SubagentStatus.PENDING,
        )

        async with self._semaphore:
            result.status = SubagentStatus.RUNNING
            result.started_at = datetime.now()

            try:
                # Create agent instance
                agent = Agent(
                    id=subagent_id,
                    model=config.model or self._default_config.model,
                    system_prompt=config.system_prompt or self._default_config.system_prompt,
                    tools=config.tools or self._default_config.tools or [],
                    policies={"max_steps": config.max_turns},
                )

                # Run the agent with timeout
                try:
                    response = await asyncio.wait_for(
                        agent.run({"message": task}),
                        timeout=config.timeout,
                    )

                    result.status = SubagentStatus.COMPLETED
                    result.result = response.content if hasattr(response, "content") else str(response)
                    result.messages = response.messages if hasattr(response, "messages") else []

                except asyncio.TimeoutError:
                    result.status = SubagentStatus.FAILED
                    result.error = f"Subagent timed out after {config.timeout}s"

            except asyncio.CancelledError:
                result.status = SubagentStatus.CANCELLED
                result.error = "Subagent was cancelled"
                raise

            except Exception as e:
                result.status = SubagentStatus.FAILED
                result.error = str(e)

            finally:
                result.completed_at = datetime.now()

        return result

    async def spawn(
        self,
        task: str,
        config: Optional[SubagentConfig] = None,
        agent: str = "default",
    ) -> str:
        """
        Spawn a new subagent.

        Args:
            task: Task for the subagent to perform
            config: Optional configuration override
            agent: Agent type from registry ("default", "explore", "plan", or custom)

        Returns:
            Subagent ID for tracking
        """
        subagent_id = self._generate_id()

        # If agent type specified and registry available, get config from registry
        if self._agent_registry and agent != "default" and config is None:
            agent_config = self._agent_registry.get(agent)
            effective_config = SubagentConfig(
                model=agent_config.model,
                system_prompt=agent_config.system_prompt,
                tools=self._resolve_tools(agent_config.tools, self._default_config.tools),
                max_turns=agent_config.max_turns,
                timeout=agent_config.timeout,
            )
        elif config is not None:
            effective_config = config
        else:
            # Try to get default from registry, fallback to default_config
            if self._agent_registry:
                agent_config = self._agent_registry.get(agent)
                effective_config = SubagentConfig(
                    model=agent_config.model or self._default_config.model,
                    system_prompt=agent_config.system_prompt or self._default_config.system_prompt,
                    tools=self._resolve_tools(agent_config.tools, self._default_config.tools),
                    max_turns=agent_config.max_turns,
                    timeout=agent_config.timeout,
                )
            else:
                effective_config = self._default_config

        # Create and store task
        coro = self._run_subagent(subagent_id, task, effective_config)
        task_obj = asyncio.create_task(coro)

        self._active[subagent_id] = task_obj

        # Set up completion callback
        def on_done(t: asyncio.Task[SubagentResult]) -> None:
            try:
                result = t.result()
            except asyncio.CancelledError:
                result = SubagentResult(
                    id=subagent_id,
                    task=task,
                    status=SubagentStatus.CANCELLED,
                    error="Cancelled",
                )
            except Exception as e:
                result = SubagentResult(
                    id=subagent_id,
                    task=task,
                    status=SubagentStatus.FAILED,
                    error=str(e),
                )

            # Store result
            self._results[subagent_id] = result
            self._active.pop(subagent_id, None)

            # Invoke callback
            if self._on_result:
                self._on_result(result)

        task_obj.add_done_callback(on_done)

        return subagent_id

    async def spawn_many(
        self,
        tasks: List[str],
        config: Optional[SubagentConfig] = None,
        agent: str = "default",
    ) -> List[str]:
        """
        Spawn multiple subagents IN PARALLEL.

        Args:
            tasks: List of tasks for subagents
            config: Optional shared configuration
            agent: Agent type for all subagents

        Returns:
            List of subagent IDs in same order as tasks
        """
        # Create all spawn coroutines and execute in parallel
        spawn_coros = [self.spawn(task, config, agent) for task in tasks]
        ids = await asyncio.gather(*spawn_coros)
        return list(ids)

    async def wait(self, subagent_id: str) -> SubagentResult:
        """
        Wait for a specific subagent to complete.

        Args:
            subagent_id: ID of subagent to wait for

        Returns:
            SubagentResult
        """
        if subagent_id in self._results:
            return self._results[subagent_id]

        if subagent_id in self._active:
            return await self._active[subagent_id]

        raise ValueError(f"Unknown subagent: {subagent_id}")

    async def wait_all(self, subagent_ids: Optional[List[str]] = None) -> List[SubagentResult]:
        """
        Wait for multiple subagents to complete IN PARALLEL.

        Args:
            subagent_ids: IDs to wait for (all active if None)

        Returns:
            List of results in same order as IDs
        """
        ids = subagent_ids or list(self._active.keys())

        if not ids:
            return []

        # Create wait coroutines for all subagents
        async def safe_wait(sid: str) -> SubagentResult:
            """Wait for a subagent, returning cached result if available."""
            if sid in self._results:
                return self._results[sid]
            if sid in self._active:
                return await self._active[sid]
            raise ValueError(f"Unknown subagent: {sid}")

        # Wait for all in parallel, handling individual failures
        wait_results = await asyncio.gather(
            *[safe_wait(sid) for sid in ids],
            return_exceptions=True
        )

        # Process results, filtering out exceptions
        results = []
        for sid, result in zip(ids, wait_results):
            if isinstance(result, Exception):
                # Try to get from results cache
                if sid in self._results:
                    results.append(self._results[sid])
                # else skip this one
            else:
                results.append(result)

        return results

    def cancel(self, subagent_id: str) -> bool:
        """
        Cancel a running subagent.

        Args:
            subagent_id: ID of subagent to cancel

        Returns:
            True if cancelled
        """
        if subagent_id in self._active:
            self._active[subagent_id].cancel()
            return True
        return False

    def cancel_all(self) -> int:
        """
        Cancel all running subagents.

        Returns:
            Number of subagents cancelled
        """
        count = 0
        for task in self._active.values():
            task.cancel()
            count += 1
        return count

    def get_result(self, subagent_id: str) -> Optional[SubagentResult]:
        """
        Get result for a subagent (if completed).

        Args:
            subagent_id: Subagent ID

        Returns:
            Result if available, None otherwise
        """
        return self._results.get(subagent_id)

    def get_status(self, subagent_id: str) -> Optional[SubagentStatus]:
        """
        Get status of a subagent.

        Args:
            subagent_id: Subagent ID

        Returns:
            Status if found
        """
        if subagent_id in self._results:
            return self._results[subagent_id].status
        if subagent_id in self._active:
            return SubagentStatus.RUNNING
        return None

    def list_subagents(self) -> List[Dict[str, Any]]:
        """
        List all subagents with status.

        Returns:
            List of subagent info dicts
        """
        subagents = []

        # Active subagents
        for sid in self._active:
            subagents.append({
                "id": sid,
                "status": SubagentStatus.RUNNING.value,
            })

        # Completed subagents
        for sid, result in self._results.items():
            subagents.append(result.to_dict())

        return subagents

    def clear_results(self) -> int:
        """
        Clear completed results.

        Returns:
            Number of results cleared
        """
        count = len(self._results)
        self._results.clear()
        return count
