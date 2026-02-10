"""
Remote Sandbox Backends

Support for cloud-based sandboxes: Modal, Runloop, and Daytona.
Provides secure, scalable code execution in remote environments.
"""

import asyncio
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RemoteSandboxConfig:
    """Configuration for remote sandbox."""

    provider: str  # "modal" | "runloop" | "daytona"
    api_key: Optional[str] = None
    sandbox_id: Optional[str] = None  # Reuse existing sandbox
    setup_script: Optional[str] = None  # Path to setup.sh
    timeout: int = 300  # 5 min default
    image: Optional[str] = None  # Container image
    memory_mb: int = 512
    cpu_count: float = 1.0
    environment: Dict[str, str] = field(default_factory=dict)


@dataclass
class RemoteExecutionResult:
    """Result from remote command execution."""

    stdout: str
    stderr: str
    exit_code: int
    success: bool
    execution_time: float = 0.0


class RemoteSandbox(ABC):
    """Abstract base for remote sandbox providers."""

    def __init__(self, config: RemoteSandboxConfig):
        self.config = config
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Check if sandbox is connected."""
        return self._connected

    @abstractmethod
    async def connect(self) -> None:
        """Connect to or create the sandbox."""
        pass

    @abstractmethod
    async def execute(
        self, command: str, timeout: Optional[int] = None
    ) -> RemoteExecutionResult:
        """Execute a command in the sandbox."""
        pass

    @abstractmethod
    async def read_file(self, path: str) -> str:
        """Read a file from the sandbox."""
        pass

    @abstractmethod
    async def write_file(self, path: str, content: str) -> None:
        """Write a file to the sandbox."""
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """Cleanup and terminate the sandbox."""
        pass

    async def execute_script(
        self, script_path: str, timeout: Optional[int] = None
    ) -> RemoteExecutionResult:
        """Execute a script file."""
        return await self.execute(f"bash {script_path}", timeout)

    async def run_setup(self) -> RemoteExecutionResult:
        """Run setup script if configured."""
        if not self.config.setup_script:
            return RemoteExecutionResult(
                stdout="No setup script configured",
                stderr="",
                exit_code=0,
                success=True,
            )

        if os.path.exists(self.config.setup_script):
            with open(self.config.setup_script) as f:
                script_content = f.read()
        else:
            script_content = self.config.setup_script

        return await self.execute(script_content, timeout=300)


class ModalSandbox(RemoteSandbox):
    """Modal.com sandbox integration.

    Modal provides serverless Python execution with fast cold starts
    and automatic scaling.
    """

    def __init__(self, config: RemoteSandboxConfig):
        super().__init__(config)
        self._sandbox = None
        self._app = None

    async def connect(self) -> None:
        """Create or connect to Modal sandbox."""
        try:
            import modal

            # Set API key if provided
            if self.config.api_key:
                os.environ["MODAL_TOKEN_ID"] = self.config.api_key

            if self.config.sandbox_id:
                # Reuse existing sandbox
                self._sandbox = await modal.Sandbox.from_id.aio(
                    self.config.sandbox_id
                )
            else:
                # Create new sandbox
                image = modal.Image.debian_slim()

                # Add Python if not specified
                if self.config.image:
                    image = modal.Image.from_registry(self.config.image)
                else:
                    image = image.pip_install("python3")

                self._sandbox = await modal.Sandbox.create.aio(
                    image=image,
                    timeout=self.config.timeout,
                    cpu=self.config.cpu_count,
                    memory=self.config.memory_mb,
                )

                # Run setup script if provided
                if self.config.setup_script:
                    await self.run_setup()

            self._connected = True
        except ImportError:
            raise ImportError(
                "Modal is not installed. Install with: pip install modal"
            )

    async def execute(
        self, command: str, timeout: Optional[int] = None
    ) -> RemoteExecutionResult:
        """Execute command in Modal sandbox."""
        if not self._connected or self._sandbox is None:
            await self.connect()

        import time

        start = time.time()

        try:
            result = await self._sandbox.exec.aio(
                "bash", "-c", command,
                timeout=timeout or self.config.timeout,
            )
            execution_time = time.time() - start

            return RemoteExecutionResult(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                success=result.returncode == 0,
                execution_time=execution_time,
            )
        except Exception as e:
            return RemoteExecutionResult(
                stdout="",
                stderr=str(e),
                exit_code=1,
                success=False,
                execution_time=time.time() - start,
            )

    async def read_file(self, path: str) -> str:
        """Read file from Modal sandbox."""
        result = await self.execute(f"cat {path}")
        if not result.success:
            raise FileNotFoundError(f"Cannot read {path}: {result.stderr}")
        return result.stdout

    async def write_file(self, path: str, content: str) -> None:
        """Write file to Modal sandbox using heredoc."""
        # Escape content for shell
        escaped = content.replace("'", "'\"'\"'")
        result = await self.execute(f"cat << 'MODAL_EOF' > {path}\n{content}\nMODAL_EOF")
        if not result.success:
            raise IOError(f"Cannot write {path}: {result.stderr}")

    async def cleanup(self) -> None:
        """Terminate Modal sandbox."""
        if self._sandbox:
            try:
                await self._sandbox.terminate.aio()
            except Exception:
                pass
        self._connected = False
        self._sandbox = None


class RunloopSandbox(RemoteSandbox):
    """Runloop sandbox integration.

    Runloop provides developer sandboxes with persistent state
    and IDE integration.
    """

    def __init__(self, config: RemoteSandboxConfig):
        super().__init__(config)
        self._client = None
        self._devbox = None

    async def connect(self) -> None:
        """Create or connect to Runloop devbox."""
        try:
            from runloop import Runloop

            api_key = self.config.api_key or os.environ.get("RUNLOOP_API_KEY")
            if not api_key:
                raise ValueError(
                    "Runloop API key required. Set RUNLOOP_API_KEY env var."
                )

            self._client = Runloop(api_key=api_key)

            if self.config.sandbox_id:
                # Connect to existing devbox
                self._devbox = await self._client.devboxes.get_async(
                    self.config.sandbox_id
                )
            else:
                # Create new devbox
                self._devbox = await self._client.devboxes.create_async()

                # Run setup if provided
                if self.config.setup_script:
                    await self.run_setup()

            self._connected = True
        except ImportError:
            raise ImportError(
                "Runloop is not installed. Install with: pip install runloop"
            )

    async def execute(
        self, command: str, timeout: Optional[int] = None
    ) -> RemoteExecutionResult:
        """Execute command in Runloop devbox."""
        if not self._connected or self._devbox is None:
            await self.connect()

        import time

        start = time.time()

        try:
            result = await self._devbox.run_command_async(
                command,
                timeout=timeout or self.config.timeout,
            )
            execution_time = time.time() - start

            return RemoteExecutionResult(
                stdout=result.stdout or "",
                stderr=result.stderr or "",
                exit_code=result.exit_code or 0,
                success=(result.exit_code or 0) == 0,
                execution_time=execution_time,
            )
        except Exception as e:
            return RemoteExecutionResult(
                stdout="",
                stderr=str(e),
                exit_code=1,
                success=False,
                execution_time=time.time() - start,
            )

    async def read_file(self, path: str) -> str:
        """Read file from Runloop devbox."""
        result = await self.execute(f"cat {path}")
        if not result.success:
            raise FileNotFoundError(f"Cannot read {path}: {result.stderr}")
        return result.stdout

    async def write_file(self, path: str, content: str) -> None:
        """Write file to Runloop devbox."""
        result = await self.execute(f"cat << 'RUNLOOP_EOF' > {path}\n{content}\nRUNLOOP_EOF")
        if not result.success:
            raise IOError(f"Cannot write {path}: {result.stderr}")

    async def cleanup(self) -> None:
        """Shutdown Runloop devbox."""
        if self._devbox:
            try:
                await self._devbox.shutdown_async()
            except Exception:
                pass
        self._connected = False
        self._devbox = None


class DaytonaSandbox(RemoteSandbox):
    """Daytona sandbox integration.

    Daytona provides developer workspaces with Git integration
    and IDE support.
    """

    def __init__(self, config: RemoteSandboxConfig):
        super().__init__(config)
        self._client = None
        self._workspace = None

    async def connect(self) -> None:
        """Create or connect to Daytona workspace."""
        try:
            from daytona_sdk import Daytona, DaytonaConfig

            api_key = self.config.api_key or os.environ.get("DAYTONA_API_KEY")
            base_url = os.environ.get("DAYTONA_BASE_URL", "https://api.daytona.io")

            daytona_config = DaytonaConfig(
                api_key=api_key,
                base_url=base_url,
            )
            self._client = Daytona(config=daytona_config)

            if self.config.sandbox_id:
                # Connect to existing workspace
                self._workspace = await self._client.workspaces.get_async(
                    self.config.sandbox_id
                )
            else:
                # Create new workspace
                self._workspace = await self._client.workspaces.create_async()

                # Run setup if provided
                if self.config.setup_script:
                    await self.run_setup()

            self._connected = True
        except ImportError:
            raise ImportError(
                "Daytona SDK is not installed. Install with: pip install daytona-sdk"
            )

    async def execute(
        self, command: str, timeout: Optional[int] = None
    ) -> RemoteExecutionResult:
        """Execute command in Daytona workspace."""
        if not self._connected or self._workspace is None:
            await self.connect()

        import time

        start = time.time()

        try:
            result = await self._workspace.exec_async(
                command,
                timeout=timeout or self.config.timeout,
            )
            execution_time = time.time() - start

            return RemoteExecutionResult(
                stdout=result.get("stdout", ""),
                stderr=result.get("stderr", ""),
                exit_code=result.get("exit_code", 0),
                success=result.get("exit_code", 0) == 0,
                execution_time=execution_time,
            )
        except Exception as e:
            return RemoteExecutionResult(
                stdout="",
                stderr=str(e),
                exit_code=1,
                success=False,
                execution_time=time.time() - start,
            )

    async def read_file(self, path: str) -> str:
        """Read file from Daytona workspace."""
        result = await self.execute(f"cat {path}")
        if not result.success:
            raise FileNotFoundError(f"Cannot read {path}: {result.stderr}")
        return result.stdout

    async def write_file(self, path: str, content: str) -> None:
        """Write file to Daytona workspace."""
        result = await self.execute(f"cat << 'DAYTONA_EOF' > {path}\n{content}\nDAYTONA_EOF")
        if not result.success:
            raise IOError(f"Cannot write {path}: {result.stderr}")

    async def cleanup(self) -> None:
        """Terminate Daytona workspace."""
        if self._workspace:
            try:
                await self._workspace.delete_async()
            except Exception:
                pass
        self._connected = False
        self._workspace = None


class MockRemoteSandbox(RemoteSandbox):
    """Mock remote sandbox for testing."""

    def __init__(self, config: RemoteSandboxConfig):
        super().__init__(config)
        self._files: Dict[str, str] = {}
        self._commands: List[str] = []

    async def connect(self) -> None:
        """Simulate connection."""
        self._connected = True

    async def execute(
        self, command: str, timeout: Optional[int] = None
    ) -> RemoteExecutionResult:
        """Execute command (mock)."""
        self._commands.append(command)

        # Simulate basic commands
        if command.startswith("echo "):
            output = command[5:].strip('"').strip("'")
            return RemoteExecutionResult(
                stdout=output + "\n",
                stderr="",
                exit_code=0,
                success=True,
            )
        elif command.startswith("cat "):
            path = command[4:].strip()
            if path in self._files:
                return RemoteExecutionResult(
                    stdout=self._files[path],
                    stderr="",
                    exit_code=0,
                    success=True,
                )
            return RemoteExecutionResult(
                stdout="",
                stderr=f"cat: {path}: No such file or directory",
                exit_code=1,
                success=False,
            )
        elif "<<" in command and ">" in command:
            # Heredoc write
            parts = command.split(">")
            if len(parts) >= 2:
                path = parts[1].split()[0].strip()
                content_start = command.find("<<")
                if content_start != -1:
                    # Extract content between heredoc markers
                    rest = command[content_start:]
                    lines = rest.split("\n")
                    if len(lines) > 1:
                        content = "\n".join(lines[1:-1])
                        self._files[path] = content
                        return RemoteExecutionResult(
                            stdout="",
                            stderr="",
                            exit_code=0,
                            success=True,
                        )

        return RemoteExecutionResult(
            stdout="mock execution",
            stderr="",
            exit_code=0,
            success=True,
        )

    async def read_file(self, path: str) -> str:
        """Read file (mock)."""
        if path in self._files:
            return self._files[path]
        raise FileNotFoundError(f"File not found: {path}")

    async def write_file(self, path: str, content: str) -> None:
        """Write file (mock)."""
        self._files[path] = content

    async def cleanup(self) -> None:
        """Cleanup (mock)."""
        self._connected = False
        self._files.clear()
        self._commands.clear()


def create_remote_sandbox(config: RemoteSandboxConfig) -> RemoteSandbox:
    """Factory for creating remote sandboxes.

    Args:
        config: Remote sandbox configuration

    Returns:
        Configured RemoteSandbox instance

    Raises:
        ValueError: If provider is unknown
    """
    provider = config.provider.lower()

    if provider == "modal":
        return ModalSandbox(config)
    elif provider == "runloop":
        return RunloopSandbox(config)
    elif provider == "daytona":
        return DaytonaSandbox(config)
    elif provider == "mock":
        return MockRemoteSandbox(config)
    else:
        raise ValueError(f"Unknown sandbox provider: {config.provider}")


async def create_and_connect_sandbox(
    provider: str,
    api_key: Optional[str] = None,
    setup_script: Optional[str] = None,
    **kwargs: Any,
) -> RemoteSandbox:
    """Create and connect to a remote sandbox.

    Args:
        provider: Sandbox provider (modal, runloop, daytona)
        api_key: API key for the provider
        setup_script: Optional setup script to run
        **kwargs: Additional configuration

    Returns:
        Connected RemoteSandbox instance
    """
    config = RemoteSandboxConfig(
        provider=provider,
        api_key=api_key,
        setup_script=setup_script,
        **kwargs,
    )
    sandbox = create_remote_sandbox(config)
    await sandbox.connect()
    return sandbox
