"""
Run guard middleware for deterministic runtime safety controls.

This middleware enforces hard limits that should not rely on prompt compliance:
- Total/per-tool tool call budgets
- Repeated tool-input loop detection
- Failure streak limits
- Subagent delegation limits
- Verification/completion contract checks before finalization
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from vel_harness.middleware.base import BaseMiddleware

_CODING_TASK_RE = re.compile(
    r"\b(implement|fix|bug|refactor|code|function|test|suite|compile|build)\b",
    flags=re.IGNORECASE,
)

def _norm_tool_input(payload: Dict[str, Any]) -> str:
    try:
        return json.dumps(payload, sort_keys=True, default=str)
    except Exception:
        return str(payload)


def _extract_text(response: Any) -> str:
    if response is None:
        return ""
    if hasattr(response, "content"):
        return str(getattr(response, "content") or "")
    return str(response)


@dataclass
class RunGuardConfig:
    """Hard runtime guard configuration."""

    enabled: bool = True
    max_tool_calls_total: int = 60
    max_tool_calls_per_tool: Dict[str, int] = field(default_factory=lambda: {
        "read_file": 30,
        "grep": 20,
        "glob": 20,
        "write_file": 20,
        "edit_file": 30,
        "spawn_subagent": 10,
        "spawn_parallel": 6,
        "run_subagent_workflow": 4,
    })
    max_same_tool_input_repeats: int = 4
    max_failure_streak: int = 6
    max_subagent_rounds: int = 8
    max_parallel_subagents: int = 5
    require_verification_before_done: bool = True
    verification_tool_names: List[str] = field(default_factory=lambda: [
        "execute",
        "execute_python",
        "sql_query",
        "wait_subagent",
        "wait_all_subagents",
    ])
    completion_required_paths: List[str] = field(default_factory=list)
    completion_required_patterns: List[str] = field(default_factory=list)


@dataclass
class _SessionState:
    tool_calls_total: int = 0
    tool_calls_by_name: Dict[str, int] = field(default_factory=dict)
    recent_signature_streak: int = 0
    recent_signature: str = ""
    failure_streak: int = 0
    subagent_rounds: int = 0
    verification_calls: int = 0
    blocked_reason: str = ""


class RunGuardMiddleware(BaseMiddleware):
    """Deterministic runtime guardrail middleware."""

    def __init__(self, config: Optional[RunGuardConfig] = None) -> None:
        self._config = config or RunGuardConfig()
        self._sessions: Dict[str, _SessionState] = {}

    @property
    def config(self) -> RunGuardConfig:
        return self._config

    def get_system_prompt_segment(self) -> str:
        return (
            "## Runtime Guardrails\n"
            "Hard limits are enforced for tool budgets, repeated identical calls, and "
            "failure streaks. If blocked, switch strategy and verify before completion."
        )

    def start(self, session_id: str) -> None:
        self._sessions.setdefault(session_id, _SessionState())

    def _state(self, session_id: str) -> _SessionState:
        if session_id not in self._sessions:
            self._sessions[session_id] = _SessionState()
        return self._sessions[session_id]

    def allow_tool_call(
        self,
        session_id: str,
        tool_name: str,
        tool_input: Dict[str, Any],
    ) -> Tuple[bool, str]:
        if not self._config.enabled:
            return True, ""
        s = self._state(session_id)

        if s.blocked_reason:
            return False, s.blocked_reason

        projected_total = s.tool_calls_total + 1
        if projected_total > self._config.max_tool_calls_total:
            reason = (
                f"RunGuard blocked tool '{tool_name}': total tool-call budget exceeded "
                f"({projected_total}>{self._config.max_tool_calls_total})."
            )
            s.blocked_reason = reason
            return False, reason

        per_tool_cap = self._config.max_tool_calls_per_tool.get(tool_name)
        if per_tool_cap is not None and (s.tool_calls_by_name.get(tool_name, 0) + 1) > per_tool_cap:
            reason = (
                f"RunGuard blocked tool '{tool_name}': per-tool budget exceeded "
                f"({s.tool_calls_by_name.get(tool_name, 0) + 1}>{per_tool_cap})."
            )
            s.blocked_reason = reason
            return False, reason

        sig = f"{tool_name}:{_norm_tool_input(tool_input)}"
        streak = s.recent_signature_streak + 1 if sig == s.recent_signature else 1
        if streak > self._config.max_same_tool_input_repeats:
            reason = (
                f"RunGuard blocked tool '{tool_name}': repeated identical calls detected "
                f"({streak}>{self._config.max_same_tool_input_repeats})."
            )
            s.blocked_reason = reason
            return False, reason

        if tool_name == "spawn_parallel":
            tasks = tool_input.get("tasks", [])
            if isinstance(tasks, list) and len(tasks) > self._config.max_parallel_subagents:
                reason = (
                    f"RunGuard blocked spawn_parallel: requested {len(tasks)} tasks, "
                    f"limit is {self._config.max_parallel_subagents}."
                )
                s.blocked_reason = reason
                return False, reason

        if tool_name in {"spawn_subagent", "spawn_parallel", "run_subagent_workflow"}:
            if (s.subagent_rounds + 1) > self._config.max_subagent_rounds:
                reason = (
                    f"RunGuard blocked subagent delegation: rounds exceeded "
                    f"({s.subagent_rounds + 1}>{self._config.max_subagent_rounds})."
                )
                s.blocked_reason = reason
                return False, reason

        return True, ""

    def on_tool_start(self, session_id: str, tool_name: str, tool_input: Dict[str, Any]) -> None:
        if not self._config.enabled:
            return
        s = self._state(session_id)
        s.tool_calls_total += 1
        s.tool_calls_by_name[tool_name] = s.tool_calls_by_name.get(tool_name, 0) + 1

        sig = f"{tool_name}:{_norm_tool_input(tool_input)}"
        if sig == s.recent_signature:
            s.recent_signature_streak += 1
        else:
            s.recent_signature = sig
            s.recent_signature_streak = 1

        if tool_name in {"spawn_subagent", "spawn_parallel", "run_subagent_workflow"}:
            s.subagent_rounds += 1
        if tool_name in set(self._config.verification_tool_names):
            s.verification_calls += 1

    def on_tool_success(self, session_id: str, tool_name: str, tool_input: Dict[str, Any]) -> None:
        if not self._config.enabled:
            return
        s = self._state(session_id)
        s.failure_streak = 0

    def on_tool_failure(self, session_id: str, tool_name: str, tool_input: Dict[str, Any]) -> None:
        if not self._config.enabled:
            return
        s = self._state(session_id)
        s.failure_streak += 1
        if s.failure_streak > self._config.max_failure_streak:
            s.blocked_reason = (
                f"RunGuard blocked further execution: failure streak exceeded "
                f"({s.failure_streak}>{self._config.max_failure_streak})."
            )

    def should_force_followup(
        self,
        session_id: str,
        user_message: str,
        response: Any,
    ) -> Tuple[bool, str]:
        if not self._config.enabled:
            return False, ""
        s = self._state(session_id)

        if s.blocked_reason:
            return True, s.blocked_reason

        reasons: List[str] = []
        if (
            self._config.require_verification_before_done
            and s.verification_calls == 0
            and _CODING_TASK_RE.search(user_message)
        ):
            reasons.append("No verification/tool-check evidence was recorded for a coding-intent run.")

        for req_path in self._config.completion_required_paths:
            if not Path(req_path).exists():
                reasons.append(f"Required output path missing: {req_path}")

        response_text = _extract_text(response)
        for patt in self._config.completion_required_patterns:
            if not re.search(patt, response_text, flags=re.IGNORECASE):
                reasons.append(f"Response missing required pattern: /{patt}/")

        if reasons:
            return True, " ".join(reasons)
        return False, ""

    def build_followup_prompt(self, reason: str) -> str:
        return (
            "RunGuard enforced an additional verification/fix pass.\n"
            f"Reason: {reason}\n\n"
            "Required now:\n"
            "1. Re-check the original request.\n"
            "2. Run concrete verification steps using available tools.\n"
            "3. If work is multi-step, create/update todos before continuing.\n"
            "4. If multiple independent research tasks remain, prefer spawn_parallel.\n"
            "5. If blocked by limits, pivot strategy and minimize tool usage.\n"
            "6. Return a concise result with explicit verification evidence."
        )

    def get_runtime_hint(self, session_id: str) -> Optional[str]:
        if not self._config.enabled:
            return None
        s = self._state(session_id)
        remaining = self._config.max_tool_calls_total - s.tool_calls_total
        if remaining <= 8:
            return (
                f"RunGuard: only {max(0, remaining)} tool calls left in this run. "
                "Switch to verification/final synthesis."
            )
        return None

    def get_state(self) -> Dict[str, Any]:
        return {
            "config": {
                "enabled": self._config.enabled,
                "max_tool_calls_total": self._config.max_tool_calls_total,
                "max_tool_calls_per_tool": self._config.max_tool_calls_per_tool,
                "max_same_tool_input_repeats": self._config.max_same_tool_input_repeats,
                "max_failure_streak": self._config.max_failure_streak,
                "max_subagent_rounds": self._config.max_subagent_rounds,
                "max_parallel_subagents": self._config.max_parallel_subagents,
                "require_verification_before_done": self._config.require_verification_before_done,
                "verification_tool_names": self._config.verification_tool_names,
                "completion_required_paths": self._config.completion_required_paths,
                "completion_required_patterns": self._config.completion_required_patterns,
            },
            "sessions": {
                sid: {
                    "tool_calls_total": s.tool_calls_total,
                    "tool_calls_by_name": s.tool_calls_by_name,
                    "recent_signature_streak": s.recent_signature_streak,
                    "recent_signature": s.recent_signature,
                    "failure_streak": s.failure_streak,
                    "subagent_rounds": s.subagent_rounds,
                    "verification_calls": s.verification_calls,
                    "blocked_reason": s.blocked_reason,
                }
                for sid, s in self._sessions.items()
            },
        }

    def load_state(self, state: Dict[str, Any]) -> None:
        cfg = state.get("config", {})
        self._config = RunGuardConfig(
            enabled=bool(cfg.get("enabled", True)),
            max_tool_calls_total=int(cfg.get("max_tool_calls_total", 60)),
            max_tool_calls_per_tool=dict(cfg.get("max_tool_calls_per_tool", {})),
            max_same_tool_input_repeats=int(cfg.get("max_same_tool_input_repeats", 4)),
            max_failure_streak=int(cfg.get("max_failure_streak", 6)),
            max_subagent_rounds=int(cfg.get("max_subagent_rounds", 8)),
            max_parallel_subagents=int(cfg.get("max_parallel_subagents", 5)),
            require_verification_before_done=bool(cfg.get("require_verification_before_done", True)),
            verification_tool_names=list(cfg.get("verification_tool_names", [])),
            completion_required_paths=list(cfg.get("completion_required_paths", [])),
            completion_required_patterns=list(cfg.get("completion_required_patterns", [])),
        )
        self._sessions = {}
        for sid, raw in (state.get("sessions", {}) or {}).items():
            self._sessions[str(sid)] = _SessionState(
                tool_calls_total=int(raw.get("tool_calls_total", 0)),
                tool_calls_by_name=dict(raw.get("tool_calls_by_name", {})),
                recent_signature_streak=int(raw.get("recent_signature_streak", 0)),
                recent_signature=str(raw.get("recent_signature", "")),
                failure_streak=int(raw.get("failure_streak", 0)),
                subagent_rounds=int(raw.get("subagent_rounds", 0)),
                verification_calls=int(raw.get("verification_calls", 0)),
                blocked_reason=str(raw.get("blocked_reason", "")),
            )
