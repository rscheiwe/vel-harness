"""
Pre-completion verification middleware.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, Tuple

from vel_harness.middleware.base import BaseMiddleware


_CODING_TASK_RE = re.compile(
    r"\b(implement|fix|bug|refactor|code|function|test|suite|compile|build)\b",
    flags=re.IGNORECASE,
)
_VERIFY_CMD_RE = re.compile(
    r"\b(pytest|unittest|nose|go test|cargo test|npm test|pnpm test|yarn test|mvn test|gradle test|py_compile|ruff check|mypy|make test|make compile|make smoke)\b",
    flags=re.IGNORECASE,
)


class VerificationMiddleware(BaseMiddleware):
    """Requires an explicit verification pass before completion."""

    def __init__(self, enabled: bool = True, strict: bool = True, max_followups: int = 1) -> None:
        self._enabled = enabled
        self._strict = strict
        self._max_followups = max_followups
        self._session_verifications = defaultdict(int)
        self._session_followups = defaultdict(int)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def get_system_prompt_segment(self) -> str:
        if not self._enabled:
            return ""
        return (
            "## Build / Verify Loop\n"
            "Before finalizing coding work, run verification (tests/lint/build), inspect full outputs,\n"
            "compare against the user spec, and fix issues if needed.\n"
        )

    def on_tool_success(self, session_id: str, tool_name: str, tool_input: Dict[str, Any]) -> None:
        if not self._enabled:
            return
        if tool_name not in {"execute", "execute_python"}:
            return
        cmd = str(tool_input.get("command") or tool_input.get("cmd") or "")
        if _VERIFY_CMD_RE.search(cmd):
            self._session_verifications[session_id] += 1

    def should_followup(
        self,
        session_id: str,
        user_message: str,
    ) -> Tuple[bool, str]:
        """Return whether another verification turn is required."""
        if not self._enabled:
            return False, ""
        if self._session_followups[session_id] >= self._max_followups:
            return False, ""
        if not _CODING_TASK_RE.search(user_message):
            return False, ""
        if self._session_verifications[session_id] > 0:
            return False, ""
        reason = "No verification command was run for a coding task."
        return True, reason

    def mark_followup_used(self, session_id: str) -> None:
        self._session_followups[session_id] += 1

    def build_followup_prompt(self, reason: str) -> str:
        return (
            "Before finalizing, complete a verification pass.\n"
            f"Reason: {reason}\n"
            "Checklist:\n"
            "1) Run concrete verification commands now (prefer tests first, then compile/lint if needed).\n"
            "2) Read full command output.\n"
            "3) Compare results against the user's original task spec.\n"
            "4) Fix issues and then provide the final response.\n"
            "Do not finalize without explicit verification evidence."
        )

    def get_state(self) -> Dict[str, Any]:
        return {
            "enabled": self._enabled,
            "strict": self._strict,
            "max_followups": self._max_followups,
            "session_verifications": dict(self._session_verifications),
            "session_followups": dict(self._session_followups),
        }

    def load_state(self, state: Dict[str, Any]) -> None:
        self._enabled = bool(state.get("enabled", True))
        self._strict = bool(state.get("strict", True))
        self._max_followups = int(state.get("max_followups", 1))
        self._session_verifications = defaultdict(
            int,
            {str(k): int(v) for k, v in state.get("session_verifications", {}).items()},
        )
        self._session_followups = defaultdict(
            int,
            {str(k): int(v) for k, v in state.get("session_followups", {}).items()},
        )
