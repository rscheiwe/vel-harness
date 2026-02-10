"""
Filesystem Middleware

Provides file system tools for reading, writing, and editing files.
Supports multiple backends (in-memory, sandbox, composite).
"""

from typing import Any, Dict, List, Optional

from vel import ToolSpec

from vel_harness.backends.protocol import FilesystemBackend
from vel_harness.backends.state import StateFilesystemBackend
from vel_harness.middleware.base import BaseMiddleware


class FilesystemMiddleware(BaseMiddleware):
    """
    Middleware providing filesystem tools.

    Supports multiple backends:
    - StateFilesystemBackend: In-memory (default)
    - SandboxFilesystemBackend: Real filesystem in sandbox
    - CompositeBackend: Route different paths to different backends
    """

    def __init__(self, backend: Optional[FilesystemBackend] = None) -> None:
        """
        Initialize filesystem middleware.

        Args:
            backend: Filesystem backend to use. Defaults to StateFilesystemBackend.
        """
        self.backend: FilesystemBackend = backend or StateFilesystemBackend()

    def get_tools(self) -> List[ToolSpec]:
        """Return filesystem tools."""
        return [
            ToolSpec.from_function(
                self._ls,
                name="ls",
                description="List files and directories at a path.",
                category="filesystem",
                tags=["read", "directory"],
            ),
            ToolSpec.from_function(
                self._read_file,
                name="read_file",
                description="""
Read contents of a file with optional pagination.
Use offset and limit for large files.
Returns numbered lines for easy reference.
                """.strip(),
                category="filesystem",
                tags=["read", "file"],
            ),
            ToolSpec.from_function(
                self._write_file,
                name="write_file",
                description="""
Write content to a file. Creates the file if it doesn't exist,
or overwrites if it does. Use for creating new documents,
saving results, or storing data.
                """.strip(),
                category="filesystem",
                tags=["write", "file"],
                requires_confirmation=True,
            ),
            ToolSpec.from_function(
                self._edit_file,
                name="edit_file",
                description="""
Edit a file by replacing specific text. The old_text must
appear exactly once in the file. Use for making targeted
changes to existing files.
                """.strip(),
                category="filesystem",
                tags=["write", "file", "edit"],
                requires_confirmation=True,
            ),
            ToolSpec.from_function(
                self._glob,
                name="glob",
                description="Find files matching a glob pattern (e.g., '**/*.md', '/reports/*.json').",
                category="filesystem",
                tags=["read", "search"],
            ),
            ToolSpec.from_function(
                self._grep,
                name="grep",
                description="Search for a regex pattern in file contents. Returns matching lines with file and line number. Use head_limit to control result size.",
                category="filesystem",
                tags=["read", "search"],
            ),
        ]

    def _ls(self, path: str = "/") -> Dict[str, Any]:
        """
        List files and directories at a path.

        Args:
            path: Directory path to list (default: root '/')

        Returns:
            Dict with path and list of entries (files and directories)
        """
        return self.backend.ls(path)

    def _read_file(
        self,
        path: str,
        offset: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """
        Read file contents with optional pagination.

        Args:
            path: File path to read
            offset: Starting line number (0-indexed, default: 0)
            limit: Maximum lines to return (default: 100)

        Returns:
            Dict with content, line count, and pagination info
        """
        return self.backend.read_file(path, offset, limit)

    def _write_file(self, path: str, content: str) -> Dict[str, Any]:
        """
        Write content to a file.

        Args:
            path: File path to write (e.g., '/reports/analysis.md')
            content: Content to write to the file

        Returns:
            Dict with status, path, and file info
        """
        return self.backend.write_file(path, content)

    def _edit_file(self, path: str, old_text: str, new_text: str) -> Dict[str, Any]:
        """
        Edit a file by replacing specific text.

        Args:
            path: File path to edit
            old_text: Text to find and replace (must appear exactly once)
            new_text: Text to replace old_text with

        Returns:
            Dict with status and edit info
        """
        return self.backend.edit_file(path, old_text, new_text)

    def _glob(self, pattern: str) -> Dict[str, Any]:
        """
        Find files matching a glob pattern.

        Args:
            pattern: Glob pattern (e.g., '**/*.md', '/data/*.csv')

        Returns:
            Dict with pattern, matching paths, and count
        """
        return self.backend.glob(pattern)

    def _grep(
        self,
        pattern: str,
        path: str = "/",
        include: Optional[str] = None,
        head_limit: int = 50,
    ) -> Dict[str, Any]:
        """
        Search for a regex pattern in files.

        Args:
            pattern: Regex pattern to search for
            path: Base directory to search in (default: root '/')
            include: Optional glob pattern to filter files (e.g., '*.py')
            head_limit: Maximum number of matches to return (default: 50, max: 200)

        Returns:
            Dict with matches (file, line number, content), counts, and truncation info
        """
        # Clamp head_limit to reasonable bounds
        head_limit = max(1, min(head_limit, 200))
        return self.backend.grep(pattern, path, include, head_limit=head_limit)

    def get_system_prompt_segment(self) -> str:
        """Return system prompt segment for filesystem."""
        return """
## File System

You have tools for working with files:

- `ls(path)` - List directory contents
- `read_file(path, offset, limit)` - Read file contents (paginated)
- `write_file(path, content)` - Create or overwrite a file
- `edit_file(path, old_text, new_text)` - Make targeted edits
- `glob(pattern)` - Find files by pattern
- `grep(pattern, path, include)` - Search file contents

**When to use files:**
- Save important findings or intermediate results
- Create reports, documents, or exports
- Offload large content from context
- Store data for later steps

**File paths:**
- All paths start with `/`
- Use descriptive names: `/reports/q4_analysis.md`
- Organize by purpose: `/data/`, `/reports/`, `/notes/`

**Best practices:**
- Write findings to files as you work
- Use files to manage large outputs
- Create markdown files for reports
- Save code to files before executing
"""

    def get_state(self) -> Dict[str, Any]:
        """Get state for persistence."""
        if hasattr(self.backend, "get_state"):
            return {"backend_state": self.backend.get_state()}
        return {}

    def load_state(self, state: Dict[str, Any]) -> None:
        """Load state from persistence."""
        if hasattr(self.backend, "load_state") and "backend_state" in state:
            self.backend.load_state(state["backend_state"])
