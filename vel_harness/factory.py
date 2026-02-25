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

import json
import tempfile
import warnings
import contextvars
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

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
from vel_harness.middleware.local_context import LocalContextMiddleware
from vel_harness.middleware.loop_detection import LoopDetectionMiddleware
from vel_harness.middleware.verification import VerificationMiddleware
from vel_harness.middleware.tracing import TracingMiddleware
from vel_harness.middleware.time_budget import TimeBudgetMiddleware
from vel_harness.middleware.run_guard import RunGuardMiddleware, RunGuardConfig as RuntimeRunGuardConfig
from vel_harness.backends.database import (
    DatabaseBackend,
    DatabaseConfig,
    DatabaseNotAvailableError,
    MockDatabaseBackend,
)
from vel_harness.backends.composite import CompositeBackend, PersistentStoreBackend
from vel_harness.backends.state import StateFilesystemBackend
from vel_harness.backends.real import RealFilesystemBackend
from vel_harness.prompts import compose_system_prompt, compose_agent_prompt
from vel_harness.reasoning_scheduler import (
    ReasoningScheduler,
    ReasoningSchedulerConfig as RuntimeReasoningSchedulerConfig,
)


_active_session_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "vel_harness_active_session_id",
    default="",
)

_TODO_NUDGE_RE = re.compile(
    r"\b(implement|fix|bug|refactor|code|function|test|suite|compile|build|workflow|subagent|parallel)\b",
    flags=re.IGNORECASE,
)

ToolInputRewriter = Callable[
    [str, Dict[str, Any], Optional[str]],
    Union[Dict[str, Any], tuple[Dict[str, Any], Optional[str]], None],
]


def _is_tool_output_failure(result: Any) -> tuple[bool, str, str]:
    """Best-effort failure extraction for non-exception tool outputs."""
    if not isinstance(result, dict):
        return False, "", ""

    status_val = str(result.get("status", "")).strip().lower()
    success_val = result.get("success")
    exit_code = result.get("exit_code")
    stderr = str(result.get("stderr", "") or "")
    error_text = str(result.get("error", "") or "")

    failed = False
    if isinstance(success_val, bool):
        failed = failed or (not success_val)
    if isinstance(exit_code, int):
        failed = failed or (exit_code != 0)
    if status_val in {"error", "failed", "failure"}:
        failed = True

    if not failed:
        return False, "", ""

    if error_text:
        return True, error_text, "ToolOutputError"
    if stderr:
        return True, stderr, "ToolOutputStderr"
    if isinstance(exit_code, int) and exit_code != 0:
        return True, f"Tool exited with non-zero exit_code={exit_code}", "ToolExitCode"
    if isinstance(success_val, bool) and not success_val:
        return True, "Tool reported success=false", "ToolOutputFailure"
    if status_val:
        return True, f"Tool status indicates failure: {status_val}", "ToolOutputStatus"
    return True, "Tool output indicates failure", "ToolOutputFailure"


def _apply_tool_input_rewriters(
    tool_name: str,
    kwargs: Dict[str, Any],
    working_dir: Optional[str],
    rewriters: List[ToolInputRewriter],
) -> tuple[Dict[str, Any], List[str]]:
    """Apply external tool input rewriters in order."""
    if not rewriters:
        return kwargs, []

    current = dict(kwargs)
    reasons: List[str] = []

    for rewriter in rewriters:
        rewritten = rewriter(tool_name, dict(current), working_dir)
        if rewritten is None:
            continue
        if isinstance(rewritten, tuple) and len(rewritten) == 2:
            candidate, reason = rewritten
            if isinstance(candidate, dict):
                current = candidate
            if isinstance(reason, str) and reason.strip():
                reasons.append(reason.strip())
            continue
        if isinstance(rewritten, dict):
            current = rewritten

    return current, reasons


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
        self._reasoning_scheduler = ReasoningScheduler(
            RuntimeReasoningSchedulerConfig(
                enabled=config.reasoning_scheduler.enabled,
                planning_budget_tokens=config.reasoning_scheduler.planning_budget_tokens,
                build_budget_tokens=config.reasoning_scheduler.build_budget_tokens,
                verify_budget_tokens=config.reasoning_scheduler.verify_budget_tokens,
            )
        )

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
    def local_context(self) -> Optional[LocalContextMiddleware]:
        """Get local context middleware."""
        return self._middlewares.get("local_context")  # type: ignore

    @property
    def loop_detection(self) -> Optional[LoopDetectionMiddleware]:
        """Get loop detection middleware."""
        return self._middlewares.get("loop_detection")  # type: ignore

    @property
    def verification(self) -> Optional[VerificationMiddleware]:
        """Get verification middleware."""
        return self._middlewares.get("verification")  # type: ignore

    @property
    def tracing(self) -> Optional[TracingMiddleware]:
        """Get tracing middleware."""
        return self._middlewares.get("tracing")  # type: ignore

    @property
    def time_budget(self) -> Optional[TimeBudgetMiddleware]:
        """Get time budget middleware."""
        return self._middlewares.get("time_budget")  # type: ignore

    @property
    def run_guard(self) -> Optional[RunGuardMiddleware]:
        """Get runtime guard middleware."""
        return self._middlewares.get("run_guard")  # type: ignore

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
        sid = session_id or "default"
        self._process_skill_context(input_text)
        await self._preprocess_context_window(sid)
        if self.time_budget is not None:
            self.time_budget.start(sid)
        if self.run_guard is not None:
            self.run_guard.start(sid, input_text if isinstance(input_text, str) else "")

        run_ctx = None
        if self.tracing is not None:
            run_ctx = self.tracing.start_run(session_id=sid)

        enriched_input = self._inject_local_context(input_text, sid)
        enriched_input = self._apply_time_budget_hint(enriched_input, sid)
        enriched_input = self._apply_run_guard_hint(enriched_input, sid)
        enriched_input = self._apply_todo_hint(enriched_input, sid)
        loop_hint = self._get_loop_hint(sid)
        if loop_hint:
            enriched_input = self._append_hint_to_input(enriched_input, loop_hint)

        if self.time_budget is not None and self.time_budget.should_pivot_to_verify(sid):
            self._apply_reasoning_phase("verify")
        else:
            self._apply_reasoning_phase("build")

        token = _active_session_id.set(sid)
        final_output_preview = ""
        try:
            response = await self._agent.run(
                {"message": enriched_input, **(context or {})},
                session_id=sid,
            )

            response = await self._maybe_verification_followup(
                response=response,
                original_input=input_text,
                session_id=sid,
                context=context,
            )
            final_output_preview = self._preview_response_output(response)
            if self.tracing is not None:
                self.tracing.record(
                    "assistant-final",
                    {"stage": "final", "output_preview": final_output_preview},
                )
        finally:
            _active_session_id.reset(token)
            await self._postprocess_context_window(sid)
            if self.tracing is not None:
                self.tracing.end_run(
                    success=True,
                    data={
                        "run_id": (run_ctx or {}).get("run_id", ""),
                        "final_output_preview": final_output_preview,
                    },
                )

        # In prompted reasoning mode, strip internal thinking tags from
        # non-streaming responses as a safety fallback.
        reasoning_cfg = self._config.reasoning
        if (
            reasoning_cfg is not None
            and getattr(reasoning_cfg, "mode", None) == "prompted"
            and (hasattr(response, "content") or isinstance(response, str))
        ):
            from vel_harness.reasoning import PromptedReasoningParser

            parser = PromptedReasoningParser(reasoning_cfg)
            response_text = response.content if hasattr(response, "content") else response
            events = parser.feed(response_text or "") + parser.finish()
            text = "".join(
                e.get("delta", "")
                for e in events
                if isinstance(e, dict) and e.get("type") == "text-delta"
            )
            if hasattr(response, "content"):
                response.content = text or response.content
            else:
                response = text or response

        return response

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
        sid = session_id or "default"
        self._process_skill_context(input_text)
        await self._preprocess_context_window(sid)
        if self.time_budget is not None:
            self.time_budget.start(sid)
        if self.run_guard is not None:
            self.run_guard.start(sid, input_text if isinstance(input_text, str) else "")

        reasoning_cfg = self._config.reasoning
        parser = None
        if reasoning_cfg is not None and getattr(reasoning_cfg, "mode", None) == "prompted":
            from vel_harness.reasoning import PromptedReasoningParser

            parser = PromptedReasoningParser(reasoning_cfg)

        run_ctx = None
        if self.tracing is not None:
            run_ctx = self.tracing.start_run(session_id=sid)

        enriched_input = self._inject_local_context(input_text, sid)
        enriched_input = self._apply_time_budget_hint(enriched_input, sid)
        enriched_input = self._apply_run_guard_hint(enriched_input, sid)
        enriched_input = self._apply_todo_hint(enriched_input, sid)
        loop_hint = self._get_loop_hint(sid)
        if loop_hint:
            enriched_input = self._append_hint_to_input(enriched_input, loop_hint)

        if self.time_budget is not None and self.time_budget.should_pivot_to_verify(sid):
            self._apply_reasoning_phase("verify")
        else:
            self._apply_reasoning_phase("build")

        # Run underlying agent with streaming
        # Use 'message' key which vel expects (not 'text')
        stream_finished = False
        buffered_events: List[Any] = []
        final_output_chunks: List[str] = []
        budget_hint_emitted = False

        def _capture_chunk(ev: Any) -> None:
            chunk = self._extract_stream_text_chunk(ev)
            if not chunk:
                return
            final_output_chunks.append(chunk)

        try:
            token = _active_session_id.set(sid)
            async for event in self._agent.run_stream(
                {"message": enriched_input, **(context or {})},
                session_id=sid,
            ):
                if isinstance(event, dict):
                    event = self._process_context_tool_event(event)

                if parser is not None and isinstance(event, dict):
                    event_type = event.get("type")
                    if event_type == "text-delta":
                        deltas = parser.feed(event.get("delta", ""))
                        for parsed_event in self._filter_reasoning_events(deltas, reasoning_cfg):
                            _capture_chunk(parsed_event)
                            if self.tracing is not None and isinstance(parsed_event, dict):
                                self.tracing.record_stream_event(sid, parsed_event)
                            buffered_events.append(parsed_event)
                        continue
                    if event_type == "finish":
                        stream_finished = True
                        trailing = parser.finish()
                        for parsed_event in self._filter_reasoning_events(trailing, reasoning_cfg):
                            _capture_chunk(parsed_event)
                            if self.tracing is not None and isinstance(parsed_event, dict):
                                self.tracing.record_stream_event(sid, parsed_event)
                            buffered_events.append(parsed_event)
                        if self.tracing is not None and isinstance(event, dict):
                            self.tracing.record_stream_event(sid, event)
                        buffered_events.append(event)
                        continue

                if self.tracing is not None and isinstance(event, dict):
                    self.tracing.record_stream_event(sid, event)
                _capture_chunk(event)
                buffered_events.append(event)
                if not budget_hint_emitted and self.time_budget is not None:
                    hint = self.time_budget.get_runtime_hint(sid)
                    if hint:
                        budget_hint_emitted = True
                        if self.tracing is not None:
                            self.tracing.record("time-budget-hint", {"session_id": sid, "hint": hint})
                        buffered_events.append(
                            {
                                "type": "status",
                                "status": "time-budget",
                                "message": hint,
                            }
                        )

            if parser is not None and not stream_finished:
                trailing = parser.finish()
                for parsed_event in self._filter_reasoning_events(trailing, reasoning_cfg):
                    _capture_chunk(parsed_event)
                    if self.tracing is not None and isinstance(parsed_event, dict):
                        self.tracing.record_stream_event(sid, parsed_event)
                    buffered_events.append(parsed_event)

            followup_needed = False
            followup_reason = ""
            if self.verification is not None and isinstance(input_text, str):
                followup_needed, followup_reason = self.verification.should_followup(
                    sid,
                    user_message=input_text,
                )
            rg_followup_needed = False
            rg_followup_reason = ""
            if self.run_guard is not None and isinstance(input_text, str):
                rg_followup_needed, rg_followup_reason = self.run_guard.should_force_followup(
                    session_id=sid,
                    user_message=input_text,
                    response="".join(final_output_chunks),
                )

            if followup_needed or rg_followup_needed:
                if followup_needed and self.verification is not None:
                    self.verification.mark_followup_used(sid)
                if self.tracing is not None:
                    self.tracing.record(
                        "verification-followup-required",
                        {
                            "reason": followup_reason if followup_needed else rg_followup_reason,
                            "session_id": sid,
                            "source": "verification" if followup_needed else "run_guard",
                        },
                    )
                yield {
                    "type": "status",
                    "status": "verification-required",
                    "message": "Running verification pass before finalizing.",
                }

                self._apply_reasoning_phase("verify")
                if followup_needed and self.verification is not None:
                    followup_prompt = self.verification.build_followup_prompt(followup_reason)
                else:
                    followup_prompt = (
                        self.run_guard.build_followup_prompt(rg_followup_reason)
                        if self.run_guard is not None
                        else "Run an additional verification pass."
                    )
                async for event in self._agent.run_stream(
                    {"message": followup_prompt, **(context or {})},
                    session_id=sid,
                ):
                    if isinstance(event, dict):
                        event = self._process_context_tool_event(event)
                    if self.tracing is not None and isinstance(event, dict):
                        self.tracing.record_stream_event(sid, event)
                    _capture_chunk(event)
                    yield event
            else:
                for event in buffered_events:
                    yield event
        finally:
            _active_session_id.reset(token)
            await self._postprocess_context_window(sid)
            if self.tracing is not None:
                self.tracing.end_run(
                    success=True,
                    data={
                        "run_id": (run_ctx or {}).get("run_id", ""),
                        "final_output_preview": "".join(final_output_chunks)[:6000],
                    },
                )

    def _process_skill_context(
        self,
        input_text: Union[str, List[Dict[str, Any]]],
    ) -> None:
        """Process user input for skill auto-activation."""
        if not self.skills:
            return

        if isinstance(input_text, str):
            self.skills.process_context(input_text)
            return

        text_parts = [p.get("text", "") for p in input_text if p.get("type") == "text"]
        self.skills.process_context(" ".join(text_parts))

    def _preview_response_output(self, response: Any, max_chars: int = 6000) -> str:
        """Extract and truncate a response text preview for tracing."""
        text = ""
        if response is None:
            return text
        if hasattr(response, "content"):
            text = str(getattr(response, "content") or "")
        elif isinstance(response, dict):
            text = str(response.get("content", "") or "")
        else:
            text = str(response)
        if len(text) <= max_chars:
            return text
        return f"{text[:max_chars]}...<truncated>"

    def _extract_stream_text_chunk(self, event: Any) -> str:
        """Extract text content from a streamed event for final output preview."""
        if isinstance(event, dict):
            if event.get("type") == "text-delta":
                return str(event.get("delta", ""))
            if event.get("type") == "assistant-message":
                return str(event.get("content", ""))
            if "content" in event and isinstance(event.get("content"), str):
                return str(event.get("content", ""))
            return ""
        if hasattr(event, "content"):
            return str(getattr(event, "content") or "")
        return ""

    def _process_context_tool_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Apply context tool-result truncation to stream events."""
        if self.context is None:
            return event

        if event.get("type") != "tool-output-available":
            return event

        output = event.get("output")
        if output is None:
            return event

        if isinstance(output, str):
            output_text = output
        else:
            try:
                output_text = json.dumps(output, default=str)
            except Exception:
                output_text = str(output)

        truncated = self.context.process_tool_result(
            output_text,
            tool_name=str(event.get("toolName", "unknown")),
            tool_call_id=str(event.get("toolCallId", "")),
        )

        if truncated != output_text:
            return {**event, "output": truncated}
        return event

    async def _preprocess_context_window(self, session_id: Optional[str]) -> None:
        """Apply proactive context compaction before a run."""
        if self.context is None or not session_id:
            return

        ctxmgr = getattr(self._agent, "ctxmgr", None)
        if ctxmgr is None or not hasattr(ctxmgr, "get_session_context"):
            return

        try:
            messages = ctxmgr.get_session_context(session_id)
            processed = await self.context.process_messages(
                messages,
                model=self._config.model.model,
                session_id=session_id,
            )
            if hasattr(ctxmgr, "set_session_context"):
                ctxmgr.set_session_context(session_id, processed)
        except Exception:
            pass

    async def _postprocess_context_window(self, session_id: Optional[str]) -> None:
        """Evict historical tool outputs after a run."""
        if self.context is None or not session_id:
            return

        ctxmgr = getattr(self._agent, "ctxmgr", None)
        if ctxmgr is None or not hasattr(ctxmgr, "get_session_context"):
            return

        try:
            messages = ctxmgr.get_session_context(session_id)
            processed = await self.context.after_assistant_response(messages)
            if hasattr(ctxmgr, "set_session_context"):
                ctxmgr.set_session_context(session_id, processed)
        except Exception:
            pass

    def _filter_reasoning_events(
        self,
        events: List[Dict[str, Any]],
        reasoning_cfg: Any,
    ) -> List[Dict[str, Any]]:
        """Filter reasoning events based on stream_reasoning setting."""
        if getattr(reasoning_cfg, "stream_reasoning", True):
            return events
        return [e for e in events if e.get("type") == "text-delta"]

    def _inject_local_context(
        self,
        input_text: Union[str, List[Dict[str, Any]]],
        session_id: str,
    ) -> Union[str, List[Dict[str, Any]]]:
        """Inject deterministic local context summary once per session."""
        if self.local_context is None:
            return input_text
        if self.local_context.has_injected(session_id):
            return input_text

        summary = self.local_context.build_injection(session_id)
        if not summary:
            return input_text
        if self.tracing is not None:
            self.tracing.record("local-context-injected", {"session_id": session_id})

        prefix = f"{summary}\n\nUse this environment context when planning and verification.\n\n"
        if isinstance(input_text, str):
            return prefix + input_text
        return [{"type": "text", "text": prefix}] + input_text

    def _get_loop_hint(self, session_id: str) -> Optional[str]:
        if self.loop_detection is None:
            return None
        hint = self.loop_detection.get_recovery_hint(session_id)
        if hint and self.tracing is not None:
            self.tracing.record("loop-recovery-hint", {"session_id": session_id, "hint": hint})
        return hint

    def _append_hint_to_input(
        self,
        input_text: Union[str, List[Dict[str, Any]]],
        hint: str,
    ) -> Union[str, List[Dict[str, Any]]]:
        if isinstance(input_text, str):
            return f"{input_text}\n\n[Loop recovery hint]\n{hint}"
        return input_text + [{"type": "text", "text": f"\n\n[Loop recovery hint]\n{hint}"}]

    def _apply_time_budget_hint(
        self,
        input_text: Union[str, List[Dict[str, Any]]],
        session_id: str,
    ) -> Union[str, List[Dict[str, Any]]]:
        if self.time_budget is None:
            return input_text
        hint = self.time_budget.get_runtime_hint(session_id)
        if not hint:
            return input_text
        if self.tracing is not None:
            self.tracing.record(
                "time-budget-hint",
                {"session_id": session_id, "hint": hint},
            )
        if isinstance(input_text, str):
            return f"{input_text}\n\n[Time budget hint]\n{hint}"
        return input_text + [{"type": "text", "text": f"\n\n[Time budget hint]\n{hint}"}]

    def _apply_run_guard_hint(
        self,
        input_text: Union[str, List[Dict[str, Any]]],
        session_id: str,
    ) -> Union[str, List[Dict[str, Any]]]:
        if self.run_guard is None:
            return input_text
        hint = self.run_guard.get_runtime_hint(session_id)
        if not hint:
            return input_text
        if self.tracing is not None:
            self.tracing.record("run-guard-hint", {"session_id": session_id, "hint": hint})
        if isinstance(input_text, str):
            return f"{input_text}\n\n[RunGuard hint]\n{hint}"
        return input_text + [{"type": "text", "text": f"\n\n[RunGuard hint]\n{hint}"}]

    def _apply_todo_hint(
        self,
        input_text: Union[str, List[Dict[str, Any]]],
        session_id: str,
    ) -> Union[str, List[Dict[str, Any]]]:
        if self.planning is None:
            return input_text
        if not isinstance(input_text, str):
            return input_text
        if self.planning.todo_list.items:
            return input_text
        if not _TODO_NUDGE_RE.search(input_text):
            return input_text
        hint = (
            "Before substantial implementation or multi-step delegation, call write_todos "
            "to create a concise 3-6 step plan, then keep it updated with completed/in_progress."
        )
        if self.tracing is not None:
            self.tracing.record("planning-todo-hint", {"session_id": session_id, "hint": hint})
        return f"{input_text}\n\n[Planning hint]\n{hint}"

    def _apply_reasoning_phase(self, phase: str) -> None:
        """Apply phase-specific reasoning budget when using native mode."""
        base = self._config.reasoning
        scheduled = self._reasoning_scheduler.for_phase(base, phase)
        if scheduled is None or scheduled.mode != "native":
            return
        budget = scheduled.budget_tokens or 10000
        self._agent.generation_config = {
            "thinking": {"type": "enabled", "budget_tokens": budget},
        }
        if self.tracing is not None:
            self.tracing.record(
                "reasoning-phase-applied",
                {"phase": phase, "budget_tokens": budget},
            )

    async def _maybe_verification_followup(
        self,
        response: Any,
        original_input: Union[str, List[Dict[str, Any]]],
        session_id: str,
        context: Optional[Dict[str, Any]],
    ) -> Any:
        """Run a forced verification turn before final completion when needed."""
        if self.verification is None or not isinstance(original_input, str):
            return response

        should_followup, reason = self.verification.should_followup(session_id, original_input)
        rg_should_followup = False
        rg_reason = ""
        if self.run_guard is not None:
            rg_should_followup, rg_reason = self.run_guard.should_force_followup(
                session_id=session_id,
                user_message=original_input,
                response=response,
            )
        if not should_followup and not rg_should_followup:
            return response

        if should_followup:
            self.verification.mark_followup_used(session_id)
        if self.tracing is not None:
            self.tracing.record(
                "verification-followup-required",
                {
                    "reason": reason if should_followup else rg_reason,
                    "session_id": session_id,
                    "source": "verification" if should_followup else "run_guard",
                },
            )

        self._apply_reasoning_phase("verify")
        if should_followup:
            followup_prompt = self.verification.build_followup_prompt(reason)
        else:
            followup_prompt = self.run_guard.build_followup_prompt(rg_reason) if self.run_guard else ""
        followup = await self._agent.run(
            {"message": followup_prompt, **(context or {})},
            session_id=session_id,
        )
        return followup


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

    if working_dir is not None and not agent_config.sandbox.working_dir:
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
            fs_base_path = working_dir or agent_config.sandbox.working_dir
            real_backend = RealFilesystemBackend(base_path=fs_base_path)
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

        # Prefer real database backend; fall back to mock when unavailable.
        try:
            db_backend = DatabaseBackend(
                config=db_config,
                readonly=agent_config.database.readonly,
            )
        except (DatabaseNotAvailableError, Exception):
            db_backend = MockDatabaseBackend(readonly=agent_config.database.readonly)
        database_mw = DatabaseMiddleware(
            backend=db_backend,
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
            discovery_mode=agent_config.skills.discovery_mode,
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
    memory_startup_context = ""
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
            agents_md_path=agent_config.memory.agents_md_path or "/memories/AGENTS.md",
        )
        memory_mw.set_filesystem(filesystem_backend)
        memory_startup_context = memory_mw.get_startup_context(filesystem_backend)
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

    # Local context onboarding middleware
    if agent_config.local_context.enabled:
        local_ctx_mw = LocalContextMiddleware(
            working_dir=agent_config.sandbox.working_dir or working_dir or str(Path.cwd()),
            enabled=agent_config.local_context.enabled,
            max_entries=agent_config.local_context.max_entries,
            max_depth=agent_config.local_context.max_depth,
            detect_tools=agent_config.local_context.detect_tools,
        )
        middlewares["local_context"] = local_ctx_mw

    # Loop detection middleware
    if agent_config.loop_detection.enabled:
        loop_mw = LoopDetectionMiddleware(
            enabled=agent_config.loop_detection.enabled,
            file_edit_threshold=agent_config.loop_detection.file_edit_threshold,
            failure_streak_threshold=agent_config.loop_detection.failure_streak_threshold,
        )
        middlewares["loop_detection"] = loop_mw

    # Verification middleware
    if agent_config.verification.enabled:
        verification_mw = VerificationMiddleware(
            enabled=agent_config.verification.enabled,
            strict=agent_config.verification.strict,
            max_followups=agent_config.verification.max_followups,
        )
        middlewares["verification"] = verification_mw

    # Tracing middleware
    if agent_config.tracing.enabled:
        tracing_mw = TracingMiddleware(
            enabled=agent_config.tracing.enabled,
            emit_langfuse=agent_config.tracing.emit_langfuse,
            telemetry_mode=agent_config.tracing.telemetry_mode,
        )
        middlewares["tracing"] = tracing_mw

    # Time budget middleware
    if agent_config.time_budget.enabled:
        time_budget_mw = TimeBudgetMiddleware(
            enabled=agent_config.time_budget.enabled,
            soft_limit_seconds=agent_config.time_budget.soft_limit_seconds,
            hard_limit_seconds=agent_config.time_budget.hard_limit_seconds,
        )
        middlewares["time_budget"] = time_budget_mw

    # Run guard middleware
    if agent_config.run_guard.enabled:
        run_guard_mw = RunGuardMiddleware(
            RuntimeRunGuardConfig(
                enabled=agent_config.run_guard.enabled,
                max_tool_calls_total=agent_config.run_guard.max_tool_calls_total,
                max_tool_calls_per_tool=agent_config.run_guard.max_tool_calls_per_tool,
                max_same_tool_input_repeats=agent_config.run_guard.max_same_tool_input_repeats,
                max_failure_streak=agent_config.run_guard.max_failure_streak,
                max_subagent_rounds=agent_config.run_guard.max_subagent_rounds,
                max_parallel_subagents=agent_config.run_guard.max_parallel_subagents,
                require_verification_before_done=agent_config.run_guard.require_verification_before_done,
                verification_tool_names=agent_config.run_guard.verification_tool_names,
                completion_required_paths=agent_config.run_guard.completion_required_paths,
                completion_required_patterns=agent_config.run_guard.completion_required_patterns,
                max_discovery_rounds_by_class=agent_config.run_guard.max_discovery_rounds_by_class,
                max_repeated_identical_execute=agent_config.run_guard.max_repeated_identical_execute,
                enforce_query_evidence_for_numeric_claims=(
                    agent_config.run_guard.enforce_query_evidence_for_numeric_claims
                ),
            )
        )
        middlewares["run_guard"] = run_guard_mw

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

    if memory_startup_context:
        prompt_segments.append(memory_startup_context)

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

    # Provide tool inventory to subagents for per-agent allowlist filtering.
    if "subagents" in middlewares:
        subagent_tools = [t for t in all_tools if t.name not in {
            "spawn_subagent",
            "spawn_parallel",
            "wait_subagent",
            "wait_all_subagents",
            "get_subagent_result",
            "list_subagents",
            "cancel_subagent",
        }]
        middlewares["subagents"].set_available_tools(subagent_tools)  # type: ignore[attr-defined]

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

    # Wrap tools with middleware observers (tracing/loop-detection/verification)
    tool_observers = [
        mw for mw in (
            middlewares.get("tracing"),
            middlewares.get("loop_detection"),
            middlewares.get("verification"),
            middlewares.get("run_guard"),
        )
        if mw is not None
    ]
    if tool_observers:
        import asyncio as _asyncio
        import time as _time
        tool_input_rewriters: List[ToolInputRewriter] = list(
            getattr(agent_config, "tool_input_rewriters", []) or []
        )

        def _notify_observers(tool: ToolSpec) -> ToolSpec:
            original_handler = tool._handler

            async def observed_handler(**kwargs: Any) -> Any:
                session_id = _active_session_id.get()
                effective_kwargs, rewrite_reasons = _apply_tool_input_rewriters(
                    tool_name=tool.name,
                    kwargs=kwargs,
                    working_dir=agent_config.sandbox.working_dir,
                    rewriters=tool_input_rewriters,
                )
                for obs in tool_observers:
                    if hasattr(obs, "allow_tool_call"):
                        allowed, reason = obs.allow_tool_call(session_id, tool.name, effective_kwargs)
                        if not allowed:
                            if hasattr(obs, "on_tool_failure"):
                                obs.on_tool_failure(session_id, tool.name, effective_kwargs)
                            return {"error": reason}
                for obs in tool_observers:
                    if hasattr(obs, "record_tool_start"):
                        obs.record_tool_start(tool.name, effective_kwargs)
                    if hasattr(obs, "on_tool_start"):
                        obs.on_tool_start(session_id, tool.name, effective_kwargs)

                started = _time.time()
                try:
                    if rewrite_reasons:
                        for rewrite_reason in rewrite_reasons:
                            for obs in tool_observers:
                                if hasattr(obs, "record"):
                                    try:
                                        obs.record(  # type: ignore[attr-defined]
                                            "tool-input-rewritten",
                                            {
                                                "tool_name": tool.name,
                                                "reason": rewrite_reason,
                                            },
                                        )
                                    except Exception:
                                        pass

                    if _asyncio.iscoroutinefunction(original_handler):
                        result = await original_handler(**effective_kwargs)
                    else:
                        result = original_handler(**effective_kwargs)

                    duration_ms = (_time.time() - started) * 1000
                    output_failed, output_error, output_error_type = _is_tool_output_failure(result)
                    if output_failed:
                        for obs in tool_observers:
                            if hasattr(obs, "record_tool_failure"):
                                obs.record_tool_failure(
                                    tool.name,
                                    effective_kwargs,
                                    output_error,
                                    duration_ms,
                                    error_type=output_error_type,
                                )
                            if hasattr(obs, "on_tool_failure"):
                                obs.on_tool_failure(session_id, tool.name, effective_kwargs)
                        return result

                    for obs in tool_observers:
                        if hasattr(obs, "record_tool_success"):
                            obs.record_tool_success(tool.name, effective_kwargs, duration_ms, result)
                        if hasattr(obs, "on_tool_success"):
                            obs.on_tool_success(session_id, tool.name, effective_kwargs)
                    return result
                except Exception as e:
                    duration_ms = (_time.time() - started) * 1000
                    for obs in tool_observers:
                        if hasattr(obs, "record_tool_failure"):
                            obs.record_tool_failure(
                                tool.name,
                                effective_kwargs,
                                str(e),
                                duration_ms,
                                error_type=e.__class__.__name__,
                            )
                        if hasattr(obs, "on_tool_failure"):
                            obs.on_tool_failure(session_id, tool.name, effective_kwargs)
                    raise

            return ToolSpec.from_function(
                observed_handler,
                name=tool.name,
                description=tool.description,
                input_schema=tool.input_schema,
                output_schema=tool.output_schema,
                category=getattr(tool, "category", None),
                tags=getattr(tool, "tags", None),
            )

        all_tools = [_notify_observers(t) for t in all_tools]

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
