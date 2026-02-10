"""
Vel Harness Session - Stateful interactive session with mid-conversation controls.

Provides a session wrapper around VelHarness that supports:
- Persistent session_id across multiple queries
- Model switching mid-conversation via set_model()
- Interrupt current generation via interrupt()
- Reasoning mode changes via set_reasoning()

Usage:
    from vel_harness import VelHarness

    harness = VelHarness(model={"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"})

    async with harness.create_session(session_id="user-123") as session:
        async for event in session.query("Analyze this codebase"):
            print(event)

        session.set_model("opus")
        async for event in session.query("Now implement the fix"):
            print(event)
"""

import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Union

from vel_harness.agents.config import AgentDefinition
from vel_harness.reasoning import ReasoningConfig


class HarnessSession:
    """Stateful, interactive session with mid-conversation controls.

    Wraps a VelHarness with a persistent session_id and supports
    model switching, interrupt, and reasoning changes between queries.

    Args:
        harness: The VelHarness instance to wrap
        session_id: Session ID for context continuity (auto-generated if not provided)
    """

    def __init__(
        self,
        harness: Any,  # VelHarness — use Any to avoid circular import
        session_id: Optional[str] = None,
    ) -> None:
        self._harness = harness
        self._session_id = session_id or str(uuid.uuid4())
        self._interrupted = False
        self._query_count = 0

    @property
    def session_id(self) -> str:
        """Get the session ID."""
        return self._session_id

    @property
    def harness(self) -> Any:
        """Get the underlying VelHarness."""
        return self._harness

    @property
    def query_count(self) -> int:
        """Get the number of queries executed in this session."""
        return self._query_count

    @property
    def model(self) -> Dict[str, Any]:
        """Get the current model configuration."""
        return self._harness.deep_agent.agent.model_cfg

    async def query(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Send a query and stream responses.

        Uses the session's persistent session_id for context continuity.
        Respects interrupt() — if called during streaming, yields an
        interrupted event and stops.

        Args:
            message: User message
            context: Optional additional context for this query

        Yields:
            Stream events from the agent
        """
        self._interrupted = False
        self._query_count += 1

        async for event in self._harness.deep_agent.run_stream(
            input_text=message,
            session_id=self._session_id,
            context=context,
        ):
            if self._interrupted:
                yield {"type": "interrupted", "session_id": self._session_id}
                return
            yield event

    async def run(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Send a query and get the full response (non-streaming).

        Args:
            message: User message
            context: Optional additional context

        Returns:
            Agent's response text
        """
        text_parts: List[str] = []
        last_event = None

        async for event in self.query(message=message, context=context):
            last_event = event
            if isinstance(event, dict):
                if event.get("type") == "text-delta":
                    text_parts.append(event.get("delta", ""))
                elif event.get("type") == "interrupted":
                    return "[interrupted]"
                elif event.get("type") == "error":
                    return f"[error: {event.get('error', 'unknown')}]"

        if text_parts:
            return "".join(text_parts)
        if last_event is not None:
            if hasattr(last_event, "content"):
                return last_event.content
            if isinstance(last_event, dict) and "content" in last_event:
                return last_event["content"]
            return str(last_event)
        return ""

    def set_model(self, model: Union[str, Dict[str, Any]]) -> None:
        """Switch model for subsequent queries.

        Accepts model shorthand ("sonnet", "opus", "haiku") or a full
        model config dict.

        Args:
            model: Model shorthand string or full config dict
        """
        if isinstance(model, str):
            resolved = AgentDefinition._resolve_model(model)
            if resolved is None:
                raise ValueError(f"Cannot resolve model: {model!r}")
            self._harness.deep_agent.agent.model_cfg = resolved
        else:
            self._harness.deep_agent.agent.model_cfg = model

    def interrupt(self) -> None:
        """Signal to stop current generation.

        The next event yielded by query() will be an interrupted event,
        then the stream will end.
        """
        self._interrupted = True

    @property
    def is_interrupted(self) -> bool:
        """Check if the session is currently interrupted."""
        return self._interrupted

    def set_reasoning(
        self, config: Union[str, Dict[str, Any], ReasoningConfig, None]
    ) -> None:
        """Change reasoning mode for subsequent queries.

        Note: This updates the stored reasoning config. Changes that affect
        the system prompt (prompted mode) or generation config (native mode)
        take effect through the agent's configuration — complex mode switches
        may require creating a new session.

        For simple cases (switching between none and native, or adjusting
        budget_tokens), this works directly.

        Args:
            config: Reasoning config — string shorthand ("native", "prompted",
                    "reflection", "none"), dict, ReasoningConfig, or None
        """
        if config is None:
            self._harness._reasoning_config = None
            return

        resolved = ReasoningConfig.from_value(config)
        self._harness._reasoning_config = resolved

        # Apply native mode generation_config directly if possible
        if resolved.mode == "native":
            agent = self._harness.deep_agent.agent
            agent.generation_config = {
                "thinking": {
                    "type": "enabled",
                    "budget_tokens": resolved.budget_tokens or 10000,
                }
            }
        elif resolved.mode == "none":
            agent = self._harness.deep_agent.agent
            if hasattr(agent, "generation_config"):
                agent.generation_config = {}

    def create_checkpoint(self, label: Optional[str] = None) -> str:
        """Create a filesystem checkpoint at the current state.

        All file changes after this point can be reverted with rewind_files().

        Args:
            label: Optional human-readable label

        Returns:
            Checkpoint ID
        """
        return self._harness.checkpoint_manager.create_checkpoint(label=label)

    def rewind_files(self, checkpoint_id: str) -> List[str]:
        """Revert all filesystem changes since the given checkpoint.

        Restores files to their state at checkpoint creation time.
        New files written after the checkpoint are cleared.
        Edited files are restored to their pre-edit content.

        Args:
            checkpoint_id: The checkpoint to rewind to

        Returns:
            List of file paths that were reverted

        Raises:
            ValueError: If checkpoint_id is not found
        """
        # Get the filesystem backend for writing restored content
        fs_middleware = self._harness.deep_agent.middlewares.get("filesystem")
        backend = None
        if fs_middleware is not None:
            backend = getattr(fs_middleware, "_backend", None) or getattr(fs_middleware, "backend", None)

        if backend is None:
            raise RuntimeError("No filesystem backend available for rewind")

        return self._harness.checkpoint_manager.rewind_to(checkpoint_id, backend)

    def get_changed_files(self) -> List[str]:
        """Get list of all files changed in this session.

        Returns:
            Deduplicated list of file paths
        """
        return self._harness.checkpoint_manager.get_changed_files()

    def get_state(self) -> Dict[str, Any]:
        """Get session state for persistence.

        Returns:
            Dict with session_id, query_count, model config, and checkpoint info
        """
        return {
            "session_id": self._session_id,
            "query_count": self._query_count,
            "model": dict(self._harness.deep_agent.agent.model_cfg),
            "checkpoints": len(self._harness.checkpoint_manager.checkpoints),
            "changes": self._harness.checkpoint_manager.change_count,
        }

    async def __aenter__(self) -> "HarnessSession":
        """Enter async context manager."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit async context manager."""
        # Reset interrupt flag on exit
        self._interrupted = False
