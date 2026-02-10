"""
In-Memory Filesystem Backend

Files are stored in memory and don't persist across sessions.
Useful for testing and ephemeral workspaces.
"""

import fnmatch
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class FileData:
    """Metadata and content for a file."""

    content: List[str]  # Lines of content
    created_at: str
    modified_at: str
    size_bytes: int = 0

    @classmethod
    def from_content(cls, content: str) -> "FileData":
        """Create FileData from string content."""
        lines = content.split("\n")
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            content=lines,
            created_at=now,
            modified_at=now,
            size_bytes=len(content.encode("utf-8")),
        )

    def to_string(self) -> str:
        """Convert back to string content."""
        return "\n".join(self.content)


class StateFilesystemBackend:
    """
    In-memory filesystem backend.

    Files are stored in a dictionary and don't persist across sessions.
    All paths are virtual and start with '/'.
    """

    def __init__(self) -> None:
        self._files: Dict[str, FileData] = {}

    def _normalize_path(self, path: str) -> str:
        """Ensure path starts with / and has no trailing /."""
        if not path.startswith("/"):
            path = "/" + path
        return path.rstrip("/") or "/"

    def ls(self, path: str = "/") -> Dict[str, Any]:
        """List files and directories at a path."""
        path = self._normalize_path(path)

        entries: List[Dict[str, Any]] = []
        dirs_seen: set[str] = set()

        for file_path, file_data in self._files.items():
            # Check if file is under this path
            if path == "/":
                rel_path = file_path.lstrip("/")
            elif file_path.startswith(path + "/"):
                rel_path = file_path[len(path) + 1 :]
            else:
                continue

            # Split into parts to find direct children
            parts = rel_path.split("/")
            if len(parts) == 1 and parts[0]:
                # Direct file child
                entries.append(
                    {
                        "name": parts[0],
                        "type": "file",
                        "path": file_path,
                        "size": file_data.size_bytes,
                    }
                )
            elif len(parts) > 1:
                # Directory child
                dir_name = parts[0]
                if dir_name and dir_name not in dirs_seen:
                    dirs_seen.add(dir_name)
                    dir_path = f"{path}/{dir_name}" if path != "/" else f"/{dir_name}"
                    entries.append(
                        {
                            "name": dir_name,
                            "type": "directory",
                            "path": dir_path,
                        }
                    )

        # Sort: directories first, then files, alphabetically
        entries.sort(key=lambda x: (x["type"] == "file", x["name"].lower()))

        return {
            "path": path,
            "entries": entries,
        }

    def read_file(
        self,
        path: str,
        offset: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Read file contents with pagination."""
        path = self._normalize_path(path)

        if path not in self._files:
            return {"error": f"File not found: {path}"}

        file_data = self._files[path]
        total_lines = len(file_data.content)

        # Apply pagination
        lines = file_data.content[offset : offset + limit]

        # Add line numbers (1-indexed for display)
        numbered_lines = [f"{i + offset + 1:6d} | {line}" for i, line in enumerate(lines)]

        return {
            "path": path,
            "content": "\n".join(numbered_lines),
            "lines_returned": len(lines),
            "total_lines": total_lines,
            "offset": offset,
            "has_more": offset + limit < total_lines,
        }

    def write_file(self, path: str, content: str) -> Dict[str, Any]:
        """Write content to a file (creates or overwrites)."""
        path = self._normalize_path(path)

        # Check if file exists to preserve created_at
        existing = self._files.get(path)
        file_data = FileData.from_content(content)
        if existing:
            file_data.created_at = existing.created_at

        self._files[path] = file_data

        return {
            "status": "ok",
            "path": path,
            "lines": len(file_data.content),
            "size_bytes": file_data.size_bytes,
        }

    def edit_file(
        self,
        path: str,
        old_text: str,
        new_text: str,
    ) -> Dict[str, Any]:
        """Edit file by replacing old_text with new_text."""
        path = self._normalize_path(path)

        if path not in self._files:
            return {"error": f"File not found: {path}"}

        content = self._files[path].to_string()

        if old_text not in content:
            return {"error": "old_text not found in file"}

        count = content.count(old_text)
        if count > 1:
            return {"error": f"old_text appears {count} times. Must be unique."}

        # Perform replacement
        new_content = content.replace(old_text, new_text)

        # Preserve created_at
        created_at = self._files[path].created_at
        self._files[path] = FileData.from_content(new_content)
        self._files[path].created_at = created_at

        # Calculate lines changed
        old_lines = old_text.count("\n")
        new_lines = new_text.count("\n")
        lines_changed = abs(new_lines - old_lines)

        return {
            "status": "ok",
            "path": path,
            "lines_changed": lines_changed,
        }

    def glob(self, pattern: str) -> Dict[str, Any]:
        """Find files matching a glob pattern."""
        # Handle patterns that don't start with /
        if not pattern.startswith("/"):
            pattern = "/" + pattern

        matches: List[str] = []
        for path in self._files.keys():
            if fnmatch.fnmatch(path, pattern):
                matches.append(path)

        return {
            "pattern": pattern,
            "matches": sorted(matches),
            "count": len(matches),
        }

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
            pattern: Regex pattern to search for
            path: Base directory to search in (default: root '/')
            include: Optional glob pattern to filter files (e.g., '*.py')
            head_limit: Maximum number of matches to return (default: 50)

        Returns:
            Dict with matches, counts, and truncation info
        """
        path = self._normalize_path(path)

        try:
            regex = re.compile(pattern)
        except re.error as e:
            return {"error": f"Invalid regex: {e}"}

        matches: List[Dict[str, Any]] = []
        files_searched = 0
        total_matches = 0

        for file_path, file_data in self._files.items():
            # Check path filter
            if path != "/" and not file_path.startswith(path + "/") and file_path != path:
                continue

            # Check include filter (glob pattern for filename)
            if include:
                filename = file_path.rsplit("/", 1)[-1]
                if not fnmatch.fnmatch(filename, include):
                    continue

            files_searched += 1

            for line_num, line in enumerate(file_data.content, 1):
                if regex.search(line):
                    total_matches += 1
                    # Only collect up to head_limit matches
                    if len(matches) < head_limit:
                        matches.append(
                            {
                                "file": file_path,
                                "line": line_num,
                                "content": line.strip()[:500],  # Truncate long lines
                            }
                        )

        truncated = total_matches > head_limit

        return {
            "pattern": pattern,
            "path": path,
            "files_searched": files_searched,
            "matches": matches,
            "total_matches": total_matches,
            "head_limit": head_limit,
            "truncated": truncated,
        }

    def delete_file(self, path: str) -> Dict[str, Any]:
        """Delete a file."""
        path = self._normalize_path(path)

        if path not in self._files:
            return {"error": f"File not found: {path}"}

        del self._files[path]

        return {
            "status": "ok",
            "path": path,
        }

    def exists(self, path: str) -> bool:
        """Check if a file exists."""
        path = self._normalize_path(path)
        return path in self._files

    def get_state(self) -> Dict[str, Any]:
        """Get serializable state for persistence."""
        return {
            "files": {
                path: {
                    "content": file_data.content,
                    "created_at": file_data.created_at,
                    "modified_at": file_data.modified_at,
                    "size_bytes": file_data.size_bytes,
                }
                for path, file_data in self._files.items()
            }
        }

    def load_state(self, state: Dict[str, Any]) -> None:
        """Load state from persistence."""
        self._files.clear()
        for path, file_info in state.get("files", {}).items():
            self._files[path] = FileData(
                content=file_info["content"],
                created_at=file_info["created_at"],
                modified_at=file_info["modified_at"],
                size_bytes=file_info.get("size_bytes", 0),
            )
