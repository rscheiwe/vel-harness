"""
Valis CLI Agent

Integration with vel_harness for agent creation and execution.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Union

from vel_harness import VelHarness
from vel_harness.middleware import ContextManagementMiddleware
from vel_harness.prompts import compose_system_prompt

from valis_cli.config import Config, ModelSettings, Permissions


class EventType(str, Enum):
    """Event types emitted during agent execution."""

    # Text events
    TEXT_START = "text-start"
    TEXT_DELTA = "text-delta"
    TEXT_END = "text-end"

    # Tool events
    TOOL_CALL = "tool-call"
    TOOL_RESULT = "tool-result"

    # Control events
    THINKING_START = "thinking-start"
    THINKING_DELTA = "thinking-delta"
    THINKING_END = "thinking-end"

    # Approval events
    APPROVAL_REQUIRED = "approval-required"
    APPROVAL_RESPONSE = "approval-response"

    # Session events
    SESSION_START = "session-start"
    SESSION_END = "session-end"
    ERROR = "error"

    # Metadata events
    RESPONSE_METADATA = "response-metadata"


@dataclass
class AgentEvent:
    """Event emitted during agent execution."""

    type: EventType
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.type.value,
            "data": self.data,
            "timestamp": self.timestamp,
        }


@dataclass
class ToolCall:
    """A tool call requiring approval."""

    id: str
    name: str
    args: Dict[str, Any]
    description: Optional[str] = None

    def format_for_display(self) -> str:
        """Format tool call for display."""
        args_str = ", ".join(f"{k}={repr(v)[:50]}" for k, v in self.args.items())
        return f"{self.name}({args_str})"


class ApprovalHandler:
    """Handles tool approval decisions."""

    def __init__(
        self,
        auto_approve: Optional[List[str]] = None,
        always_deny: Optional[List[str]] = None,
        callback: Optional[Callable[[ToolCall], bool]] = None,
    ):
        self.auto_approve = set(auto_approve or [])
        self.always_deny = set(always_deny or [])
        self.callback = callback
        self._pending: Dict[str, ToolCall] = {}

    def should_auto_approve(self, tool_name: str) -> bool:
        """Check if tool should be auto-approved."""
        return tool_name in self.auto_approve

    def should_deny(self, tool_name: str) -> bool:
        """Check if tool should be denied."""
        return tool_name in self.always_deny

    def add_pending(self, tool_call: ToolCall) -> None:
        """Add a pending approval."""
        self._pending[tool_call.id] = tool_call

    def get_pending(self, tool_id: str) -> Optional[ToolCall]:
        """Get a pending approval."""
        return self._pending.get(tool_id)

    def resolve(self, tool_id: str, approved: bool) -> bool:
        """Resolve a pending approval."""
        if tool_id in self._pending:
            del self._pending[tool_id]
            return approved
        return False

    def clear_pending(self) -> None:
        """Clear all pending approvals."""
        self._pending.clear()


class AgentRunner:
    """
    Runs the agent and yields events for the TUI.

    Handles:
    - Agent execution with streaming
    - Tool approval flow
    - Event normalization
    - Session management
    """

    def __init__(
        self,
        config: Config,
        approval_handler: Optional[ApprovalHandler] = None,
    ):
        self.config = config
        self.approval_handler = approval_handler or ApprovalHandler(
            auto_approve=config.approval.auto_approve,
            always_deny=config.approval.always_deny,
        )
        self._agent: Optional[VelHarness] = None
        self._session_id: str = str(uuid.uuid4())[:8]
        self._messages: List[Dict[str, Any]] = []
        self._running = False

        # Load permissions from settings.local.json
        self._permissions = config.load_permissions()

        # Pending approval callbacks
        self._pending_approvals: Dict[str, asyncio.Future] = {}

        # Message tracking state (reset each turn)
        self._current_assistant_text: str = ""
        self._current_tool_calls: List[Dict[str, Any]] = []
        self._pending_tool_results: Dict[str, Dict[str, Any]] = {}

        # Cumulative token usage from API
        self._total_usage: Dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
        }

    @property
    def session_id(self) -> str:
        """Get current session ID."""
        return self._session_id

    @property
    def is_running(self) -> bool:
        """Check if agent is currently running."""
        return self._running

    @property
    def _context_middleware(self) -> Optional[ContextManagementMiddleware]:
        """Get context middleware from VelHarness."""
        if self._agent is None:
            return None
        return self._agent.deep_agent.context

    async def initialize(self) -> None:
        """Initialize the agent."""
        if self._agent is not None:
            return

        # Get skill directories (check multiple locations)
        skill_dirs = []

        # 1. Global skills (~/.valis/skills/)
        if self.config.skills_dir.exists():
            skill_dirs.append(str(self.config.skills_dir))

        # 2. Project skills (.valis/skills/)
        if self.config.project_dir:
            project_skills = self.config.project_dir / "skills"
            if project_skills.exists():
                skill_dirs.append(str(project_skills))

        # 3. vel-harness package skills (where this code lives)
        package_skills = Path(__file__).parent.parent / "skills"
        if package_skills.exists() and str(package_skills) not in skill_dirs:
            skill_dirs.append(str(package_skills))

        # 4. Current working directory skills
        cwd_skills = Path.cwd() / "skills"
        if cwd_skills.exists() and str(cwd_skills) not in skill_dirs:
            skill_dirs.append(str(cwd_skills))

        # Create tool approval callback
        async def tool_approval_callback(tool_name: str, tool_args: Dict[str, Any], tool_call_id: str) -> bool:
            """Check if tool is approved to run."""
            # Check permission
            permission = self.check_tool_permission(tool_name, tool_args)

            if permission == "allow":
                return True
            elif permission == "deny":
                return False
            else:
                # Tool needs approval - for now, auto-approve and show dialog as informational
                # The dialog allows user to click "Always Allow" to save permission for future
                # Blocking approval would require a more complex architecture
                # (separate thread/process for TUI, or restructuring vel's event loop)
                return True

        # Build system prompt using modular composition
        import os
        system_prompt = self._build_system_prompt()

        self._agent = VelHarness(
            model=self.config.model.to_dict(),
            skill_dirs=skill_dirs,
            sandbox=self.config.sandbox_enabled,
            database=self.config.database_enabled,
            system_prompt=system_prompt,
            working_directory=os.getcwd(),  # Use real filesystem from current directory
            planning=True,
            tool_approval_callback=tool_approval_callback,
        )

        # Track system prompt in messages for /tokens command
        self._messages.append({
            "role": "system",
            "content": system_prompt,
        })

        # Load AGENTS.md if exists
        if self.config.agents_file.exists():
            agents_content = self.config.agents_file.read_text()
            self._messages.append({
                "role": "system",
                "content": f"<agent_knowledge>\n{agents_content}\n</agent_knowledge>",
            })

    def _build_system_prompt(self) -> str:
        """Build the system prompt using modular composition."""
        import os

        # Use composed prompt from vel_harness.prompts
        base_prompt = compose_system_prompt(
            working_dir=os.getcwd(),
            agent_name=self.config.agent_name,
        )

        # Add project context if available
        if self.config.project_dir:
            base_prompt += f"\n\n## Project Context\nWorking in project: {self.config.project_dir.parent.name}"

        return base_prompt

    async def run(
        self,
        user_input: str,
        images: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncIterator[AgentEvent]:
        """
        Run the agent with user input.

        Args:
            user_input: User's message text
            images: Optional list of image dicts with keys:
                    - type: "image"
                    - image: base64 encoded data
                    - mimeType: e.g., "image/png"

        Yields:
            AgentEvent instances
        """
        await self.initialize()

        if self._agent is None:
            yield AgentEvent(
                type=EventType.ERROR,
                data={"error": "Agent not initialized"},
            )
            return

        self._running = True

        try:
            # Build content - either string or list for multimodal
            if images:
                # Multimodal: list of content parts
                content: Union[str, List[Dict[str, Any]]] = []
                # Add images first
                for img in images:
                    content.append({
                        "type": "image",
                        "image": img.get("image"),
                        "mimeType": img.get("mimeType", "image/png"),
                    })
                # Add text
                if user_input:
                    content.append({
                        "type": "text",
                        "text": user_input,
                    })
            else:
                # Text only
                content = user_input

            # Add user message to local tracking
            self._messages.append({
                "role": "user",
                "content": content,
            })

            yield AgentEvent(type=EventType.SESSION_START, data={
                "session_id": self._session_id,
            })

            # Run agent with streaming
            async for event in self._run_with_approval():
                yield event

            yield AgentEvent(type=EventType.SESSION_END, data={
                "session_id": self._session_id,
            })

        except Exception as e:
            yield AgentEvent(
                type=EventType.ERROR,
                data={"error": str(e), "type": type(e).__name__},
            )
        finally:
            self._running = False

    async def _run_with_approval(self) -> AsyncIterator[AgentEvent]:
        """Run agent with tool approval handling."""
        # Reset turn-level tracking
        self._current_assistant_text = ""
        self._current_tool_calls = []
        self._pending_tool_results = {}

        try:
            # Get content from last message (may be string or multimodal list)
            last_content = self._messages[-1]["content"]
            async for event in self._agent.run_stream(
                message=last_content,
                session_id=self._session_id,
            ):
                # Track events for message history
                self._track_event(event)

                # Normalize events from vel to CLI format
                normalized = self._normalize_event(event)
                if normalized:
                    yield normalized

            # Finalize assistant message at end of turn
            await self._finalize_turn_messages()

        except Exception as e:
            import traceback
            yield AgentEvent(
                type=EventType.ERROR,
                data={"error": f"{str(e)}\n{traceback.format_exc()}"},
            )

    def _track_event(self, event: Any) -> None:
        """Track event for message history building."""
        if not isinstance(event, dict):
            if hasattr(event, 'to_dict'):
                event = event.to_dict()
            else:
                return

        event_type = event.get("type", "")

        if event_type == "text-delta":
            # Accumulate assistant text
            self._current_assistant_text += event.get("delta", "")

        elif event_type == "tool-input-available":
            # Track tool call
            tool_call = {
                "id": event.get("toolCallId", ""),
                "name": event.get("toolName", ""),
                "args": event.get("input", {}),
            }
            self._current_tool_calls.append(tool_call)

        elif event_type == "tool-output-available":
            # Track tool result
            tool_id = event.get("toolCallId", "")
            tool_name = event.get("toolName", "unknown")
            content = str(event.get("output", ""))

            # Process through context middleware (truncation if needed)
            ctx_mw = self._context_middleware
            if ctx_mw is not None:
                content = ctx_mw.process_tool_result(
                    content=content,
                    tool_name=tool_name,
                    tool_call_id=tool_id,
                )

            self._pending_tool_results[tool_id] = {
                "role": "tool",
                "tool_call_id": tool_id,
                "content": content,
            }

        elif event_type == "response-metadata":
            # Track cumulative token usage from API
            # Handle None usage gracefully (early metadata events have usage=None)
            usage = event.get("usage") or {}
            prompt = usage.get("promptTokens", 0) or usage.get("inputTokens", 0)
            completion = usage.get("completionTokens", 0) or usage.get("outputTokens", 0)
            total = usage.get("totalTokens", 0)
            cache_read = usage.get("cacheReadTokens", 0)
            cache_creation = usage.get("cacheCreationTokens", 0)

            self._total_usage["prompt_tokens"] += prompt
            self._total_usage["completion_tokens"] += completion
            self._total_usage["total_tokens"] += total
            self._total_usage["cache_read_tokens"] += cache_read
            self._total_usage["cache_creation_tokens"] += cache_creation

    async def _finalize_turn_messages(self) -> None:
        """Finalize messages at end of turn."""
        # Add assistant message with tool calls and/or text
        if self._current_assistant_text or self._current_tool_calls:
            assistant_msg: Dict[str, Any] = {"role": "assistant"}

            if self._current_assistant_text:
                assistant_msg["content"] = self._current_assistant_text

            if self._current_tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": str(tc["args"]),
                        },
                    }
                    for tc in self._current_tool_calls
                ]

            self._messages.append(assistant_msg)

        # Add tool result messages
        for tool_id in [tc["id"] for tc in self._current_tool_calls]:
            if tool_id in self._pending_tool_results:
                self._messages.append(self._pending_tool_results[tool_id])

        # Process messages through context middleware (historical offload)
        ctx_mw = self._context_middleware
        if ctx_mw is not None:
            self._messages = await ctx_mw.after_assistant_response(self._messages)

    def _normalize_event(self, event: Any) -> Optional[AgentEvent]:
        """Normalize vel event to CLI event format.

        vel yields event.to_dict() which converts to camelCase keys:
        - toolName (not tool_name)
        - toolCallId (not tool_call_id)
        - errorText (not error)
        """
        # Events from vel are dicts (from event.to_dict())
        if not isinstance(event, dict):
            # If somehow we get an object, convert it
            if hasattr(event, 'to_dict'):
                event = event.to_dict()
            else:
                return None

        event_type = event.get("type", "")

        if event_type == "text-delta":
            return AgentEvent(
                type=EventType.TEXT_DELTA,
                data={"delta": event.get("delta", "")},
            )
        elif event_type == "error":
            # ErrorEvent dict uses 'errorText' key
            return AgentEvent(
                type=EventType.ERROR,
                data={"error": event.get("errorText", event.get("error", "Unknown error"))},
            )
        elif event_type == "tool-input-available":
            # Tool is about to be called - check permissions
            # Dict keys from to_dict(): toolCallId, toolName, input
            tool_id = event.get("toolCallId", "")
            tool_name = event.get("toolName", "unknown")
            tool_args = event.get("input", {})

            # Check permission
            permission = self.check_tool_permission(tool_name, tool_args)

            if permission == "allow":
                # Auto-approved - show as normal tool call
                return AgentEvent(
                    type=EventType.TOOL_CALL,
                    data={
                        "id": tool_id,
                        "name": tool_name,
                        "args": tool_args,
                        "approved": True,
                    },
                )
            elif permission == "deny":
                # Denied - show as denied tool call
                return AgentEvent(
                    type=EventType.TOOL_CALL,
                    data={
                        "id": tool_id,
                        "name": tool_name,
                        "args": tool_args,
                        "denied": True,
                    },
                )
            else:
                # Needs approval - emit approval required event
                return AgentEvent(
                    type=EventType.APPROVAL_REQUIRED,
                    data={
                        "id": tool_id,
                        "name": tool_name,
                        "args": tool_args,
                    },
                )
        elif event_type == "tool-output-available":
            # ToolOutputAvailableEvent dict has: toolCallId, output (no toolName)
            return AgentEvent(
                type=EventType.TOOL_RESULT,
                data={
                    "id": event.get("toolCallId", ""),
                    "result": event.get("output", {}),
                },
            )
        elif event_type == "response-metadata":
            # Response metadata with token usage
            # Handle both naming conventions:
            # - OpenAI: inputTokens, outputTokens, totalTokens
            # - Anthropic: promptTokens, completionTokens, totalTokens
            usage = event.get("usage", {})
            prompt = usage.get("promptTokens", 0) or usage.get("inputTokens", 0)
            completion = usage.get("completionTokens", 0) or usage.get("outputTokens", 0)
            total = usage.get("totalTokens", 0)
            return AgentEvent(
                type=EventType.RESPONSE_METADATA,
                data={
                    "model_id": event.get("modelId", ""),
                    "usage": {
                        "prompt_tokens": prompt,
                        "completion_tokens": completion,
                        "total_tokens": total,
                    },
                },
            )
        # Ignore control events (start, finish, finish-step)

        return None

    def approve_tool(self, tool_id: str, approved: bool = True) -> None:
        """Approve or deny a pending tool call."""
        self.approval_handler.resolve(tool_id, approved)
        # Resolve pending future if exists
        if tool_id in self._pending_approvals:
            future = self._pending_approvals.pop(tool_id)
            if not future.done():
                future.set_result(approved)

    def grant_permission(
        self,
        tool_name: str,
        args: Optional[Dict[str, Any]] = None,
        always: bool = False,
    ) -> None:
        """
        Grant permission for a tool.

        Args:
            tool_name: Name of the tool
            args: Optional args to include in pattern
            always: If True, save to settings.local.json
        """
        if always:
            # Create pattern for this tool
            pattern = tool_name
            self._permissions.add_allow(pattern)
            self.config.save_permissions(self._permissions)

    def deny_permission(
        self,
        tool_name: str,
        args: Optional[Dict[str, Any]] = None,
        always: bool = False,
    ) -> None:
        """
        Deny permission for a tool.

        Args:
            tool_name: Name of the tool
            args: Optional args to include in pattern
            always: If True, save to settings.local.json
        """
        if always:
            pattern = tool_name
            self._permissions.add_deny(pattern)
            self.config.save_permissions(self._permissions)

    def check_tool_permission(
        self,
        tool_name: str,
        args: Dict[str, Any],
    ) -> Optional[str]:
        """
        Check permission for a tool call.

        Returns:
            "allow", "deny", "ask", or None
        """
        # Check built-in auto-approve list first
        if self.approval_handler.should_auto_approve(tool_name):
            return "allow"

        if self.approval_handler.should_deny(tool_name):
            return "deny"

        # Check settings.local.json permissions
        return self._permissions.check_permission(tool_name, args)

    @property
    def permissions(self) -> Permissions:
        """Get current permissions."""
        return self._permissions

    def reset_session(self) -> None:
        """Reset the session."""
        self._messages.clear()
        self._session_id = str(uuid.uuid4())[:8]
        self.approval_handler.clear_pending()

        # Reset tracking state
        self._current_assistant_text = ""
        self._current_tool_calls = []
        self._pending_tool_results = {}
        self._total_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
        }

    def get_message_history(self) -> List[Dict[str, Any]]:
        """Get message history including tool calls and results."""
        return self._messages.copy()

    def get_api_usage(self) -> Dict[str, int]:
        """Get cumulative token usage as reported by the API."""
        return self._total_usage.copy()


def create_cli_agent(
    config: Optional[Config] = None,
    model: Optional[Union[ModelSettings, Dict[str, str]]] = None,
) -> AgentRunner:
    """
    Create an agent runner for CLI usage.

    Args:
        config: CLI configuration
        model: Model settings override

    Returns:
        Configured AgentRunner
    """
    from valis_cli.config import get_config

    if config is None:
        config = get_config()

    if model is not None:
        if isinstance(model, dict):
            config.model = ModelSettings.from_dict(model)
        else:
            config.model = model

    return AgentRunner(config=config)


async def run_single_turn(
    prompt: str,
    config: Optional[Config] = None,
) -> str:
    """
    Run a single turn conversation (non-interactive).

    Args:
        prompt: User prompt
        config: CLI configuration

    Returns:
        Agent response as string
    """
    runner = create_cli_agent(config=config)

    response_parts = []

    async for event in runner.run(prompt):
        if event.type == EventType.TEXT_DELTA:
            response_parts.append(event.data.get("delta", ""))
        elif event.type == EventType.ERROR:
            raise RuntimeError(event.data.get("error", "Unknown error"))

    return "".join(response_parts)
