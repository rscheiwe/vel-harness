"""
Vel Harness Backends

Backend implementations for filesystem, sandbox execution, and database operations.
"""

from vel_harness.backends.protocol import (
    FilesystemBackend,
)
from vel_harness.backends.state import (
    StateFilesystemBackend,
    FileData,
)
from vel_harness.backends.sandbox import (
    BaseSandbox,
    SeatbeltSandbox,
    BubblewrapSandbox,
    UnsandboxedExecutor,
    SandboxFilesystemBackend,
    SandboxNotAvailableError,
    ExecutionResult,
    create_sandbox,
)
from vel_harness.backends.database import (
    DatabaseBackend,
    DatabaseConfig,
    DatabaseConnectionError,
    DatabaseNotAvailableError,
    DatabaseQueryError,
    MockDatabaseBackend,
    QueryResult,
    is_write_query,
)
from vel_harness.backends.composite import (
    CompositeBackend,
    PersistentStoreBackend,
    StorageBackend,
    RouteConfig,
    create_composite_backend,
)
from vel_harness.backends.sandbox_remote import (
    RemoteSandbox,
    RemoteSandboxConfig,
    RemoteExecutionResult,
    ModalSandbox,
    RunloopSandbox,
    DaytonaSandbox,
    MockRemoteSandbox,
    create_remote_sandbox,
    create_and_connect_sandbox,
)

__all__ = [
    "FilesystemBackend",
    "StateFilesystemBackend",
    "FileData",
    # Sandbox
    "BaseSandbox",
    "SeatbeltSandbox",
    "BubblewrapSandbox",
    "UnsandboxedExecutor",
    "SandboxFilesystemBackend",
    "SandboxNotAvailableError",
    "ExecutionResult",
    "create_sandbox",
    # Database
    "DatabaseBackend",
    "DatabaseConfig",
    "DatabaseConnectionError",
    "DatabaseNotAvailableError",
    "DatabaseQueryError",
    "MockDatabaseBackend",
    "QueryResult",
    "is_write_query",
    # Composite
    "CompositeBackend",
    "PersistentStoreBackend",
    "StorageBackend",
    "RouteConfig",
    "create_composite_backend",
    # Remote Sandbox
    "RemoteSandbox",
    "RemoteSandboxConfig",
    "RemoteExecutionResult",
    "ModalSandbox",
    "RunloopSandbox",
    "DaytonaSandbox",
    "MockRemoteSandbox",
    "create_remote_sandbox",
    "create_and_connect_sandbox",
]
