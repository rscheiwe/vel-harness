"""
Loop detection and recovery hints middleware.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from vel_harness.middleware.base import BaseMiddleware


class LoopDetectionMiddleware(BaseMiddleware):
    """Tracks repeated edits/failures and emits recovery nudges."""

    def __init__(
        self,
        enabled: bool = True,
        file_edit_threshold: int = 4,
        failure_streak_threshold: int = 3,
    ) -> None:
        self._enabled = enabled
        self._file_edit_threshold = file_edit_threshold
        self._failure_streak_threshold = failure_streak_threshold
        self._session_file_edits: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._session_failure_streak: Dict[str, int] = defaultdict(int)

    def get_system_prompt_segment(self) -> str:
        if not self._enabled:
            return ""
        return (
            "## Loop Recovery\n"
            "If you repeatedly edit the same file or repeat failing commands,\n"
            "step back, re-check the task spec, and choose a different approach.\n"
        )

    def on_tool_success(self, session_id: str, tool_name: str, tool_input: Dict[str, Any]) -> None:
        if not self._enabled:
            return
        if tool_name in {"write_file", "edit_file"}:
            path = str(tool_input.get("path", ""))
            if path:
                self._session_file_edits[session_id][path] += 1
        self._session_failure_streak[session_id] = 0

    def on_tool_failure(self, session_id: str, tool_name: str, _tool_input: Dict[str, Any]) -> None:
        if not self._enabled:
            return
        self._session_failure_streak[session_id] += 1

    def get_recovery_hint(self, session_id: str) -> Optional[str]:
        if not self._enabled:
            return None
        hint_parts: List[str] = []

        hot_file = self._get_hot_file(session_id)
        if hot_file is not None:
            path, count = hot_file
            if count >= self._file_edit_threshold:
                hint_parts.append(
                    f"You have edited `{path}` {count} times. Reconsider your approach before more edits."
                )

        failures = self._session_failure_streak.get(session_id, 0)
        if failures >= self._failure_streak_threshold:
            hint_parts.append(
                f"You have {failures} consecutive tool failures. Re-plan and try an alternate strategy."
            )

        if not hint_parts:
            return None
        return " ".join(hint_parts)

    def get_state(self) -> Dict[str, Any]:
        return {
            "enabled": self._enabled,
            "file_edit_threshold": self._file_edit_threshold,
            "failure_streak_threshold": self._failure_streak_threshold,
            "session_file_edits": {sid: dict(counts) for sid, counts in self._session_file_edits.items()},
            "session_failure_streak": dict(self._session_failure_streak),
        }

    def load_state(self, state: Dict[str, Any]) -> None:
        self._enabled = bool(state.get("enabled", True))
        self._file_edit_threshold = int(state.get("file_edit_threshold", 4))
        self._failure_streak_threshold = int(state.get("failure_streak_threshold", 3))

        self._session_file_edits.clear()
        for sid, counts in state.get("session_file_edits", {}).items():
            if isinstance(counts, dict):
                self._session_file_edits[str(sid)] = defaultdict(
                    int, {str(path): int(c) for path, c in counts.items()}
                )

        self._session_failure_streak = defaultdict(
            int,
            {str(sid): int(c) for sid, c in state.get("session_failure_streak", {}).items()},
        )

    def _get_hot_file(self, session_id: str) -> Optional[Tuple[str, int]]:
        counts = self._session_file_edits.get(session_id, {})
        if not counts:
            return None
        path = max(counts, key=lambda p: counts[p])
        return path, counts[path]

