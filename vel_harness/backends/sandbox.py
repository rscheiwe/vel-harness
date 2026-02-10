"""
Sandbox Backends

Provides secure code execution using OS-level sandboxing:
- macOS: Seatbelt (sandbox-exec)
- Linux: bubblewrap (bwrap)
"""

import platform
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ExecutionResult:
    """Result of sandbox execution."""

    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "success": self.exit_code == 0 and not self.timed_out,
        }


class SandboxNotAvailableError(Exception):
    """Raised when sandbox is not available on this platform."""

    pass


class BaseSandbox:
    """Base class for sandbox implementations."""

    def __init__(
        self,
        working_dir: str,
        allowed_paths: Optional[List[str]] = None,
        network: bool = False,
        timeout: int = 30,
    ) -> None:
        """
        Initialize sandbox.

        Args:
            working_dir: Directory for sandboxed file operations (read-write)
            allowed_paths: Additional paths to allow read access
            network: Whether to allow network access
            timeout: Default command timeout in seconds
        """
        self.working_dir = Path(working_dir).resolve()
        self.allowed_paths = allowed_paths or []
        self.network = network
        self.timeout = timeout

        # Ensure working directory exists
        self.working_dir.mkdir(parents=True, exist_ok=True)

    def execute(self, command: str, timeout: Optional[int] = None) -> ExecutionResult:
        """Execute command in sandbox."""
        raise NotImplementedError

    def execute_python(
        self,
        code: str,
        timeout: Optional[int] = None,
    ) -> ExecutionResult:
        """Execute Python code in sandbox."""
        # Write code to temp file in working directory
        script_path = self.working_dir / "_temp_script.py"
        script_path.write_text(code)

        try:
            result = self.execute(f"python3 {script_path}", timeout)
        finally:
            # Clean up
            script_path.unlink(missing_ok=True)

        return result


class SeatbeltSandbox(BaseSandbox):
    """
    macOS sandbox using Seatbelt (sandbox-exec).

    Provides filesystem and network isolation via macOS sandbox profiles.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        if platform.system() != "Darwin":
            raise SandboxNotAvailableError("SeatbeltSandbox requires macOS")

    def _build_profile(self) -> str:
        """Build Seatbelt profile (SBPL)."""
        # Base profile with deny-default
        profile = f"""
(version 1)
(deny default)

;; Allow process operations
(allow process-fork)
(allow process-exec)
(allow process-info*)
(allow signal)
(allow sysctl-read)

;; Allow Mach IPC (required for many system services)
(allow mach-lookup)
(allow mach-register)
(allow ipc-posix-shm*)

;; Allow pseudo-terminals (for shell execution)
(allow pseudo-tty)

;; Allow reading system libraries and binaries
(allow file-read*
    (subpath "/usr")
    (subpath "/System")
    (subpath "/Library")
    (subpath "/bin")
    (subpath "/sbin")
    (subpath "/private/var/db")
    (subpath "/private/etc")
    (subpath "/etc")
    (subpath "/Applications/Xcode.app")
    (subpath "/Library/Developer")
)

;; Allow /dev access (null, urandom, tty, etc.)
(allow file-read* file-write*
    (subpath "/dev")
)

;; Allow temp directories (both real and symlinked paths)
(allow file-read* file-write*
    (subpath "/tmp")
    (subpath "/private/tmp")
    (subpath "/var/folders")
    (subpath "/private/var/folders")
)

;; Allow working directory (read-write)
(allow file-read* file-write*
    (subpath "{self.working_dir}")
)

;; Allow Python/Homebrew paths
(allow file-read*
    (subpath "/opt/homebrew")
    (subpath "/usr/local")
    (subpath "/Library/Frameworks/Python.framework")
)

;; Allow user site-packages (common anaconda/venv locations)
(allow file-read*
    (subpath "/opt/anaconda3")
    (regex #"^/Users/[^/]+/\\.pyenv")
    (regex #"^/Users/[^/]+/anaconda3")
    (regex #"^/Users/[^/]+/miniconda3")
    (regex #"^/Users/[^/]+/\\.local")
)
"""
        # Additional allowed paths
        for path in self.allowed_paths:
            resolved = Path(path).resolve()
            if resolved.exists():
                profile += f'\n(allow file-read* (subpath "{resolved}"))'

        # Network policy
        if self.network:
            profile += "\n(allow network*)"
        else:
            profile += "\n(deny network*)"

        return profile

    def execute(self, command: str, timeout: Optional[int] = None) -> ExecutionResult:
        """Execute command in Seatbelt sandbox."""
        timeout = timeout or self.timeout
        profile = self._build_profile()

        try:
            result = subprocess.run(
                ["sandbox-exec", "-p", profile, "bash", "-c", command],
                capture_output=True,
                timeout=timeout,
                cwd=str(self.working_dir),
            )
            return ExecutionResult(
                stdout=result.stdout.decode("utf-8", errors="replace"),
                stderr=result.stderr.decode("utf-8", errors="replace"),
                exit_code=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                exit_code=-1,
                timed_out=True,
            )
        except Exception as e:
            return ExecutionResult(
                stdout="",
                stderr=str(e),
                exit_code=-1,
            )


class BubblewrapSandbox(BaseSandbox):
    """
    Linux sandbox using bubblewrap.

    Provides filesystem and network isolation via Linux namespaces.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        if platform.system() != "Linux":
            raise SandboxNotAvailableError("BubblewrapSandbox requires Linux")

        if not shutil.which("bwrap"):
            raise SandboxNotAvailableError(
                "bubblewrap not found. Install with:\n"
                "  Ubuntu/Debian: sudo apt install bubblewrap\n"
                "  Fedora: sudo dnf install bubblewrap\n"
                "  Arch: sudo pacman -S bubblewrap"
            )

    def _build_command(self, command: str) -> List[str]:
        """Build bwrap command with arguments."""
        args = [
            "bwrap",
            # Read-only system directories
            "--ro-bind",
            "/usr",
            "/usr",
            "--ro-bind",
            "/lib",
            "/lib",
            "--ro-bind",
            "/bin",
            "/bin",
            "--ro-bind",
            "/sbin",
            "/sbin",
            # Required virtual filesystems
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            # Temp directory
            "--tmpfs",
            "/tmp",
            # Working directory (read-write)
            "--bind",
            str(self.working_dir),
            str(self.working_dir),
            "--chdir",
            str(self.working_dir),
            # Isolation
            "--unshare-all",
            "--die-with-parent",
        ]

        # Handle /lib64 if it exists
        if Path("/lib64").exists():
            args.extend(["--ro-bind", "/lib64", "/lib64"])

        # Network isolation
        if not self.network:
            args.append("--unshare-net")

        # Additional allowed paths (read-only)
        for path in self.allowed_paths:
            resolved = Path(path).resolve()
            if resolved.exists():
                args.extend(["--ro-bind", str(resolved), str(resolved)])

        # Add common Python locations if they exist
        python_paths = [
            "/opt/anaconda3",
            "/opt/miniconda3",
            "/usr/local/lib/python3",
            Path.home() / ".local",
            Path.home() / ".pyenv",
        ]
        for p in python_paths:
            if Path(p).exists():
                args.extend(["--ro-bind", str(p), str(p)])

        # Command to execute
        args.extend(["--", "bash", "-c", command])

        return args

    def execute(self, command: str, timeout: Optional[int] = None) -> ExecutionResult:
        """Execute command in bubblewrap sandbox."""
        timeout = timeout or self.timeout
        bwrap_cmd = self._build_command(command)

        try:
            result = subprocess.run(
                bwrap_cmd,
                capture_output=True,
                timeout=timeout,
            )
            return ExecutionResult(
                stdout=result.stdout.decode("utf-8", errors="replace"),
                stderr=result.stderr.decode("utf-8", errors="replace"),
                exit_code=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                exit_code=-1,
                timed_out=True,
            )
        except Exception as e:
            return ExecutionResult(
                stdout="",
                stderr=str(e),
                exit_code=-1,
            )


class UnsandboxedExecutor(BaseSandbox):
    """
    Fallback executor without sandboxing.

    Used when no sandbox is available or sandboxing is disabled.
    WARNING: This provides no isolation - use with caution.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    def execute(self, command: str, timeout: Optional[int] = None) -> ExecutionResult:
        """Execute command without sandboxing."""
        timeout = timeout or self.timeout

        try:
            result = subprocess.run(
                ["bash", "-c", command],
                capture_output=True,
                timeout=timeout,
                cwd=str(self.working_dir),
            )
            return ExecutionResult(
                stdout=result.stdout.decode("utf-8", errors="replace"),
                stderr=result.stderr.decode("utf-8", errors="replace"),
                exit_code=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                exit_code=-1,
                timed_out=True,
            )
        except Exception as e:
            return ExecutionResult(
                stdout="",
                stderr=str(e),
                exit_code=-1,
            )


def _test_sandbox_works(sandbox: BaseSandbox) -> bool:
    """Test if a sandbox can execute a simple command."""
    try:
        result = sandbox.execute("echo test", timeout=5)
        return result.exit_code == 0 and "test" in result.stdout
    except Exception:
        return False


def create_sandbox(
    working_dir: str,
    allowed_paths: Optional[List[str]] = None,
    network: bool = False,
    timeout: int = 30,
    fallback_unsandboxed: bool = False,
) -> BaseSandbox:
    """
    Factory function to create appropriate sandbox for current OS.

    Args:
        working_dir: Directory for sandboxed file operations
        allowed_paths: Additional paths to allow read access
        network: Whether to allow network access
        timeout: Default command timeout in seconds
        fallback_unsandboxed: If True, use unsandboxed executor when sandbox unavailable

    Returns:
        Sandbox instance for current platform

    Raises:
        SandboxNotAvailableError: If no sandbox available and fallback not enabled
    """
    system = platform.system()
    kwargs = {
        "working_dir": working_dir,
        "allowed_paths": allowed_paths,
        "network": network,
        "timeout": timeout,
    }

    sandbox: Optional[BaseSandbox] = None

    if system == "Darwin":
        try:
            sandbox = SeatbeltSandbox(**kwargs)
            # Test if Seatbelt actually works (may fail due to SIP or environment)
            if not _test_sandbox_works(sandbox):
                sandbox = None
        except SandboxNotAvailableError:
            sandbox = None
    elif system == "Linux":
        try:
            sandbox = BubblewrapSandbox(**kwargs)
            if not _test_sandbox_works(sandbox):
                sandbox = None
        except SandboxNotAvailableError:
            sandbox = None

    if sandbox is not None:
        return sandbox

    if fallback_unsandboxed:
        return UnsandboxedExecutor(**kwargs)

    raise SandboxNotAvailableError(
        f"No working sandbox available for {system}. "
        "Supported platforms: Linux (bubblewrap), macOS (Seatbelt). "
        "Use fallback_unsandboxed=True to run without sandboxing."
    )


class SandboxFilesystemBackend:
    """
    Filesystem backend that operates within a sandbox.

    File operations go through the sandbox, and execute()
    runs commands in isolated environment.
    """

    def __init__(
        self,
        working_dir: str,
        network: bool = False,
        timeout: int = 30,
        fallback_unsandboxed: bool = False,
    ) -> None:
        """
        Initialize sandbox filesystem backend.

        Args:
            working_dir: Working directory for file operations
            network: Whether to allow network access
            timeout: Default command timeout
            fallback_unsandboxed: Use unsandboxed executor if sandbox unavailable
        """
        self.working_dir = Path(working_dir).resolve()
        self.working_dir.mkdir(parents=True, exist_ok=True)

        self.sandbox = create_sandbox(
            working_dir=str(self.working_dir),
            network=network,
            timeout=timeout,
            fallback_unsandboxed=fallback_unsandboxed,
        )

    def _resolve_path(self, path: str) -> str:
        """Resolve path relative to working directory."""
        if path.startswith("/"):
            path = path[1:]
        return str(self.working_dir / path)

    def ls(self, path: str = "/") -> Dict[str, Any]:
        """List directory contents via sandbox."""
        full_path = self._resolve_path(path)
        result = self.sandbox.execute(f'ls -la "{full_path}" 2>&1')

        if result.exit_code != 0:
            return {"error": result.stderr or result.stdout}

        return {
            "path": path,
            "listing": result.stdout,
        }

    def read_file(self, path: str, offset: int = 0, limit: int = 100) -> Dict[str, Any]:
        """Read file via sandbox."""
        full_path = self._resolve_path(path)

        # Use sed for pagination
        start_line = offset + 1
        end_line = offset + limit
        result = self.sandbox.execute(f'sed -n "{start_line},{end_line}p" "{full_path}" 2>&1')

        if result.exit_code != 0:
            return {"error": result.stderr or result.stdout}

        # Get total line count
        wc_result = self.sandbox.execute(f'wc -l < "{full_path}" 2>&1')
        total_lines = 0
        if wc_result.exit_code == 0:
            try:
                total_lines = int(wc_result.stdout.strip())
            except ValueError:
                pass

        # Add line numbers
        lines = result.stdout.split("\n")
        numbered = [
            f"{i + offset + 1:6d} | {line}"
            for i, line in enumerate(lines)
            if line or i < len(lines) - 1  # Skip trailing empty
        ]

        return {
            "path": path,
            "content": "\n".join(numbered),
            "lines_returned": len(numbered),
            "total_lines": total_lines,
            "offset": offset,
            "has_more": offset + limit < total_lines,
        }

    def write_file(self, path: str, content: str) -> Dict[str, Any]:
        """Write file via sandbox."""
        full_path = self._resolve_path(path)

        # Ensure parent directory exists
        parent = Path(full_path).parent
        self.sandbox.execute(f'mkdir -p "{parent}"')

        # Write using heredoc to handle special characters
        # Use a unique delimiter to avoid conflicts
        result = self.sandbox.execute(f"cat << 'VEL_HARNESS_EOF' > \"{full_path}\"\n{content}\nVEL_HARNESS_EOF")

        if result.exit_code != 0:
            return {"error": result.stderr or result.stdout}

        return {
            "status": "ok",
            "path": path,
            "lines": len(content.split("\n")),
        }

    def edit_file(self, path: str, old_text: str, new_text: str) -> Dict[str, Any]:
        """Edit file via sandbox."""
        full_path = self._resolve_path(path)

        # Read current content
        result = self.sandbox.execute(f'cat "{full_path}" 2>&1')

        if result.exit_code != 0:
            return {"error": f"Cannot read file: {result.stderr or result.stdout}"}

        content = result.stdout

        if old_text not in content:
            return {"error": "old_text not found in file"}

        if content.count(old_text) > 1:
            return {"error": "old_text appears multiple times. Must be unique."}

        new_content = content.replace(old_text, new_text)
        return self.write_file(path, new_content)

    def glob(self, pattern: str) -> Dict[str, Any]:
        """Find files matching pattern."""
        # Convert glob to find pattern
        result = self.sandbox.execute(
            f'find "{self.working_dir}" -name "{pattern.split("/")[-1]}" 2>/dev/null'
        )

        matches = [
            line.replace(str(self.working_dir), "")
            for line in result.stdout.strip().split("\n")
            if line
        ]

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
        """Search files via sandbox."""
        full_path = self._resolve_path(path)

        cmd = f'grep -rn "{pattern}" "{full_path}" 2>/dev/null'
        if include:
            cmd = f'grep -rn --include="{include}" "{pattern}" "{full_path}" 2>/dev/null'

        result = self.sandbox.execute(cmd)

        matches: List[Dict[str, Any]] = []
        total_matches = 0
        for line in result.stdout.strip().split("\n"):
            if line and ":" in line:
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    total_matches += 1
                    if len(matches) < head_limit:
                        matches.append(
                            {
                                "file": parts[0].replace(str(self.working_dir), ""),
                                "line": int(parts[1]) if parts[1].isdigit() else 0,
                                "content": parts[2].strip()[:500],  # Truncate long lines
                            }
                        )

        return {
            "pattern": pattern,
            "path": path,
            "matches": matches,
            "total_matches": total_matches,
            "head_limit": head_limit,
            "truncated": total_matches > head_limit,
        }

    def execute(self, command: str, timeout: Optional[int] = None) -> Dict[str, Any]:
        """Execute shell command in sandbox."""
        result = self.sandbox.execute(command, timeout)
        return result.to_dict()

    def execute_python(self, code: str, timeout: Optional[int] = None) -> Dict[str, Any]:
        """Execute Python code in sandbox."""
        result = self.sandbox.execute_python(code, timeout)
        return result.to_dict()
