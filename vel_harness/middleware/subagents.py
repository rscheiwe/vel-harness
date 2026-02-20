"""
Subagents Middleware

Provides tools for spawning and managing parallel subagents.
Integrates with AgentRegistry for typed agent configurations.
"""

from typing import Any, Dict, List, Optional

from vel import ToolSpec

from vel_harness.agents import AgentRegistry
from vel_harness.middleware.base import BaseMiddleware
from vel_harness.subagents.spawner import (
    SubagentConfig,
    SubagentResult,
    SubagentSpawner,
    SubagentStatus,
)


class SubagentsMiddleware(BaseMiddleware):
    """
    Middleware providing subagent spawning tools.

    Provides tools:
    - spawn_subagent: Create a new subagent for a task
    - spawn_parallel: Spawn multiple subagents for parallel research
    - wait_subagent: Wait for a subagent to complete
    - get_subagent_result: Get result from a completed subagent
    - list_subagents: List all active and completed subagents
    - cancel_subagent: Cancel a running subagent

    Subagents are independent agents that can:
    - Execute research tasks in parallel
    - Have their own tools and context
    - Report results back to the parent agent
    """

    def __init__(
        self,
        default_model: Optional[Dict[str, str]] = None,
        default_system_prompt: Optional[str] = None,
        default_tools: Optional[List[Any]] = None,
        max_concurrent: int = 5,
        max_turns: int = 10,
        timeout: float = 300.0,
        agent_registry: Optional[AgentRegistry] = None,
    ) -> None:
        """
        Initialize subagents middleware.

        Args:
            default_model: Default model config for subagents
            default_system_prompt: Default system prompt for subagents
            default_tools: Default tools for subagents
            max_concurrent: Maximum concurrent subagents
            max_turns: Maximum turns per subagent
            timeout: Default timeout per subagent
            agent_registry: Registry of typed agent configurations
        """
        # Create registry if not provided
        self._agent_registry = agent_registry or AgentRegistry()

        self._default_config = SubagentConfig(
            model=default_model,
            system_prompt=default_system_prompt,
            tools=default_tools,
            max_turns=max_turns,
            timeout=timeout,
        )

        self._spawner = SubagentSpawner(
            default_config=self._default_config,
            max_concurrent=max_concurrent,
            agent_registry=self._agent_registry,
        )

        self._max_concurrent = max_concurrent
        self._available_tools: List[Any] = list(default_tools or [])

    @property
    def spawner(self) -> SubagentSpawner:
        """Get the subagent spawner."""
        return self._spawner

    @property
    def agent_registry(self) -> AgentRegistry:
        """Get the agent registry."""
        return self._agent_registry

    def set_available_tools(self, tools: List[Any]) -> None:
        """Set the full toolset available for subagent filtering."""
        self._available_tools = list(tools)
        self._default_config.tools = list(tools)

    def get_tools(self) -> List[ToolSpec]:
        """Return subagent tools."""
        # Build agent type description from registry
        agent_descriptions = self._agent_registry.get_descriptions()

        return [
            ToolSpec.from_function(
                self._spawn_subagent,
                name="spawn_subagent",
                description=(
                    "Launch a sub-agent to handle a specific task independently.\n\n"
                    "## When to use:\n"
                    "- Complex operations requiring multiple steps\n"
                    "- Work that benefits from isolated context\n"
                    "- Parallel-friendly tasks that don't need your current context\n"
                    "- Exploratory work (use agent='explore')\n"
                    "- Planning work (use agent='plan')\n\n"
                    "## Agent Types:\n"
                    f"{agent_descriptions}\n\n"
                    "## Important:\n"
                    "- Subagent has FRESH context (doesn't see your conversation)\n"
                    "- Provide ALL necessary context in the task description\n"
                    "- Subagent result returns to you as tool_result\n"
                    "- Use for delegation, not for simple tasks\n"
                    "- If you have 2+ independent subagent tasks, prefer spawn_parallel"
                ),
                category="subagents",
                requires_confirmation=True,
            ),
            ToolSpec.from_function(
                self._spawn_parallel,
                name="spawn_parallel",
                description=(
                    "Spawn multiple subagents to research different aspects in parallel. "
                    "Each task gets its own independent subagent. "
                    "Returns list of subagent IDs. "
                    "Prefer this over repeated spawn_subagent calls when tasks are independent."
                ),
                category="subagents",
                requires_confirmation=True,
            ),
            ToolSpec.from_function(
                self._wait_subagent,
                name="wait_subagent",
                description=(
                    "Wait for a specific subagent to complete and get its result. "
                    "Blocks until the subagent finishes."
                ),
                category="subagents",
                requires_confirmation=True,
            ),
            ToolSpec.from_function(
                self._wait_all,
                name="wait_all_subagents",
                description=(
                    "Wait for all active subagents to complete. "
                    "Returns all results."
                ),
                category="subagents",
                requires_confirmation=True,
            ),
            ToolSpec.from_function(
                self._get_result,
                name="get_subagent_result",
                description=(
                    "Get the result from a completed subagent. "
                    "Returns None if subagent is still running."
                ),
                category="subagents",
                requires_confirmation=True,
            ),
            ToolSpec.from_function(
                self._list_subagents,
                name="list_subagents",
                description="List all active and completed subagents with their status.",
                category="subagents",
            ),
            ToolSpec.from_function(
                self._cancel_subagent,
                name="cancel_subagent",
                description="Cancel a running subagent.",
                category="subagents",
            ),
            ToolSpec.from_function(
                self._run_subagent_workflow,
                name="run_subagent_workflow",
                description=(
                    "Run a structured multi-role workflow: discover -> implement -> verify"
                    " -> critic (optional), and return a merged result."
                ),
                category="subagents",
                requires_confirmation=True,
            ),
        ]

    def get_system_prompt_segment(self) -> str:
        """Return system prompt describing subagent capabilities."""
        agent_descriptions = self._agent_registry.get_descriptions()

        return f"""## Parallel Subagents

You can spawn independent subagents to handle research and complex tasks in parallel.

**Available Agent Types:**
{agent_descriptions}

**Available Tools:**
- `spawn_subagent(task, agent="default")`: Create a subagent for a task
- `spawn_parallel(tasks)`: Spawn multiple subagents at once
- `wait_subagent(id)`: Wait for a subagent to complete
- `wait_all_subagents()`: Wait for all subagents
- `get_subagent_result(id)`: Get result (non-blocking)
- `list_subagents()`: Show all subagents
- `cancel_subagent(id)`: Stop a running subagent
- `run_subagent_workflow(goal, include_critic=True)`: One-call multi-role workflow

**Configuration:**
- Max concurrent: {self._max_concurrent}
- Default timeout: {self._default_config.timeout}s
- Max turns per subagent: {self._default_config.max_turns}

**Key Principles:**
- Subagents get FRESH context (isolated from parent conversation)
- Provide ALL necessary context in the task description
- Use agent="explore" for read-only investigation
- Use agent="plan" for structured planning tasks
- Use agent="discover" for environment and codebase mapping
- Use agent="implement" for focused code changes
- Use agent="verify" for spec and test validation
- Use agent="critic" for independent quality challenge
- Use default for general task execution
- If you identify 2+ independent investigations, batch them with `spawn_parallel`
"""

    async def run_workflow(self, goal: str, include_critic: bool = True) -> Dict[str, Any]:
        """Run discover -> implement -> verify -> critic workflow."""
        discover_prompt = (
            "Goal:\n"
            f"{goal}\n\n"
            "Produce: relevant files, constraints, interfaces, and suggested verification commands."
        )
        discover = await self._spawn_and_wait(discover_prompt, agent="discover")

        implement_prompt = (
            "Goal:\n"
            f"{goal}\n\n"
            "Discovery findings:\n"
            f"{discover.get('result', discover)}\n\n"
            "Implement the required changes with focused scope."
        )
        implement = await self._spawn_and_wait(implement_prompt, agent="implement")

        verify_prompt = (
            "Goal:\n"
            f"{goal}\n\n"
            "Implementation output:\n"
            f"{implement.get('result', implement)}\n\n"
            "Verify against spec using tests/checks and return pass/fail evidence."
        )
        verify = await self._spawn_and_wait(verify_prompt, agent="verify")

        critic: Dict[str, Any] = {}
        if include_critic:
            critic_prompt = (
                "Goal:\n"
                f"{goal}\n\n"
                "Discovery:\n"
                f"{discover.get('result', discover)}\n\n"
                "Implementation:\n"
                f"{implement.get('result', implement)}\n\n"
                "Verification:\n"
                f"{verify.get('result', verify)}\n\n"
                "Provide an independent critique with specific risks and fixes."
            )
            critic = await self._spawn_and_wait(critic_prompt, agent="critic")

        return {
            "status": "completed",
            "goal": goal,
            "stages": {
                "discover": discover,
                "implement": implement,
                "verify": verify,
                "critic": critic if include_critic else {"status": "skipped"},
            },
            "summary": {
                "discover_status": discover.get("status"),
                "implement_status": implement.get("status"),
                "verify_status": verify.get("status"),
                "critic_status": critic.get("status") if include_critic else "skipped",
            },
        }

    async def _run_subagent_workflow(
        self,
        goal: str,
        include_critic: bool = True,
    ) -> Dict[str, Any]:
        """Tool wrapper for one-call workflow execution."""
        try:
            return await self.run_workflow(goal=goal, include_critic=include_critic)
        except Exception as e:
            return {"error": str(e)}

    async def _spawn_and_wait(self, task: str, agent: str) -> Dict[str, Any]:
        """Spawn subagent for a role and wait for completion."""
        subagent_id = await self._spawner.spawn(task, None, agent=agent)
        result = await self._spawner.wait(subagent_id)
        payload = result.to_dict()
        payload["agent"] = agent
        return payload

    async def _spawn_subagent(
        self,
        task: str,
        agent: str = "default",
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Spawn a new subagent.

        Args:
            task: Task description for the subagent (include ALL necessary context)
            agent: Agent type from registry ("default", "explore", "plan", or custom)
            system_prompt: Optional custom system prompt (overrides agent type prompt)

        Returns:
            Dict with subagent ID and metadata
        """
        config = None
        if system_prompt:
            # Custom system prompt overrides agent type
            config = SubagentConfig(
                model=self._default_config.model,
                system_prompt=system_prompt,
                tools=self._default_config.tools,
                max_turns=self._default_config.max_turns,
                timeout=self._default_config.timeout,
            )

        try:
            subagent_id = await self._spawner.spawn(task, config, agent=agent)

            # Get agent config for metadata
            agent_config = self._agent_registry.get(agent)

            return {
                "status": "spawned",
                "id": subagent_id,
                "task": task,
                "agent": agent,
                "agent_description": agent_config.description,
            }
        except Exception as e:
            return {"error": str(e)}

    async def _spawn_parallel(
        self,
        tasks: List[str],
    ) -> Dict[str, Any]:
        """
        Spawn multiple subagents in parallel.

        Args:
            tasks: List of task descriptions

        Returns:
            Dict with list of subagent IDs
        """
        if len(tasks) > self._max_concurrent:
            return {
                "error": f"Too many tasks ({len(tasks)}). "
                f"Maximum concurrent: {self._max_concurrent}"
            }

        try:
            ids = await self._spawner.spawn_many(tasks)
            return {
                "status": "spawned",
                "count": len(ids),
                "subagents": [
                    {"id": sid, "task": task}
                    for sid, task in zip(ids, tasks)
                ],
            }
        except Exception as e:
            return {"error": str(e)}

    async def _wait_subagent(self, subagent_id: str) -> Dict[str, Any]:
        """
        Wait for a subagent to complete.

        Args:
            subagent_id: ID of the subagent

        Returns:
            Dict with subagent result
        """
        try:
            result = await self._spawner.wait(subagent_id)
            return result.to_dict()
        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": f"Error waiting for subagent: {e}"}

    async def _wait_all(self) -> Dict[str, Any]:
        """
        Wait for all active subagents.

        Returns:
            Dict with all results
        """
        try:
            results = await self._spawner.wait_all()
            return {
                "count": len(results),
                "results": [r.to_dict() for r in results],
            }
        except Exception as e:
            return {"error": str(e)}

    def _get_result(self, subagent_id: str) -> Dict[str, Any]:
        """
        Get result for a subagent (non-blocking).

        Args:
            subagent_id: ID of the subagent

        Returns:
            Dict with result or status
        """
        result = self._spawner.get_result(subagent_id)
        if result:
            return result.to_dict()

        status = self._spawner.get_status(subagent_id)
        if status:
            return {
                "id": subagent_id,
                "status": status.value,
                "message": "Subagent is still running" if status == SubagentStatus.RUNNING else "Unknown",
            }

        return {"error": f"Subagent '{subagent_id}' not found"}

    def _list_subagents(self) -> Dict[str, Any]:
        """
        List all subagents.

        Returns:
            Dict with subagent list
        """
        subagents = self._spawner.list_subagents()
        active = sum(1 for s in subagents if s.get("status") == "running")

        return {
            "active": active,
            "total": len(subagents),
            "subagents": subagents,
        }

    def _cancel_subagent(self, subagent_id: str) -> Dict[str, Any]:
        """
        Cancel a running subagent.

        Args:
            subagent_id: ID of the subagent

        Returns:
            Dict with cancellation status
        """
        if self._spawner.cancel(subagent_id):
            return {"status": "cancelled", "id": subagent_id}
        return {"error": f"Subagent '{subagent_id}' not found or already completed"}

    def get_state(self) -> Dict[str, Any]:
        """Get middleware state."""
        return {
            "max_concurrent": self._max_concurrent,
            "active_count": self._spawner.active_count,
            "completed_count": len(self._spawner.results),
        }

    def load_state(self, state: Dict[str, Any]) -> None:
        """Load middleware state."""
        # Note: Subagent tasks are not persisted
        self._max_concurrent = state.get("max_concurrent", self._max_concurrent)
