"""
Tests for Remote Sandbox Backends
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from vel_harness.backends.sandbox_remote import (
    RemoteSandboxConfig,
    RemoteExecutionResult,
    RemoteSandbox,
    ModalSandbox,
    RunloopSandbox,
    DaytonaSandbox,
    MockRemoteSandbox,
    create_remote_sandbox,
    create_and_connect_sandbox,
)


class TestRemoteSandboxConfig:
    """Test RemoteSandboxConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = RemoteSandboxConfig(provider="modal")
        assert config.provider == "modal"
        assert config.timeout == 300
        assert config.memory_mb == 512
        assert config.cpu_count == 1.0
        assert config.api_key is None
        assert config.sandbox_id is None

    def test_custom_values(self):
        """Test custom configuration values."""
        config = RemoteSandboxConfig(
            provider="runloop",
            api_key="test-key",
            sandbox_id="sb-123",
            timeout=600,
            memory_mb=1024,
        )
        assert config.provider == "runloop"
        assert config.api_key == "test-key"
        assert config.sandbox_id == "sb-123"
        assert config.timeout == 600
        assert config.memory_mb == 1024


class TestRemoteExecutionResult:
    """Test RemoteExecutionResult dataclass."""

    def test_success_result(self):
        """Test successful execution result."""
        result = RemoteExecutionResult(
            stdout="Hello, World!",
            stderr="",
            exit_code=0,
            success=True,
            execution_time=0.5,
        )
        assert result.success
        assert result.exit_code == 0
        assert result.stdout == "Hello, World!"

    def test_failure_result(self):
        """Test failed execution result."""
        result = RemoteExecutionResult(
            stdout="",
            stderr="Command not found",
            exit_code=127,
            success=False,
        )
        assert not result.success
        assert result.exit_code == 127


class TestMockRemoteSandbox:
    """Test MockRemoteSandbox class."""

    @pytest.fixture
    def sandbox(self):
        """Create a mock sandbox."""
        config = RemoteSandboxConfig(provider="mock")
        return MockRemoteSandbox(config)

    @pytest.mark.asyncio
    async def test_connect(self, sandbox):
        """Test connecting to mock sandbox."""
        assert not sandbox.is_connected
        await sandbox.connect()
        assert sandbox.is_connected

    @pytest.mark.asyncio
    async def test_execute_echo(self, sandbox):
        """Test executing echo command."""
        await sandbox.connect()
        result = await sandbox.execute('echo "Hello"')
        assert result.success
        assert "Hello" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_cat_missing(self, sandbox):
        """Test reading missing file."""
        await sandbox.connect()
        result = await sandbox.execute("cat /missing.txt")
        assert not result.success
        assert "No such file" in result.stderr

    @pytest.mark.asyncio
    async def test_write_and_read_file(self, sandbox):
        """Test writing and reading files."""
        await sandbox.connect()

        # Write file
        await sandbox.write_file("/test.txt", "Hello, World!")

        # Read file
        content = await sandbox.read_file("/test.txt")
        assert content == "Hello, World!"

    @pytest.mark.asyncio
    async def test_read_missing_file(self, sandbox):
        """Test reading missing file raises error."""
        await sandbox.connect()

        with pytest.raises(FileNotFoundError):
            await sandbox.read_file("/missing.txt")

    @pytest.mark.asyncio
    async def test_cleanup(self, sandbox):
        """Test cleanup clears state."""
        await sandbox.connect()
        await sandbox.write_file("/test.txt", "content")

        await sandbox.cleanup()

        assert not sandbox.is_connected
        with pytest.raises(FileNotFoundError):
            await sandbox.read_file("/test.txt")


class TestCreateRemoteSandbox:
    """Test create_remote_sandbox factory."""

    def test_create_mock(self):
        """Test creating mock sandbox."""
        config = RemoteSandboxConfig(provider="mock")
        sandbox = create_remote_sandbox(config)
        assert isinstance(sandbox, MockRemoteSandbox)

    def test_create_modal(self):
        """Test creating Modal sandbox."""
        config = RemoteSandboxConfig(provider="modal")
        sandbox = create_remote_sandbox(config)
        assert isinstance(sandbox, ModalSandbox)

    def test_create_runloop(self):
        """Test creating Runloop sandbox."""
        config = RemoteSandboxConfig(provider="runloop")
        sandbox = create_remote_sandbox(config)
        assert isinstance(sandbox, RunloopSandbox)

    def test_create_daytona(self):
        """Test creating Daytona sandbox."""
        config = RemoteSandboxConfig(provider="daytona")
        sandbox = create_remote_sandbox(config)
        assert isinstance(sandbox, DaytonaSandbox)

    def test_create_unknown_raises(self):
        """Test creating unknown provider raises error."""
        config = RemoteSandboxConfig(provider="unknown")
        with pytest.raises(ValueError, match="Unknown sandbox provider"):
            create_remote_sandbox(config)


class TestCreateAndConnectSandbox:
    """Test create_and_connect_sandbox helper."""

    @pytest.mark.asyncio
    async def test_create_and_connect_mock(self):
        """Test creating and connecting mock sandbox."""
        sandbox = await create_and_connect_sandbox(provider="mock")
        assert sandbox.is_connected
        await sandbox.cleanup()


class TestModalSandbox:
    """Test ModalSandbox class."""

    @pytest.fixture
    def sandbox(self):
        """Create Modal sandbox."""
        config = RemoteSandboxConfig(provider="modal", api_key="test-key")
        return ModalSandbox(config)

    def test_init(self, sandbox):
        """Test initialization."""
        assert sandbox.config.provider == "modal"
        assert not sandbox.is_connected

    @pytest.mark.asyncio
    async def test_connect_without_modal(self, sandbox):
        """Test connect raises when modal not installed."""
        # Modal is likely not installed in test environment
        # This should raise ImportError
        with pytest.raises(ImportError, match="Modal is not installed"):
            await sandbox.connect()


class TestRunloopSandbox:
    """Test RunloopSandbox class."""

    @pytest.fixture
    def sandbox(self):
        """Create Runloop sandbox."""
        config = RemoteSandboxConfig(provider="runloop", api_key="test-key")
        return RunloopSandbox(config)

    def test_init(self, sandbox):
        """Test initialization."""
        assert sandbox.config.provider == "runloop"
        assert not sandbox.is_connected

    @pytest.mark.asyncio
    async def test_connect_without_runloop(self, sandbox):
        """Test connect raises when runloop not installed."""
        with pytest.raises(ImportError, match="Runloop is not installed"):
            await sandbox.connect()


class TestDaytonaSandbox:
    """Test DaytonaSandbox class."""

    @pytest.fixture
    def sandbox(self):
        """Create Daytona sandbox."""
        config = RemoteSandboxConfig(provider="daytona", api_key="test-key")
        return DaytonaSandbox(config)

    def test_init(self, sandbox):
        """Test initialization."""
        assert sandbox.config.provider == "daytona"
        assert not sandbox.is_connected

    @pytest.mark.asyncio
    async def test_connect_without_daytona(self, sandbox):
        """Test connect raises when daytona not installed."""
        with pytest.raises(ImportError, match="Daytona SDK is not installed"):
            await sandbox.connect()


class TestRemoteSandboxIntegration:
    """Integration tests for remote sandboxes."""

    @pytest.mark.asyncio
    async def test_full_workflow_mock(self):
        """Test full workflow with mock sandbox."""
        # Create and connect
        sandbox = await create_and_connect_sandbox(provider="mock")

        try:
            # Write a script
            await sandbox.write_file("/script.sh", "echo 'Hello from script'")

            # Execute command
            result = await sandbox.execute("echo 'Direct command'")
            assert result.success

            # Read file back
            content = await sandbox.read_file("/script.sh")
            assert "Hello from script" in content

        finally:
            await sandbox.cleanup()

    @pytest.mark.asyncio
    async def test_setup_script(self):
        """Test setup script execution."""
        config = RemoteSandboxConfig(
            provider="mock",
            setup_script="echo 'Setup complete'",
        )
        sandbox = MockRemoteSandbox(config)
        await sandbox.connect()

        result = await sandbox.run_setup()
        # Mock doesn't execute setup, just returns success
        assert result.success


class TestRemoteSandboxConfig:
    """Additional config tests."""

    def test_environment_variables(self):
        """Test environment configuration."""
        config = RemoteSandboxConfig(
            provider="modal",
            environment={"API_KEY": "secret", "DEBUG": "true"},
        )
        assert config.environment["API_KEY"] == "secret"
        assert config.environment["DEBUG"] == "true"

    def test_image_configuration(self):
        """Test custom image configuration."""
        config = RemoteSandboxConfig(
            provider="modal",
            image="python:3.11-slim",
        )
        assert config.image == "python:3.11-slim"
