"""
Sandbox Tests

Tests for sandbox backends and sandbox middleware.
"""

import platform
import tempfile
from pathlib import Path

import pytest

from vel_harness.backends.sandbox import (
    BaseSandbox,
    ExecutionResult,
    SandboxNotAvailableError,
    UnsandboxedExecutor,
    create_sandbox,
)
from vel_harness.middleware.sandbox import (
    SandboxMiddleware,
    SandboxFilesystemMiddleware,
)


# Fixtures


@pytest.fixture
def temp_working_dir() -> str:
    """Create a temporary working directory."""
    with tempfile.TemporaryDirectory(prefix="vel_test_sandbox_") as tmpdir:
        yield tmpdir


@pytest.fixture
def unsandboxed_executor(temp_working_dir: str) -> UnsandboxedExecutor:
    """Create an unsandboxed executor for testing."""
    return UnsandboxedExecutor(working_dir=temp_working_dir)


@pytest.fixture
def sandbox(temp_working_dir: str) -> BaseSandbox:
    """Create a sandbox appropriate for the current platform."""
    return create_sandbox(
        working_dir=temp_working_dir,
        network=False,
        timeout=30,
        fallback_unsandboxed=True,
    )


@pytest.fixture
def sandbox_middleware(temp_working_dir: str) -> SandboxMiddleware:
    """Create sandbox middleware for testing."""
    return SandboxMiddleware(
        working_dir=temp_working_dir,
        network=False,
        timeout=30,
        fallback_unsandboxed=True,
    )


@pytest.fixture
def sandbox_filesystem_middleware(temp_working_dir: str) -> SandboxFilesystemMiddleware:
    """Create sandbox filesystem middleware for testing."""
    return SandboxFilesystemMiddleware(
        working_dir=temp_working_dir,
        network=False,
        timeout=30,
        fallback_unsandboxed=True,
    )


# ExecutionResult Tests


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_successful_result(self) -> None:
        """Test creating a successful result."""
        result = ExecutionResult(
            stdout="Hello",
            stderr="",
            exit_code=0,
        )
        assert result.stdout == "Hello"
        assert result.stderr == ""
        assert result.exit_code == 0
        assert result.timed_out is False

        d = result.to_dict()
        assert d["success"] is True
        assert d["timed_out"] is False

    def test_failed_result(self) -> None:
        """Test creating a failed result."""
        result = ExecutionResult(
            stdout="",
            stderr="Error occurred",
            exit_code=1,
        )
        d = result.to_dict()
        assert d["success"] is False
        assert d["exit_code"] == 1
        assert d["stderr"] == "Error occurred"

    def test_timeout_result(self) -> None:
        """Test creating a timeout result."""
        result = ExecutionResult(
            stdout="",
            stderr="Timed out",
            exit_code=-1,
            timed_out=True,
        )
        d = result.to_dict()
        assert d["success"] is False
        assert d["timed_out"] is True


# UnsandboxedExecutor Tests


class TestUnsandboxedExecutor:
    """Tests for UnsandboxedExecutor."""

    def test_execute_simple_command(self, unsandboxed_executor: UnsandboxedExecutor) -> None:
        """Test executing a simple command."""
        result = unsandboxed_executor.execute("echo 'Hello World'")
        assert result.exit_code == 0
        assert "Hello World" in result.stdout
        assert result.timed_out is False

    def test_execute_with_exit_code(self, unsandboxed_executor: UnsandboxedExecutor) -> None:
        """Test command with non-zero exit code."""
        result = unsandboxed_executor.execute("exit 42")
        assert result.exit_code == 42

    def test_execute_with_stderr(self, unsandboxed_executor: UnsandboxedExecutor) -> None:
        """Test command that writes to stderr."""
        result = unsandboxed_executor.execute("echo 'error' >&2")
        assert "error" in result.stderr

    def test_execute_in_working_dir(
        self, unsandboxed_executor: UnsandboxedExecutor, temp_working_dir: str
    ) -> None:
        """Test that commands run in working directory."""
        result = unsandboxed_executor.execute("pwd")
        assert temp_working_dir in result.stdout

    def test_execute_with_timeout(self, unsandboxed_executor: UnsandboxedExecutor) -> None:
        """Test command that times out."""
        result = unsandboxed_executor.execute("sleep 10", timeout=1)
        assert result.timed_out is True
        assert result.exit_code == -1

    def test_execute_python(self, unsandboxed_executor: UnsandboxedExecutor) -> None:
        """Test executing Python code."""
        result = unsandboxed_executor.execute_python("print('Hello from Python')")
        assert result.exit_code == 0
        assert "Hello from Python" in result.stdout

    def test_execute_python_with_imports(self, unsandboxed_executor: UnsandboxedExecutor) -> None:
        """Test executing Python code with imports."""
        code = """
import json
data = {"key": "value"}
print(json.dumps(data))
"""
        result = unsandboxed_executor.execute_python(code)
        assert result.exit_code == 0
        assert '"key"' in result.stdout

    def test_execute_python_error(self, unsandboxed_executor: UnsandboxedExecutor) -> None:
        """Test executing Python code with error."""
        result = unsandboxed_executor.execute_python("raise ValueError('test error')")
        assert result.exit_code != 0
        assert "ValueError" in result.stderr or "test error" in result.stderr


# create_sandbox Factory Tests


class TestCreateSandbox:
    """Tests for create_sandbox factory function."""

    def test_create_sandbox_with_fallback(self, temp_working_dir: str) -> None:
        """Test creating sandbox with fallback enabled."""
        sandbox = create_sandbox(
            working_dir=temp_working_dir,
            fallback_unsandboxed=True,
        )
        assert sandbox is not None
        # Should be able to execute
        result = sandbox.execute("echo test")
        assert result.exit_code == 0

    def test_create_sandbox_platform_specific(self, temp_working_dir: str) -> None:
        """Test that sandbox is platform-appropriate."""
        sandbox = create_sandbox(
            working_dir=temp_working_dir,
            fallback_unsandboxed=True,
        )
        system = platform.system()
        if system == "Darwin":
            from vel_harness.backends.sandbox import SeatbeltSandbox

            assert isinstance(sandbox, (SeatbeltSandbox, UnsandboxedExecutor))
        elif system == "Linux":
            from vel_harness.backends.sandbox import BubblewrapSandbox

            assert isinstance(sandbox, (BubblewrapSandbox, UnsandboxedExecutor))
        else:
            assert isinstance(sandbox, UnsandboxedExecutor)


# Sandbox Execution Tests (platform-specific behavior)


class TestSandboxExecution:
    """Tests for sandbox execution."""

    def test_sandbox_execute(self, sandbox: BaseSandbox) -> None:
        """Test basic sandbox execution."""
        result = sandbox.execute("echo 'sandboxed'")
        assert result.exit_code == 0
        assert "sandboxed" in result.stdout

    def test_sandbox_file_operations(
        self, sandbox: BaseSandbox, temp_working_dir: str
    ) -> None:
        """Test file operations within sandbox."""
        # Write a file
        sandbox.execute(f'echo "test content" > "{temp_working_dir}/test.txt"')

        # Read it back
        result = sandbox.execute(f'cat "{temp_working_dir}/test.txt"')
        assert result.exit_code == 0
        assert "test content" in result.stdout

    def test_sandbox_python_execution(self, sandbox: BaseSandbox) -> None:
        """Test Python execution in sandbox."""
        code = """
x = 5
y = 10
print(f"Sum: {x + y}")
"""
        result = sandbox.execute_python(code)
        assert result.exit_code == 0
        assert "Sum: 15" in result.stdout


# SandboxMiddleware Tests


class TestSandboxMiddleware:
    """Tests for SandboxMiddleware."""

    def test_get_tools(self, sandbox_middleware: SandboxMiddleware) -> None:
        """Test that middleware returns expected tools."""
        tools = sandbox_middleware.get_tools()
        tool_names = [t.name for t in tools]

        assert "execute" in tool_names
        assert "execute_python" in tool_names
        assert len(tools) == 2

    def test_tool_categories(self, sandbox_middleware: SandboxMiddleware) -> None:
        """Test that tools have correct categories."""
        tools = sandbox_middleware.get_tools()
        for tool in tools:
            assert tool.category == "execution"

    def test_system_prompt_segment(self, sandbox_middleware: SandboxMiddleware) -> None:
        """Test system prompt content."""
        segment = sandbox_middleware.get_system_prompt_segment()

        assert "execute" in segment
        assert "execute_python" in segment
        assert "sandbox" in segment.lower()

    def test_execute_via_middleware(self, sandbox_middleware: SandboxMiddleware) -> None:
        """Test executing commands via middleware."""
        result = sandbox_middleware._execute("echo 'hello'")
        assert result["success"] is True
        assert "hello" in result["stdout"]

    def test_execute_python_via_middleware(
        self, sandbox_middleware: SandboxMiddleware
    ) -> None:
        """Test executing Python via middleware."""
        result = sandbox_middleware._execute_python("print(2 + 2)")
        assert result["success"] is True
        assert "4" in result["stdout"]

    def test_state_persistence(
        self, sandbox_middleware: SandboxMiddleware, temp_working_dir: str
    ) -> None:
        """Test middleware state persistence."""
        state = sandbox_middleware.get_state()

        assert state["working_dir"] == temp_working_dir
        assert state["network"] is False
        assert state["timeout"] == 30

    def test_working_dir_property(
        self, sandbox_middleware: SandboxMiddleware, temp_working_dir: str
    ) -> None:
        """Test working_dir property."""
        assert sandbox_middleware.working_dir == temp_working_dir


# SandboxFilesystemMiddleware Tests


class TestSandboxFilesystemMiddleware:
    """Tests for SandboxFilesystemMiddleware."""

    def test_get_tools(
        self, sandbox_filesystem_middleware: SandboxFilesystemMiddleware
    ) -> None:
        """Test that middleware returns all expected tools."""
        tools = sandbox_filesystem_middleware.get_tools()
        tool_names = [t.name for t in tools]

        # Filesystem tools
        assert "ls" in tool_names
        assert "read_file" in tool_names
        assert "write_file" in tool_names
        assert "edit_file" in tool_names
        assert "glob" in tool_names
        assert "grep" in tool_names

        # Execution tools
        assert "execute" in tool_names
        assert "execute_python" in tool_names

        assert len(tools) == 8

    def test_tool_categories(
        self, sandbox_filesystem_middleware: SandboxFilesystemMiddleware
    ) -> None:
        """Test that tools have correct categories."""
        tools = sandbox_filesystem_middleware.get_tools()

        for tool in tools:
            if tool.name in ["execute", "execute_python"]:
                assert tool.category == "execution"
            else:
                assert tool.category == "filesystem"

    def test_write_and_read_file(
        self, sandbox_filesystem_middleware: SandboxFilesystemMiddleware
    ) -> None:
        """Test writing and reading files via sandbox."""
        # Write a file
        write_result = sandbox_filesystem_middleware.backend.write_file(
            "/test.txt", "Hello Sandbox"
        )
        assert write_result["status"] == "ok"

        # Read it back
        read_result = sandbox_filesystem_middleware.backend.read_file("/test.txt")
        assert "error" not in read_result
        assert "Hello Sandbox" in read_result["content"]

    def test_execute_with_file(
        self, sandbox_filesystem_middleware: SandboxFilesystemMiddleware
    ) -> None:
        """Test executing commands that interact with files."""
        # Write a file
        sandbox_filesystem_middleware.backend.write_file(
            "/script.sh", "#!/bin/bash\necho 'Script ran!'"
        )

        # Execute it (use relative path since we run in working directory)
        result = sandbox_filesystem_middleware.backend.execute("bash script.sh")
        assert result["success"] is True
        assert "Script ran!" in result["stdout"]

    def test_system_prompt_segment(
        self, sandbox_filesystem_middleware: SandboxFilesystemMiddleware
    ) -> None:
        """Test system prompt content."""
        segment = sandbox_filesystem_middleware.get_system_prompt_segment()

        # Filesystem tools
        assert "ls" in segment
        assert "read_file" in segment
        assert "write_file" in segment

        # Execution tools
        assert "execute" in segment
        assert "execute_python" in segment

    def test_state_persistence(
        self,
        sandbox_filesystem_middleware: SandboxFilesystemMiddleware,
        temp_working_dir: str,
    ) -> None:
        """Test middleware state persistence."""
        state = sandbox_filesystem_middleware.get_state()

        assert state["working_dir"] == temp_working_dir
        assert state["network"] is False
        assert state["timeout"] == 30


# Integration Tests


class TestSandboxIntegration:
    """Integration tests for sandbox functionality."""

    def test_data_analysis_workflow(
        self, sandbox_filesystem_middleware: SandboxFilesystemMiddleware
    ) -> None:
        """Test a typical data analysis workflow."""
        # Write data file
        csv_data = "name,value\nAlice,100\nBob,200\nCharlie,150"
        sandbox_filesystem_middleware.backend.write_file("/data.csv", csv_data)

        # Execute Python analysis
        code = """
import csv
total = 0
with open('data.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        total += int(row['value'])
print(f"Total: {total}")
"""
        result = sandbox_filesystem_middleware.backend.execute_python(code)
        assert result["success"] is True
        assert "Total: 450" in result["stdout"]

    def test_script_development_workflow(
        self, sandbox_filesystem_middleware: SandboxFilesystemMiddleware
    ) -> None:
        """Test developing and running a script."""
        # Write a Python script
        script = """
def greet(name):
    return f"Hello, {name}!"

if __name__ == "__main__":
    print(greet("World"))
"""
        sandbox_filesystem_middleware.backend.write_file("/greet.py", script)

        # Run the script (use relative path since we run in working directory)
        result = sandbox_filesystem_middleware.backend.execute("python3 greet.py")
        assert result["success"] is True
        assert "Hello, World!" in result["stdout"]

        # Edit the script
        edit_result = sandbox_filesystem_middleware.backend.edit_file(
            "/greet.py", 'print(greet("World"))', 'print(greet("Sandbox"))'
        )
        assert edit_result["status"] == "ok"

        # Run again
        result2 = sandbox_filesystem_middleware.backend.execute("python3 greet.py")
        assert "Hello, Sandbox!" in result2["stdout"]

    def test_grep_across_files(
        self, sandbox_filesystem_middleware: SandboxFilesystemMiddleware
    ) -> None:
        """Test grep functionality across multiple files."""
        # Create some files
        sandbox_filesystem_middleware.backend.write_file(
            "/src/main.py", "def main():\n    print('Main function')\n"
        )
        sandbox_filesystem_middleware.backend.write_file(
            "/src/utils.py", "def helper():\n    print('Helper function')\n"
        )
        sandbox_filesystem_middleware.backend.write_file(
            "/readme.txt", "This is the readme file"
        )

        # Search for function definitions
        result = sandbox_filesystem_middleware.backend.grep("def.*:")
        assert result["total_matches"] >= 2
