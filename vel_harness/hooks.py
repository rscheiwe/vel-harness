"""
Vel Harness Hooks - Control hooks for tool execution.

Provides Agent SDK-compatible control hooks that can modify or block
tool calls, unlike vel's observability-only hooks.

Key concepts:
- HookResult: allow/deny/modify decision from a hook
- HookMatcher: matches tool names via regex, dispatches to handler
- HookEngine: orchestrates hook execution with timeout support
- Pre-tool hooks can block or modify tool input (first deny wins)
- Post-tool hooks are informational (cannot modify output)

Usage:
    from vel_harness.hooks import HookEngine, HookMatcher, HookResult

    async def block_writes(event):
        if "secret" in str(event.tool_input):
            return HookResult(decision="deny", reason="Contains secrets")
        return HookResult(decision="allow")

    engine = HookEngine(hooks={
        "pre_tool_use": [
            HookMatcher(matcher="write_file|edit_file", handler=block_writes),
        ],
    })
"""

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Literal, Optional, Union

logger = logging.getLogger(__name__)


# --- Hook Event Types ---

HookEvent = Literal[
    "pre_tool_use",
    "post_tool_use",
    "post_tool_use_failure",
    "pre_step",
    "post_step",
    "on_stop",
]


@dataclass
class PreToolUseEvent:
    """Event emitted before a tool is executed."""

    tool_name: str
    tool_input: Dict[str, Any]
    tool_call_id: str = ""
    session_id: str = ""
    step: int = 0


@dataclass
class PostToolUseEvent:
    """Event emitted after a tool executes successfully."""

    tool_name: str
    tool_input: Dict[str, Any]
    tool_output: Any = None
    tool_call_id: str = ""
    session_id: str = ""
    step: int = 0
    duration_ms: float = 0


@dataclass
class PostToolUseFailureEvent:
    """Event emitted when a tool execution fails."""

    tool_name: str
    tool_input: Dict[str, Any]
    error: str = ""
    tool_call_id: str = ""
    session_id: str = ""
    step: int = 0
    duration_ms: float = 0


# --- Hook Results ---


@dataclass
class HookResult:
    """Result from a control hook.

    Decisions:
    - "allow": Tool executes normally
    - "deny": Tool is blocked, error returned to agent
    - "modify": Tool executes with updated_input
    """

    decision: Literal["allow", "deny", "modify"] = "allow"
    updated_input: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None


# --- Hook Matcher ---


@dataclass
class HookMatcher:
    """Matches tool names via regex and dispatches to handler.

    Args:
        matcher: Regex pattern for tool names. None matches all tools.
                 Examples: "write_file|edit_file", "execute.*", None
        handler: Async callable (event) -> HookResult | None
                 Return None or HookResult(decision="allow") to allow.
        timeout: Max seconds to wait for handler. Default 30s.
    """

    matcher: Optional[str] = None
    handler: Optional[Callable] = None
    timeout: float = 30.0

    def matches(self, tool_name: str) -> bool:
        """Check if this matcher applies to the given tool name."""
        if self.matcher is None:
            return True
        try:
            return bool(re.fullmatch(self.matcher, tool_name))
        except re.error:
            logger.warning(f"Invalid hook matcher regex: {self.matcher}")
            return False


# --- Hook Engine ---


class HookEngine:
    """Orchestrates hook execution with matcher-based dispatch.

    Supports multiple matchers per event type. For pre-tool hooks,
    first deny wins — if any matcher returns deny, the tool is blocked.

    Example:
        engine = HookEngine(hooks={
            "pre_tool_use": [
                HookMatcher(matcher="write_file", handler=audit_writes),
                HookMatcher(matcher=None, handler=log_all_tools),
            ],
            "post_tool_use": [
                HookMatcher(handler=track_duration),
            ],
        })
    """

    def __init__(
        self,
        hooks: Optional[Dict[str, List[HookMatcher]]] = None,
    ):
        self._hooks: Dict[str, List[HookMatcher]] = hooks or {}

    @property
    def hooks(self) -> Dict[str, List[HookMatcher]]:
        """Get registered hooks."""
        return self._hooks

    def has_hooks(self, event_type: str) -> bool:
        """Check if any hooks are registered for an event type."""
        return bool(self._hooks.get(event_type))

    async def run_pre_tool_hooks(self, event: PreToolUseEvent) -> HookResult:
        """Run pre-tool-use hooks. First deny wins.

        Returns:
            Combined HookResult. If any matcher denies, returns deny.
            If any matcher modifies (and none deny), returns the last modify.
            Otherwise returns allow.
        """
        matchers = self._hooks.get("pre_tool_use", [])
        if not matchers:
            return HookResult(decision="allow")

        last_modify: Optional[HookResult] = None

        for matcher in matchers:
            if not matcher.matches(event.tool_name):
                continue
            if matcher.handler is None:
                continue

            result = await self._invoke_handler(matcher, event)
            if result is None:
                continue

            if result.decision == "deny":
                return result
            elif result.decision == "modify" and result.updated_input is not None:
                last_modify = result
                # Apply modification for subsequent hooks to see
                event.tool_input = result.updated_input

        if last_modify is not None:
            return last_modify

        return HookResult(decision="allow")

    async def run_post_tool_hooks(self, event: PostToolUseEvent) -> None:
        """Run post-tool-use hooks (informational, no return value)."""
        matchers = self._hooks.get("post_tool_use", [])
        for matcher in matchers:
            if not matcher.matches(event.tool_name):
                continue
            if matcher.handler is None:
                continue
            await self._invoke_handler(matcher, event)

    async def run_post_tool_failure_hooks(
        self, event: PostToolUseFailureEvent
    ) -> None:
        """Run post-tool-use-failure hooks (informational)."""
        matchers = self._hooks.get("post_tool_use_failure", [])
        for matcher in matchers:
            if not matcher.matches(event.tool_name):
                continue
            if matcher.handler is None:
                continue
            await self._invoke_handler(matcher, event)

    async def _invoke_handler(
        self,
        matcher: HookMatcher,
        event: Any,
    ) -> Optional[HookResult]:
        """Invoke a handler with timeout protection."""
        try:
            if asyncio.iscoroutinefunction(matcher.handler):
                result = await asyncio.wait_for(
                    matcher.handler(event),
                    timeout=matcher.timeout,
                )
            else:
                result = matcher.handler(event)

            if result is None:
                return None
            if isinstance(result, HookResult):
                return result
            # Non-HookResult return treated as allow
            return None
        except asyncio.TimeoutError:
            logger.warning(
                f"Hook timed out after {matcher.timeout}s for tool "
                f"{getattr(event, 'tool_name', '?')}"
            )
            return HookResult(
                decision="deny",
                reason=f"Hook timed out after {matcher.timeout}s",
            )
        except Exception as e:
            logger.warning(
                f"Hook raised exception for tool "
                f"{getattr(event, 'tool_name', '?')}: {e}"
            )
            # Hook errors don't block execution by default
            return None

    def add_hooks(self, event_type: str, matchers: List[HookMatcher]) -> None:
        """Add additional hook matchers to an event type."""
        if event_type not in self._hooks:
            self._hooks[event_type] = []
        self._hooks[event_type].extend(matchers)


# --- Built-in Sandbox Enforcement Hook ---


def create_sandbox_enforcement_hook(
    excluded_commands: List[str],
    allowed_commands: List[str],
    network_allowed_hosts: List[str],
    network_enabled: bool = False,
) -> HookMatcher:
    """Create a pre_tool_use hook that enforces sandbox settings.

    This hook blocks tool calls that violate sandbox configuration:
    - Commands in excluded_commands are blocked
    - If allowed_commands is non-empty, only those commands are permitted
    - Network access violations (curl/wget to disallowed hosts)

    Args:
        excluded_commands: Commands to block (substring match)
        allowed_commands: If non-empty, only these commands are allowed (substring match)
        network_allowed_hosts: Allowed network hosts (empty = all blocked if network disabled)
        network_enabled: Whether network access is enabled at all

    Returns:
        HookMatcher configured for execute/execute_python tools
    """

    async def sandbox_enforcer(event: PreToolUseEvent) -> HookResult:
        command = event.tool_input.get("command", "")

        # Check excluded commands (substring match)
        for excluded in excluded_commands:
            if excluded in command:
                return HookResult(
                    decision="deny",
                    reason=f"Command contains excluded term: '{excluded}'",
                )

        # Check allowed commands (if set, only these are permitted)
        if allowed_commands:
            is_allowed = any(allowed in command for allowed in allowed_commands)
            if not is_allowed:
                return HookResult(
                    decision="deny",
                    reason=f"Command not in allowed list: {allowed_commands}",
                )

        # Check network access
        if not network_enabled and network_allowed_hosts:
            # Network is disabled but some hosts are allowed — check if command
            # targets an allowed host
            network_commands = ("curl", "wget", "fetch", "http")
            is_network_cmd = any(nc in command for nc in network_commands)
            if is_network_cmd:
                host_allowed = any(host in command for host in network_allowed_hosts)
                if not host_allowed:
                    return HookResult(
                        decision="deny",
                        reason="Network command targets disallowed host",
                    )

        return HookResult(decision="allow")

    return HookMatcher(
        matcher="execute|execute_python",
        handler=sandbox_enforcer,
    )
