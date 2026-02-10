"""
Filesystem Middleware Tests

Tests for StateFilesystemBackend and FilesystemMiddleware.
"""

import pytest

from vel_harness.backends.state import StateFilesystemBackend, FileData
from vel_harness.middleware.filesystem import FilesystemMiddleware


class TestStateFilesystemBackend:
    """Tests for StateFilesystemBackend."""

    def test_write_and_read_file(self, state_backend: StateFilesystemBackend) -> None:
        """Test basic write and read operations."""
        # Write a file
        result = state_backend.write_file("/test.txt", "Hello, World!")

        assert result["status"] == "ok"
        assert result["path"] == "/test.txt"
        assert result["lines"] == 1

        # Read it back
        read_result = state_backend.read_file("/test.txt")

        assert "error" not in read_result
        assert "Hello, World!" in read_result["content"]
        assert read_result["total_lines"] == 1

    def test_read_nonexistent_file(self, state_backend: StateFilesystemBackend) -> None:
        """Test reading a file that doesn't exist."""
        result = state_backend.read_file("/nonexistent.txt")
        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_write_file_creates_path(self, state_backend: StateFilesystemBackend) -> None:
        """Test that writing creates nested paths."""
        result = state_backend.write_file("/deep/nested/path/file.txt", "content")
        assert result["status"] == "ok"

        # Should be readable
        read_result = state_backend.read_file("/deep/nested/path/file.txt")
        assert "error" not in read_result

    def test_read_file_pagination(self, state_backend: StateFilesystemBackend) -> None:
        """Test reading files with pagination."""
        # Create a multi-line file
        lines = "\n".join([f"Line {i}" for i in range(100)])
        state_backend.write_file("/multiline.txt", lines)

        # Read first page
        result1 = state_backend.read_file("/multiline.txt", offset=0, limit=10)
        assert result1["lines_returned"] == 10
        assert result1["has_more"] is True
        assert result1["total_lines"] == 100

        # Read second page
        result2 = state_backend.read_file("/multiline.txt", offset=10, limit=10)
        assert result2["lines_returned"] == 10
        assert "Line 10" in result2["content"]

    def test_edit_file_unique_match(self, state_backend: StateFilesystemBackend) -> None:
        """Test editing a file with unique text."""
        state_backend.write_file("/edit.txt", "Hello World\nGoodbye World")

        result = state_backend.edit_file("/edit.txt", "Hello", "Hi")
        assert result["status"] == "ok"

        # Verify change
        read_result = state_backend.read_file("/edit.txt")
        assert "Hi World" in read_result["content"]
        assert "Hello" not in read_result["content"]

    def test_edit_file_multiple_matches_error(self, state_backend: StateFilesystemBackend) -> None:
        """Test that editing fails when text appears multiple times."""
        state_backend.write_file("/edit.txt", "World Hello World")

        result = state_backend.edit_file("/edit.txt", "World", "Earth")
        assert "error" in result
        assert "2 times" in result["error"]

    def test_edit_file_not_found_error(self, state_backend: StateFilesystemBackend) -> None:
        """Test editing when old_text not in file."""
        state_backend.write_file("/edit.txt", "Hello World")

        result = state_backend.edit_file("/edit.txt", "Goodbye", "Hi")
        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_edit_nonexistent_file(self, state_backend: StateFilesystemBackend) -> None:
        """Test editing a file that doesn't exist."""
        result = state_backend.edit_file("/nonexistent.txt", "old", "new")
        assert "error" in result

    def test_ls_root(self, populated_backend: StateFilesystemBackend) -> None:
        """Test listing root directory."""
        result = populated_backend.ls("/")

        assert result["path"] == "/"
        entries = result["entries"]

        # Should have directories and files
        names = [e["name"] for e in entries]
        assert "data" in names
        assert "reports" in names
        assert "src" in names
        assert "readme.md" in names

    def test_ls_subdirectory(self, populated_backend: StateFilesystemBackend) -> None:
        """Test listing a subdirectory."""
        result = populated_backend.ls("/data")

        entries = result["entries"]
        names = [e["name"] for e in entries]

        assert "sales.csv" in names
        assert "users.csv" in names

    def test_ls_empty_directory(self, state_backend: StateFilesystemBackend) -> None:
        """Test listing an empty or non-existent directory."""
        result = state_backend.ls("/empty")
        assert result["entries"] == []

    def test_glob_pattern_matching(self, populated_backend: StateFilesystemBackend) -> None:
        """Test glob pattern matching."""
        # Match markdown file at root
        result = populated_backend.glob("/*.md")
        assert result["count"] >= 1
        assert any("readme.md" in m for m in result["matches"])

        # Match markdown in reports
        result2 = populated_backend.glob("/reports/*.md")
        assert result2["count"] >= 1
        assert any("q1.md" in m for m in result2["matches"])

    def test_glob_specific_directory(self, populated_backend: StateFilesystemBackend) -> None:
        """Test glob in specific directory."""
        result = populated_backend.glob("/data/*.csv")
        assert result["count"] == 2

    def test_grep_regex_search(self, populated_backend: StateFilesystemBackend) -> None:
        """Test searching with regex patterns."""
        result = populated_backend.grep("def.*:")

        assert result["total_matches"] >= 2
        # Should find main and helper functions
        files_matched = [m["file"] for m in result["matches"]]
        assert any("main.py" in f for f in files_matched)
        assert any("utils.py" in f for f in files_matched)

    def test_grep_with_path_filter(self, populated_backend: StateFilesystemBackend) -> None:
        """Test grep with path filter."""
        result = populated_backend.grep("Alice", path="/data")

        assert result["total_matches"] >= 1
        assert all("/data" in m["file"] for m in result["matches"])

    def test_grep_with_include_filter(self, populated_backend: StateFilesystemBackend) -> None:
        """Test grep with include pattern."""
        result = populated_backend.grep(".*", path="/", include="*.py")

        # Should only match .py files
        for match in result["matches"]:
            assert match["file"].endswith(".py")

    def test_grep_invalid_regex(self, state_backend: StateFilesystemBackend) -> None:
        """Test grep with invalid regex."""
        result = state_backend.grep("[invalid")
        assert "error" in result
        assert "Invalid regex" in result["error"]

    def test_delete_file(self, state_backend: StateFilesystemBackend) -> None:
        """Test deleting a file."""
        state_backend.write_file("/to_delete.txt", "temporary")

        # Delete it
        result = state_backend.delete_file("/to_delete.txt")
        assert result["status"] == "ok"

        # Should not exist anymore
        assert not state_backend.exists("/to_delete.txt")

    def test_delete_nonexistent_file(self, state_backend: StateFilesystemBackend) -> None:
        """Test deleting a file that doesn't exist."""
        result = state_backend.delete_file("/nonexistent.txt")
        assert "error" in result

    def test_path_normalization(self, state_backend: StateFilesystemBackend) -> None:
        """Test that paths are normalized."""
        # Write without leading slash
        state_backend.write_file("test.txt", "content")

        # Read with leading slash
        result = state_backend.read_file("/test.txt")
        assert "error" not in result

    def test_state_persistence(self, populated_backend: StateFilesystemBackend) -> None:
        """Test state serialization and restoration."""
        # Get state
        state = populated_backend.get_state()

        # Create new backend and load state
        new_backend = StateFilesystemBackend()
        new_backend.load_state(state)

        # Verify files are restored
        result = new_backend.read_file("/readme.md")
        assert "My Project" in result["content"]


class TestFilesystemMiddleware:
    """Tests for FilesystemMiddleware."""

    def test_get_tools(self, filesystem_middleware: FilesystemMiddleware) -> None:
        """Test that middleware returns expected tools."""
        tools = filesystem_middleware.get_tools()

        tool_names = [t.name for t in tools]
        assert "ls" in tool_names
        assert "read_file" in tool_names
        assert "write_file" in tool_names
        assert "edit_file" in tool_names
        assert "glob" in tool_names
        assert "grep" in tool_names

    def test_tool_categories(self, filesystem_middleware: FilesystemMiddleware) -> None:
        """Test that tools have correct categories."""
        tools = filesystem_middleware.get_tools()

        for tool in tools:
            assert tool.category == "filesystem"

    def test_system_prompt_segment(self, filesystem_middleware: FilesystemMiddleware) -> None:
        """Test system prompt segment content."""
        segment = filesystem_middleware.get_system_prompt_segment()

        assert "File System" in segment
        assert "ls" in segment
        assert "read_file" in segment
        assert "write_file" in segment

    def test_tool_execution(self, filesystem_middleware: FilesystemMiddleware) -> None:
        """Test executing tools through middleware."""
        # Write via tool
        write_result = filesystem_middleware._write_file("/test.txt", "Hello")
        assert write_result["status"] == "ok"

        # Read via tool
        read_result = filesystem_middleware._read_file("/test.txt")
        assert "Hello" in read_result["content"]

    def test_middleware_state_persistence(
        self, populated_filesystem_middleware: FilesystemMiddleware
    ) -> None:
        """Test middleware state persistence."""
        # Get state
        state = populated_filesystem_middleware.get_state()

        # Create new middleware and load state
        new_middleware = FilesystemMiddleware()
        new_middleware.load_state(state)

        # Verify files are accessible
        result = new_middleware._read_file("/readme.md")
        assert "My Project" in result["content"]
