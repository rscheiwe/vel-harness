"""
Backend Protocols

Defines interfaces for filesystem, sandbox, and database backends.
"""

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class FilesystemBackend(Protocol):
    """
    Protocol for filesystem backends.

    Implementations provide file operations that may be:
    - In-memory (StateFilesystemBackend)
    - Sandboxed (SandboxFilesystemBackend)
    - Composite (routing different paths to different backends)
    """

    def ls(self, path: str = "/") -> Dict[str, Any]:
        """
        List files and directories at a path.

        Args:
            path: Directory path to list

        Returns:
            Dict with 'path' and 'entries' (list of file/dir info)
        """
        ...

    def read_file(
        self,
        path: str,
        offset: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """
        Read file contents with pagination.

        Args:
            path: File path to read
            offset: Starting line number (0-indexed)
            limit: Maximum number of lines to return

        Returns:
            Dict with 'content', 'lines_returned', 'total_lines', 'has_more'
        """
        ...

    def write_file(self, path: str, content: str) -> Dict[str, Any]:
        """
        Write content to a file.

        Args:
            path: File path to write
            content: Content to write

        Returns:
            Dict with 'status', 'path', 'lines', 'size_bytes'
        """
        ...

    def edit_file(
        self,
        path: str,
        old_text: str,
        new_text: str,
    ) -> Dict[str, Any]:
        """
        Edit file by replacing old_text with new_text.

        Args:
            path: File path to edit
            old_text: Text to find and replace (must be unique)
            new_text: Replacement text

        Returns:
            Dict with 'status', 'path', 'lines_changed'
        """
        ...

    def glob(self, pattern: str) -> Dict[str, Any]:
        """
        Find files matching a glob pattern.

        Args:
            pattern: Glob pattern (e.g., '**/*.md')

        Returns:
            Dict with 'pattern', 'matches', 'count'
        """
        ...

    def grep(
        self,
        pattern: str,
        path: str = "/",
        include: Optional[str] = None,
        head_limit: int = 50,
    ) -> Dict[str, Any]:
        """
        Search for a regex pattern in files.

        Args:
            pattern: Regex pattern to search
            path: Base path to search in
            include: Optional glob pattern to filter files
            head_limit: Maximum number of matches to return (default: 50)

        Returns:
            Dict with 'pattern', 'matches', 'total_matches', 'head_limit', 'truncated'
        """
        ...


@runtime_checkable
class ExecutionBackend(Protocol):
    """
    Protocol for code execution backends.

    Provides sandboxed execution of shell commands and Python code.
    """

    def execute(
        self,
        command: str,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute a shell command.

        Args:
            command: Shell command to execute
            timeout: Maximum execution time in seconds

        Returns:
            Dict with 'stdout', 'stderr', 'exit_code', 'success', 'timed_out'
        """
        ...

    def execute_python(
        self,
        code: str,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute Python code.

        Args:
            code: Python code to execute
            timeout: Maximum execution time in seconds

        Returns:
            Dict with 'stdout', 'stderr', 'exit_code', 'success', 'timed_out'
        """
        ...
