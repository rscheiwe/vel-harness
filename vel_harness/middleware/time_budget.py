"""Time budget middleware for long-running autonomous tasks."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Dict, Optional

from vel_harness.middleware.base import BaseMiddleware


class TimeBudgetMiddleware(BaseMiddleware):
    """Tracks per-session elapsed runtime and suggests verification pivots."""

    def __init__(
        self,
        enabled: bool = True,
        soft_limit_seconds: int = 240,
        hard_limit_seconds: int = 300,
    ) -> None:
        self._enabled = enabled
        self._soft_limit_seconds = soft_limit_seconds
        self._hard_limit_seconds = hard_limit_seconds
        self._session_started_at: Dict[str, float] = {}
        self._session_warned: Dict[str, bool] = defaultdict(bool)
        self._session_hard_warned: Dict[str, bool] = defaultdict(bool)

    def start(self, session_id: str) -> None:
        if not self._enabled:
            return
        if session_id not in self._session_started_at:
            self._session_started_at[session_id] = time.time()

    def elapsed_seconds(self, session_id: str) -> float:
        started = self._session_started_at.get(session_id)
        if started is None:
            return 0.0
        return max(0.0, time.time() - started)

    def should_pivot_to_verify(self, session_id: str) -> bool:
        if not self._enabled:
            return False
        return self.elapsed_seconds(session_id) >= self._soft_limit_seconds

    def is_over_hard_limit(self, session_id: str) -> bool:
        if not self._enabled:
            return False
        return self.elapsed_seconds(session_id) >= self._hard_limit_seconds

    def get_runtime_hint(self, session_id: str) -> Optional[str]:
        if not self._enabled:
            return None
        elapsed = self.elapsed_seconds(session_id)
        if elapsed >= self._hard_limit_seconds and not self._session_hard_warned[session_id]:
            self._session_hard_warned[session_id] = True
            return (
                f"Hard time budget exceeded ({int(elapsed)}s). Immediately switch to verification "
                "and finalization unless a critical blocker remains."
            )
        if elapsed >= self._soft_limit_seconds and not self._session_warned[session_id]:
            self._session_warned[session_id] = True
            return (
                f"Soft time budget reached ({int(elapsed)}s). Shift from exploration to verification "
                "and completion."
            )
        return None

    def get_system_prompt_segment(self) -> str:
        if not self._enabled:
            return ""
        return (
            "## Time Budgeting\n"
            "Use available time intentionally: discover quickly, then prioritize verification and completion\n"
            "as budget is consumed.\n"
        )

    def get_state(self) -> Dict[str, Any]:
        return {
            "enabled": self._enabled,
            "soft_limit_seconds": self._soft_limit_seconds,
            "hard_limit_seconds": self._hard_limit_seconds,
            "active_sessions": sorted(self._session_started_at.keys()),
        }

    def load_state(self, state: Dict[str, Any]) -> None:
        self._enabled = bool(state.get("enabled", True))
        self._soft_limit_seconds = int(state.get("soft_limit_seconds", 240))
        self._hard_limit_seconds = int(state.get("hard_limit_seconds", 300))

