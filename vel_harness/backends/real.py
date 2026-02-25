"""
Real Filesystem Backend

Provides direct access to the actual filesystem.
"""

import os
import re
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Dict, List, Optional


class RealFilesystemBackend:
    """
    Backend that provides direct access to the real filesystem.

    No sandboxing - full read/write access to the filesystem.
    """

    def __init__(self, base_path: Optional[str] = None) -> None:
        """
        Initialize real filesystem backend.

        Args:
            base_path: Optional base path to scope operations to.
                       If None, allows access to entire filesystem.
        """
        self.base_path = Path(base_path).resolve() if base_path else None

    def _resolve_path(self, path: str) -> Path:
        """Resolve a path, optionally relative to base_path."""
        if self.base_path:
            raw = Path(path)
            # Keep absolute paths absolute; resolve relative paths from base_path.
            candidate = raw.resolve() if raw.is_absolute() else (self.base_path / raw).resolve()
            try:
                candidate.relative_to(self.base_path)
            except ValueError:
                raise PermissionError(f"Path escapes base_path: {path}")
            return candidate
        return Path(path).resolve()

    def ls(self, path: str = "/") -> Dict[str, Any]:
        """List files and directories at a path."""
        try:
            resolved = self._resolve_path(path)
        except PermissionError as e:
            return {"path": path, "error": str(e), "entries": []}

        if not resolved.exists():
            return {
                "path": str(resolved),
                "error": f"Path does not exist: {resolved}",
                "entries": [],
            }

        if not resolved.is_dir():
            return {
                "path": str(resolved),
                "error": f"Not a directory: {resolved}",
                "entries": [],
            }

        entries = []
        try:
            for item in sorted(resolved.iterdir()):
                try:
                    stat = item.stat()
                    entries.append({
                        "name": item.name,
                        "type": "directory" if item.is_dir() else "file",
                        "size": stat.st_size if item.is_file() else None,
                    })
                except (PermissionError, OSError):
                    entries.append({
                        "name": item.name,
                        "type": "unknown",
                        "error": "permission denied",
                    })
        except PermissionError:
            return {
                "path": str(resolved),
                "error": "Permission denied",
                "entries": [],
            }

        return {
            "path": str(resolved),
            "entries": entries,
        }

    def read_file(
        self,
        path: str,
        offset: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Read file contents with pagination."""
        try:
            resolved = self._resolve_path(path)
        except PermissionError as e:
            return {"path": path, "error": str(e), "content": ""}

        if not resolved.exists():
            return {
                "path": str(resolved),
                "error": f"File does not exist: {resolved}",
                "content": "",
            }

        if not resolved.is_file():
            return {
                "path": str(resolved),
                "error": f"Not a file: {resolved}",
                "content": "",
            }

        try:
            with open(resolved, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            total_lines = len(lines)
            selected = lines[offset : offset + limit]

            # Add line numbers
            numbered = []
            for i, line in enumerate(selected, start=offset + 1):
                numbered.append(f"{i:6d}│{line.rstrip()}")

            return {
                "path": str(resolved),
                "content": "\n".join(numbered),
                "lines_returned": len(selected),
                "total_lines": total_lines,
                "has_more": offset + limit < total_lines,
            }
        except PermissionError:
            return {
                "path": str(resolved),
                "error": "Permission denied",
                "content": "",
            }
        except Exception as e:
            return {
                "path": str(resolved),
                "error": str(e),
                "content": "",
            }

    def write_file(self, path: str, content: str) -> Dict[str, Any]:
        """Write content to a file."""
        try:
            resolved = self._resolve_path(path)
        except PermissionError as e:
            return {"status": "error", "path": path, "error": str(e)}

        try:
            # Create parent directories if needed
            resolved.parent.mkdir(parents=True, exist_ok=True)

            with open(resolved, "w", encoding="utf-8") as f:
                f.write(content)

            lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)

            return {
                "status": "success",
                "path": str(resolved),
                "lines": lines,
                "size_bytes": len(content.encode("utf-8")),
            }
        except PermissionError:
            return {
                "status": "error",
                "path": str(resolved),
                "error": "Permission denied",
            }
        except Exception as e:
            return {
                "status": "error",
                "path": str(resolved),
                "error": str(e),
            }

    def edit_file(
        self,
        path: str,
        old_text: str,
        new_text: str,
    ) -> Dict[str, Any]:
        """Edit file by replacing old_text with new_text."""
        try:
            resolved = self._resolve_path(path)
        except PermissionError as e:
            return {"status": "error", "path": path, "error": str(e)}

        if not resolved.exists():
            return {
                "status": "error",
                "path": str(resolved),
                "error": f"File does not exist: {resolved}",
            }

        try:
            with open(resolved, "r", encoding="utf-8") as f:
                content = f.read()

            count = content.count(old_text)

            if count == 0:
                return {
                    "status": "error",
                    "path": str(resolved),
                    "error": "old_text not found in file",
                }

            if count > 1:
                return {
                    "status": "error",
                    "path": str(resolved),
                    "error": f"old_text found {count} times, must be unique",
                }

            new_content = content.replace(old_text, new_text)

            with open(resolved, "w", encoding="utf-8") as f:
                f.write(new_content)

            old_lines = old_text.count("\n")
            new_lines = new_text.count("\n")

            return {
                "status": "success",
                "path": str(resolved),
                "lines_changed": abs(new_lines - old_lines) + 1,
            }
        except PermissionError:
            return {
                "status": "error",
                "path": str(resolved),
                "error": "Permission denied",
            }
        except Exception as e:
            return {
                "status": "error",
                "path": str(resolved),
                "error": str(e),
            }

    def glob(self, pattern: str) -> Dict[str, Any]:
        """Find files matching a glob pattern."""
        # Determine base directory for glob
        if self.base_path:
            base = self.base_path
            glob_pattern = pattern.lstrip("/")
        elif pattern.startswith("/"):
            base = Path("/")
            glob_pattern = pattern[1:]
        else:
            base = Path.cwd()
            glob_pattern = pattern

        try:
            matches = []
            for match in base.glob(glob_pattern):
                matches.append({
                    "path": str(match),
                    "type": "directory" if match.is_dir() else "file",
                })

            return {
                "pattern": pattern,
                "matches": matches[:100],  # Limit results
                "count": len(matches),
                "truncated": len(matches) > 100,
            }
        except Exception as e:
            return {
                "pattern": pattern,
                "error": str(e),
                "matches": [],
                "count": 0,
            }

    def grep(
        self,
        pattern: str,
        path: str = "/",
        include: Optional[str] = None,
        head_limit: int = 50,
    ) -> Dict[str, Any]:
        """Search for a regex pattern in files."""
        try:
            resolved = self._resolve_path(path)
        except PermissionError as e:
            return {"pattern": pattern, "path": path, "error": str(e), "matches": []}

        if not resolved.exists():
            return {
                "pattern": pattern,
                "path": str(resolved),
                "error": f"Path does not exist: {resolved}",
                "matches": [],
            }

        try:
            regex = re.compile(pattern)
        except re.error as e:
            return {
                "pattern": pattern,
                "error": f"Invalid regex: {e}",
                "matches": [],
            }

        matches = []
        total_matches = 0

        def search_file(filepath: Path) -> None:
            nonlocal total_matches
            try:
                with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                    for line_num, line in enumerate(f, start=1):
                        if regex.search(line):
                            total_matches += 1
                            if len(matches) < head_limit:
                                matches.append({
                                    "file": str(filepath),
                                    "line": line_num,
                                    "content": line.rstrip()[:200],  # Truncate long lines
                                })
            except (PermissionError, OSError):
                pass

        if resolved.is_file():
            search_file(resolved)
        else:
            # Walk directory
            for root, dirs, files in os.walk(resolved):
                # Skip hidden directories
                dirs[:] = [d for d in dirs if not d.startswith(".")]

                for filename in files:
                    if filename.startswith("."):
                        continue

                    filepath = Path(root) / filename

                    # Apply include filter if specified
                    if include and not fnmatch(filename, include):
                        continue

                    search_file(filepath)

                    # Early exit if we have enough matches
                    if total_matches >= head_limit * 2:
                        break

                if total_matches >= head_limit * 2:
                    break

        return {
            "pattern": pattern,
            "path": str(resolved),
            "matches": matches,
            "total_matches": total_matches,
            "head_limit": head_limit,
            "truncated": total_matches > head_limit,
        }
