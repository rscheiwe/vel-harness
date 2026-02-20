"""
Local environment onboarding middleware.

Builds deterministic environment context (directory layout + available tools)
and injects it into early turns to reduce environment discovery errors.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from vel_harness.middleware.base import BaseMiddleware


class LocalContextMiddleware(BaseMiddleware):
    """Discovers local execution context and prepares injection text."""

    def __init__(
        self,
        working_dir: str,
        enabled: bool = True,
        max_entries: int = 40,
        max_depth: int = 1,
        detect_tools: Optional[List[str]] = None,
    ) -> None:
        self._enabled = enabled
        self._working_dir = str(Path(working_dir).resolve())
        self._max_entries = max_entries
        self._max_depth = max_depth
        self._detect_tools = detect_tools or [
            "python",
            "python3",
            "pytest",
            "uv",
            "npm",
            "pnpm",
            "node",
            "go",
            "cargo",
            "ruff",
            "mypy",
        ]
        self._summary_cache: Dict[str, str] = {}
        self._discovered_sessions: Set[str] = set()

    def get_system_prompt_segment(self) -> str:
        if not self._enabled:
            return ""
        return (
            "## Local Environment Context\n"
            "Start by using the injected workspace map and tool availability.\n"
            "Prefer deterministic verification commands discovered for this workspace.\n"
            "If constraints are tight, shift from exploration to verification and completion.\n"
        )

    def build_injection(self, session_id: str) -> str:
        """Build or reuse deterministic context summary for a session."""
        if not self._enabled:
            return ""
        if session_id in self._summary_cache:
            return self._summary_cache[session_id]
        summary = self._discover_summary()
        self._summary_cache[session_id] = summary
        self._discovered_sessions.add(session_id)
        return summary

    def has_injected(self, session_id: str) -> bool:
        return session_id in self._discovered_sessions

    def get_state(self) -> Dict[str, Any]:
        return {
            "enabled": self._enabled,
            "working_dir": self._working_dir,
            "discovered_sessions": sorted(self._discovered_sessions),
        }

    def load_state(self, state: Dict[str, Any]) -> None:
        self._enabled = bool(state.get("enabled", True))
        wd = state.get("working_dir")
        if isinstance(wd, str):
            self._working_dir = wd
        sessions = state.get("discovered_sessions", [])
        if isinstance(sessions, list):
            self._discovered_sessions = {str(s) for s in sessions}

    def _discover_summary(self) -> str:
        cwd = Path(self._working_dir)
        parent = cwd.parent
        children = self._safe_listdir(cwd)
        parent_children = self._safe_listdir(parent) if parent != cwd else []
        tools = [t for t in self._detect_tools if shutil.which(t)]
        verification_hints = self._verification_hints(children, tools)

        lines = [
            "<local-context>",
            f"cwd: {cwd}",
            f"parent: {parent}",
            f"cwd_entries: {', '.join(children[: self._max_entries]) or '(none)'}",
            f"parent_entries: {', '.join(parent_children[: self._max_entries]) or '(none)'}",
            f"available_tools: {', '.join(tools) if tools else '(none detected)'}",
            f"suggested_verification: {', '.join(verification_hints) if verification_hints else '(none inferred)'}",
            "</local-context>",
        ]
        return "\n".join(lines)

    def _safe_listdir(self, path: Path) -> List[str]:
        try:
            entries = sorted(e.name for e in path.iterdir())
            return entries[: self._max_entries]
        except Exception:
            return []

    def _verification_hints(self, entries: List[str], tools: List[str]) -> List[str]:
        hints: List[str] = []
        lower_entries = {e.lower() for e in entries}
        if "pytest" in tools and any(
            name in lower_entries for name in ("tests", "pyproject.toml", "pytest.ini")
        ):
            hints.append("pytest -q")
        if "npm" in tools and any(name in lower_entries for name in ("package.json",)):
            hints.append("npm test")
        if "pnpm" in tools and any(name in lower_entries for name in ("package.json",)):
            hints.append("pnpm test")
        if "go" in tools and any(name.endswith(".go") for name in lower_entries):
            hints.append("go test ./...")
        if "cargo" in tools and "cargo.toml" in lower_entries:
            hints.append("cargo test")
        return hints

