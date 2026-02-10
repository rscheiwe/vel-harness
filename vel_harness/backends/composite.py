"""
Composite Storage Backend

Routes file operations to different backends based on path prefix.
Enables mixing ephemeral (in-memory/sandbox) storage with persistent
storage for specific paths like /memories/.
"""

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Tuple


class StorageBackend(Protocol):
    """Protocol for storage backends."""

    def ls(self, path: str) -> Dict[str, Any]: ...
    def read_file(self, path: str, offset: int = 0, limit: int = 100) -> Dict[str, Any]: ...
    def write_file(self, path: str, content: str) -> Dict[str, Any]: ...
    def delete_file(self, path: str) -> Dict[str, Any]: ...
    def exists(self, path: str) -> bool: ...
    def glob(self, pattern: str) -> Dict[str, Any]: ...
    def grep(self, pattern: str, path: str = "/", include: Optional[str] = None, head_limit: int = 50) -> Dict[str, Any]: ...


@dataclass
class RouteConfig:
    """Configuration for a storage route."""

    prefix: str
    backend: StorageBackend
    description: str = ""


class CompositeBackend:
    """
    Routes file operations to different backends based on path prefix.

    Enables mixing ephemeral (in-memory/sandbox) storage with persistent
    storage for specific paths like /memories/.

    Example:
        composite = CompositeBackend(
            default=in_memory_backend,
            routes={
                "/memories/": persistent_backend,
                "/context/": context_backend,
            }
        )
    """

    def __init__(
        self,
        default: StorageBackend,
        routes: Optional[Dict[str, StorageBackend]] = None,
    ):
        """
        Args:
            default: Backend for paths not matching any route
            routes: Map of path prefix → backend
        """
        self.default = default
        self.routes = routes or {}

    def _get_backend(self, path: str) -> Tuple[StorageBackend, str]:
        """Get backend and adjusted path for a given path."""
        # Sort by prefix length (longest first) to match most specific route
        for prefix in sorted(self.routes.keys(), key=len, reverse=True):
            if path.startswith(prefix):
                return self.routes[prefix], path
        return self.default, path

    def ls(self, path: str = "/") -> Dict[str, Any]:
        """List files and directories at a path."""
        backend, adjusted_path = self._get_backend(path)
        return backend.ls(adjusted_path)

    def read_file(
        self,
        path: str,
        offset: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Read file contents with pagination."""
        backend, adjusted_path = self._get_backend(path)
        return backend.read_file(adjusted_path, offset, limit)

    def write_file(self, path: str, content: str) -> Dict[str, Any]:
        """Write content to a file."""
        backend, adjusted_path = self._get_backend(path)
        return backend.write_file(adjusted_path, content)

    def edit_file(
        self,
        path: str,
        old_text: str,
        new_text: str,
    ) -> Dict[str, Any]:
        """Edit file by replacing old_text with new_text."""
        backend, adjusted_path = self._get_backend(path)
        # Some backends may not have edit_file
        if hasattr(backend, "edit_file"):
            return backend.edit_file(adjusted_path, old_text, new_text)
        # Fallback: read, replace, write
        result = backend.read_file(adjusted_path)
        if "error" in result:
            return result
        content = result.get("content", "")
        # Remove line numbers if present
        lines = []
        for line in content.split("\n"):
            if " | " in line:
                lines.append(line.split(" | ", 1)[1])
            else:
                lines.append(line)
        content = "\n".join(lines)
        if old_text not in content:
            return {"error": "old_text not found in file"}
        new_content = content.replace(old_text, new_text)
        return backend.write_file(adjusted_path, new_content)

    def delete_file(self, path: str) -> Dict[str, Any]:
        """Delete a file."""
        backend, adjusted_path = self._get_backend(path)
        return backend.delete_file(adjusted_path)

    def exists(self, path: str) -> bool:
        """Check if a file exists."""
        backend, adjusted_path = self._get_backend(path)
        return backend.exists(adjusted_path)

    def glob(self, pattern: str) -> Dict[str, Any]:
        """Find files matching a glob pattern."""
        # Glob needs to search all backends
        all_matches: List[str] = []
        seen_paths: set = set()

        # Check each routed backend
        for prefix, backend in self.routes.items():
            if pattern.startswith(prefix) or pattern.startswith("/" + prefix.lstrip("/")):
                result = backend.glob(pattern)
                for match in result.get("matches", []):
                    if match not in seen_paths:
                        seen_paths.add(match)
                        all_matches.append(match)

        # Check default backend
        result = self.default.glob(pattern)
        for match in result.get("matches", []):
            if match not in seen_paths:
                seen_paths.add(match)
                all_matches.append(match)

        return {
            "pattern": pattern,
            "matches": sorted(all_matches),
            "count": len(all_matches),
        }

    def grep(
        self,
        pattern: str,
        path: str = "/",
        include: Optional[str] = None,
        head_limit: int = 50,
    ) -> Dict[str, Any]:
        """Search for a regex pattern in files."""
        backend, adjusted_path = self._get_backend(path)
        return backend.grep(pattern, adjusted_path, include, head_limit=head_limit)

    def get_routes(self) -> Dict[str, str]:
        """Get information about configured routes."""
        return {
            prefix: type(backend).__name__
            for prefix, backend in self.routes.items()
        }


class PersistentStoreBackend:
    """
    Backend that persists to disk.

    Used for /memories/ path to survive across sessions.
    """

    def __init__(
        self,
        base_path: str,  # e.g., ~/.vel_harness/memories/
        agent_id: str = "default",
    ):
        self.base_path = os.path.expanduser(base_path)
        self.agent_id = agent_id
        self.root = os.path.join(self.base_path, agent_id)
        os.makedirs(self.root, exist_ok=True)

    def _resolve_path(self, path: str) -> str:
        """Resolve virtual path to filesystem path."""
        # Strip /memories/ prefix if present
        if path.startswith("/memories/"):
            path = path[len("/memories/"):]
        elif path.startswith("/"):
            path = path[1:]
        return os.path.join(self.root, path)

    def _virtual_path(self, fs_path: str) -> str:
        """Convert filesystem path back to virtual path."""
        rel_path = os.path.relpath(fs_path, self.root)
        return f"/memories/{rel_path}"

    def ls(self, path: str = "/") -> Dict[str, Any]:
        """List files and directories at a path."""
        fs_path = self._resolve_path(path)

        if not os.path.exists(fs_path):
            return {"path": path, "entries": []}

        entries: List[Dict[str, Any]] = []

        if os.path.isdir(fs_path):
            for name in os.listdir(fs_path):
                full_path = os.path.join(fs_path, name)
                if os.path.isdir(full_path):
                    entries.append({
                        "name": name,
                        "type": "directory",
                        "path": f"{path.rstrip('/')}/{name}",
                    })
                else:
                    entries.append({
                        "name": name,
                        "type": "file",
                        "path": f"{path.rstrip('/')}/{name}",
                        "size": os.path.getsize(full_path),
                    })

        # Sort: directories first, then files, alphabetically
        entries.sort(key=lambda x: (x["type"] == "file", x["name"].lower()))

        return {"path": path, "entries": entries}

    def read_file(
        self,
        path: str,
        offset: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Read file contents with pagination."""
        fs_path = self._resolve_path(path)

        if not os.path.exists(fs_path):
            return {"error": f"File not found: {path}"}

        if os.path.isdir(fs_path):
            return {"error": f"Path is a directory: {path}"}

        with open(fs_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        total_lines = len(lines)

        # Apply pagination
        selected = lines[offset : offset + limit]

        # Add line numbers (1-indexed for display)
        numbered_lines = [
            f"{i + offset + 1:6d} | {line.rstrip()}"
            for i, line in enumerate(selected)
        ]

        return {
            "path": path,
            "content": "\n".join(numbered_lines),
            "lines_returned": len(selected),
            "total_lines": total_lines,
            "offset": offset,
            "has_more": offset + limit < total_lines,
        }

    def write_file(self, path: str, content: str) -> Dict[str, Any]:
        """Write content to a file (creates or overwrites)."""
        fs_path = self._resolve_path(path)

        # Ensure parent directory exists
        os.makedirs(os.path.dirname(fs_path), exist_ok=True)

        with open(fs_path, "w", encoding="utf-8") as f:
            f.write(content)

        lines = content.split("\n")

        return {
            "status": "ok",
            "path": path,
            "lines": len(lines),
            "size_bytes": len(content.encode("utf-8")),
        }

    def edit_file(
        self,
        path: str,
        old_text: str,
        new_text: str,
    ) -> Dict[str, Any]:
        """Edit file by replacing old_text with new_text."""
        fs_path = self._resolve_path(path)

        if not os.path.exists(fs_path):
            return {"error": f"File not found: {path}"}

        with open(fs_path, "r", encoding="utf-8") as f:
            content = f.read()

        if old_text not in content:
            return {"error": "old_text not found in file"}

        count = content.count(old_text)
        if count > 1:
            return {"error": f"old_text appears {count} times. Must be unique."}

        new_content = content.replace(old_text, new_text)

        with open(fs_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        old_lines = old_text.count("\n")
        new_lines = new_text.count("\n")
        lines_changed = abs(new_lines - old_lines)

        return {
            "status": "ok",
            "path": path,
            "lines_changed": lines_changed,
        }

    def delete_file(self, path: str) -> Dict[str, Any]:
        """Delete a file."""
        fs_path = self._resolve_path(path)

        if not os.path.exists(fs_path):
            return {"error": f"File not found: {path}"}

        os.remove(fs_path)

        return {"status": "ok", "path": path}

    def exists(self, path: str) -> bool:
        """Check if a file exists."""
        fs_path = self._resolve_path(path)
        return os.path.exists(fs_path)

    def glob(self, pattern: str) -> Dict[str, Any]:
        """Find files matching a glob pattern."""
        import fnmatch

        # Adjust pattern for virtual path
        if pattern.startswith("/memories/"):
            search_pattern = pattern[len("/memories/"):]
        elif pattern.startswith("/"):
            search_pattern = pattern[1:]
        else:
            search_pattern = pattern

        matches: List[str] = []

        for root, dirs, files in os.walk(self.root):
            for filename in files:
                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, self.root)
                if fnmatch.fnmatch(rel_path, search_pattern):
                    matches.append(f"/memories/{rel_path}")

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
        """Search for a regex pattern in files."""
        import fnmatch
        import re

        try:
            regex = re.compile(pattern)
        except re.error as e:
            return {"error": f"Invalid regex: {e}"}

        search_path = self._resolve_path(path)
        matches: List[Dict[str, Any]] = []
        files_searched = 0
        total_matches = 0

        for root, dirs, files in os.walk(search_path):
            for filename in files:
                # Check include filter
                if include and not fnmatch.fnmatch(filename, include):
                    continue

                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, self.root)
                virtual_path = f"/memories/{rel_path}"

                files_searched += 1

                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        for line_num, line in enumerate(f, 1):
                            if regex.search(line):
                                total_matches += 1
                                if len(matches) < head_limit:
                                    matches.append({
                                        "file": virtual_path,
                                        "line": line_num,
                                        "content": line.strip()[:500],  # Truncate long lines
                                    })
                except Exception:
                    continue  # Skip unreadable files

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

    def get_state(self) -> Dict[str, Any]:
        """Get serializable state (for compatibility)."""
        return {"base_path": self.base_path, "agent_id": self.agent_id}


def create_composite_backend(
    default_backend: StorageBackend,
    memories_path: str = "~/.vel_harness/memories",
    agent_id: str = "default",
    additional_routes: Optional[Dict[str, StorageBackend]] = None,
) -> CompositeBackend:
    """
    Create a composite backend with /memories/ routing.

    Args:
        default_backend: Backend for ephemeral storage
        memories_path: Path for persistent memory storage
        agent_id: Agent identifier for memory isolation
        additional_routes: Additional path→backend routes

    Returns:
        Configured CompositeBackend
    """
    persistent = PersistentStoreBackend(memories_path, agent_id)

    routes = {"/memories/": persistent}
    if additional_routes:
        routes.update(additional_routes)

    return CompositeBackend(
        default=default_backend,
        routes=routes,
    )
