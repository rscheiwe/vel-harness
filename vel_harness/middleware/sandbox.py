"""
Sandbox Middleware

Provides secure code execution tools using OS-level sandboxing.
"""

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from vel import ToolSpec

from vel_harness.backends.sandbox import (
    BaseSandbox,
    SandboxFilesystemBackend,
    create_sandbox,
)
from vel_harness.middleware.base import BaseMiddleware


class SandboxMiddleware(BaseMiddleware):
    """
    Middleware providing sandboxed code execution.

    Provides tools:
    - execute: Run shell commands in sandbox
    - execute_python: Run Python code in sandbox

    Sandbox isolation depends on platform:
    - macOS: Seatbelt (sandbox-exec)
    - Linux: bubblewrap (bwrap)
    """

    def __init__(
        self,
        working_dir: Optional[str] = None,
        network: bool = False,
        timeout: int = 30,
        allowed_paths: Optional[List[str]] = None,
        fallback_unsandboxed: bool = False,
    ) -> None:
        """
        Initialize sandbox middleware.

        Args:
            working_dir: Working directory for execution. Defaults to temp dir.
            network: Whether to allow network access
            timeout: Default command timeout in seconds
            allowed_paths: Additional paths to allow read access
            fallback_unsandboxed: Use unsandboxed executor if sandbox unavailable
        """
        self._working_dir = working_dir or tempfile.mkdtemp(prefix="vel_sandbox_")
        self._network = network
        self._timeout = timeout
        self._allowed_paths = allowed_paths or []
        self._fallback_unsandboxed = fallback_unsandboxed

        self._sandbox = create_sandbox(
            working_dir=self._working_dir,
            network=network,
            timeout=timeout,
            allowed_paths=self._allowed_paths,
            fallback_unsandboxed=fallback_unsandboxed,
        )

    @property
    def working_dir(self) -> str:
        """Get the sandbox working directory."""
        return self._working_dir

    @property
    def sandbox(self) -> BaseSandbox:
        """Get the underlying sandbox instance."""
        return self._sandbox

    def get_tools(self) -> List[ToolSpec]:
        """Return sandbox tools."""
        return [
            ToolSpec.from_function(
                self._execute,
                name="execute",
                description=(
                    "Execute a shell command in the sandbox environment. "
                    "Commands run in an isolated environment with limited "
                    "filesystem access. Use for running scripts, compiling code, "
                    "or executing programs."
                ),
                category="execution",
            ),
            ToolSpec.from_function(
                self._execute_python,
                name="execute_python",
                description=(
                    "Execute Python code in the sandbox environment. "
                    "Code runs in an isolated Python interpreter with limited "
                    "filesystem and network access. Use for data analysis, "
                    "calculations, or testing code snippets."
                ),
                category="execution",
            ),
        ]

    def get_system_prompt_segment(self) -> str:
        """Return system prompt segment describing sandbox capabilities."""
        return f"""## Code Execution

You have access to a sandboxed execution environment for running code safely.

**Available Tools:**
- `execute(command, timeout)`: Run shell commands
- `execute_python(code, timeout)`: Run Python code

**Working Directory:** `{self._working_dir}`

**Sandbox Properties:**
- Network access: {'enabled' if self._network else 'disabled'}
- Default timeout: {self._timeout} seconds
- Platform: {self._sandbox.__class__.__name__}

**Usage Notes:**
- Files written persist in the working directory between executions
- Use execute_python for data analysis, calculations, and testing
- Use execute for shell operations, compiling, running scripts
- Long-running commands will timeout after {self._timeout}s (adjustable via timeout param)
"""

    def _execute(self, command: str, timeout: Optional[int] = None) -> Dict[str, Any]:
        """
        Execute a shell command in the sandbox.

        Args:
            command: Shell command to execute
            timeout: Command timeout in seconds (optional, uses default if not specified)

        Returns:
            Dict with stdout, stderr, exit_code, success, timed_out
        """
        result = self._sandbox.execute(command, timeout)
        return result.to_dict()

    def _execute_python(self, code: str, timeout: Optional[int] = None) -> Dict[str, Any]:
        """
        Execute Python code in the sandbox.

        Args:
            code: Python code to execute
            timeout: Execution timeout in seconds (optional, uses default if not specified)

        Returns:
            Dict with stdout, stderr, exit_code, success, timed_out
        """
        result = self._sandbox.execute_python(code, timeout)
        return result.to_dict()

    def get_state(self) -> Dict[str, Any]:
        """Get current middleware state."""
        return {
            "working_dir": self._working_dir,
            "network": self._network,
            "timeout": self._timeout,
            "allowed_paths": self._allowed_paths,
            "fallback_unsandboxed": self._fallback_unsandboxed,
        }

    def load_state(self, state: Dict[str, Any]) -> None:
        """
        Load middleware state.

        Note: This recreates the sandbox with saved settings.
        The working directory contents are NOT preserved by this method -
        that should be handled separately if needed.
        """
        self._working_dir = state.get("working_dir", self._working_dir)
        self._network = state.get("network", self._network)
        self._timeout = state.get("timeout", self._timeout)
        self._allowed_paths = state.get("allowed_paths", self._allowed_paths)
        self._fallback_unsandboxed = state.get("fallback_unsandboxed", self._fallback_unsandboxed)

        # Recreate sandbox with loaded settings
        self._sandbox = create_sandbox(
            working_dir=self._working_dir,
            network=self._network,
            timeout=self._timeout,
            allowed_paths=self._allowed_paths,
            fallback_unsandboxed=self._fallback_unsandboxed,
        )


class SandboxFilesystemMiddleware(BaseMiddleware):
    """
    Middleware combining filesystem operations with sandboxed execution.

    Provides a complete environment for code development and execution:
    - Read/write files in sandbox
    - Execute commands in sandbox
    - All operations isolated from host system
    """

    def __init__(
        self,
        working_dir: Optional[str] = None,
        network: bool = False,
        timeout: int = 30,
        fallback_unsandboxed: bool = False,
    ) -> None:
        """
        Initialize sandbox filesystem middleware.

        Args:
            working_dir: Working directory. Defaults to temp dir.
            network: Whether to allow network access
            timeout: Default command timeout
            fallback_unsandboxed: Use unsandboxed executor if sandbox unavailable
        """
        self._working_dir = working_dir or tempfile.mkdtemp(prefix="vel_sandbox_")
        self._network = network
        self._timeout = timeout
        self._fallback_unsandboxed = fallback_unsandboxed

        self._backend = SandboxFilesystemBackend(
            working_dir=self._working_dir,
            network=network,
            timeout=timeout,
            fallback_unsandboxed=fallback_unsandboxed,
        )

    @property
    def working_dir(self) -> str:
        """Get the sandbox working directory."""
        return self._working_dir

    @property
    def backend(self) -> SandboxFilesystemBackend:
        """Get the underlying filesystem backend."""
        return self._backend

    def get_tools(self) -> List[ToolSpec]:
        """Return all sandbox filesystem tools."""
        return [
            ToolSpec.from_function(
                self._backend.ls,
                name="ls",
                description="List directory contents in the sandbox",
                category="filesystem",
            ),
            ToolSpec.from_function(
                self._backend.read_file,
                name="read_file",
                description=(
                    "Read a file from the sandbox. Supports pagination with "
                    "offset and limit parameters."
                ),
                category="filesystem",
            ),
            ToolSpec.from_function(
                self._backend.write_file,
                name="write_file",
                description="Write content to a file in the sandbox",
                category="filesystem",
            ),
            ToolSpec.from_function(
                self._backend.edit_file,
                name="edit_file",
                description=(
                    "Edit a file by replacing old_text with new_text. "
                    "old_text must appear exactly once in the file."
                ),
                category="filesystem",
            ),
            ToolSpec.from_function(
                self._backend.glob,
                name="glob",
                description="Find files matching a glob pattern in the sandbox",
                category="filesystem",
            ),
            ToolSpec.from_function(
                self._backend.grep,
                name="grep",
                description=(
                    "Search for a regex pattern in files. Optionally filter by "
                    "path and file extension."
                ),
                category="filesystem",
            ),
            ToolSpec.from_function(
                self._backend.execute,
                name="execute",
                description=(
                    "Execute a shell command in the sandbox. Returns stdout, "
                    "stderr, exit_code, and success status."
                ),
                category="execution",
            ),
            ToolSpec.from_function(
                self._backend.execute_python,
                name="execute_python",
                description=(
                    "Execute Python code in the sandbox. Returns stdout, "
                    "stderr, exit_code, and success status."
                ),
                category="execution",
            ),
        ]

    def get_system_prompt_segment(self) -> str:
        """Return system prompt describing sandbox filesystem capabilities."""
        return f"""## Sandboxed Development Environment

You have access to a sandboxed environment for developing and executing code.

**Filesystem Tools:**
- `ls(path)`: List directory contents
- `read_file(path, offset?, limit?)`: Read file with optional pagination
- `write_file(path, content)`: Write content to file
- `edit_file(path, old_text, new_text)`: Replace text in file
- `glob(pattern)`: Find files matching pattern
- `grep(pattern, path?, include?)`: Search file contents

**Execution Tools:**
- `execute(command, timeout?)`: Run shell command
- `execute_python(code, timeout?)`: Run Python code

**Working Directory:** `{self._working_dir}`
**Network Access:** {'enabled' if self._network else 'disabled'}
**Default Timeout:** {self._timeout} seconds

**Notes:**
- All file paths are relative to the working directory
- Files persist between executions within the session
- Commands are isolated from the host system
"""

    def get_state(self) -> Dict[str, Any]:
        """Get current middleware state."""
        return {
            "working_dir": self._working_dir,
            "network": self._network,
            "timeout": self._timeout,
            "fallback_unsandboxed": self._fallback_unsandboxed,
        }

    def load_state(self, state: Dict[str, Any]) -> None:
        """Load middleware state."""
        self._working_dir = state.get("working_dir", self._working_dir)
        self._network = state.get("network", self._network)
        self._timeout = state.get("timeout", self._timeout)
        self._fallback_unsandboxed = state.get("fallback_unsandboxed", self._fallback_unsandboxed)

        # Recreate backend with loaded settings
        self._backend = SandboxFilesystemBackend(
            working_dir=self._working_dir,
            network=self._network,
            timeout=self._timeout,
            fallback_unsandboxed=self._fallback_unsandboxed,
        )
