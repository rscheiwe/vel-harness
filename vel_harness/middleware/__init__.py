"""
Vel Harness Middleware

Middleware components that extend agent capabilities with planning,
filesystem access, skills, and subagent spawning.
"""

from vel_harness.middleware.planning import (
    PlanningMiddleware,
    TodoItem,
    TodoList,
)
from vel_harness.middleware.filesystem import (
    FilesystemMiddleware,
)
from vel_harness.middleware.sandbox import (
    SandboxMiddleware,
    SandboxFilesystemMiddleware,
)
from vel_harness.middleware.database import (
    DatabaseMiddleware,
)
from vel_harness.middleware.skills import (
    SkillsMiddleware,
)
from vel_harness.middleware.subagents import (
    SubagentsMiddleware,
)
from vel_harness.middleware.context import (
    ContextManagementMiddleware,
    ContextConfig,
    CompressionEvent,
    create_context_middleware,
)
from vel_harness.middleware.memory import (
    MemoryMiddleware,
    create_memory_middleware,
)
from vel_harness.middleware.caching import (
    AnthropicPromptCachingMiddleware,
    ToolCachingMiddleware,
    CacheConfig,
    CacheEntry,
    PromptCache,
    ToolResultCache,
    create_caching_middleware,
)
from vel_harness.middleware.retry import (
    ToolRetryMiddleware,
    RetryConfig,
    RetryResult,
    RetryAttempt,
    CircuitBreaker,
    CircuitBreakerMiddleware,
    create_retry_middleware,
)
from vel_harness.middleware.local_context import (
    LocalContextMiddleware,
)
from vel_harness.middleware.loop_detection import (
    LoopDetectionMiddleware,
)
from vel_harness.middleware.verification import (
    VerificationMiddleware,
)
from vel_harness.middleware.tracing import (
    TracingMiddleware,
    TraceEvent,
)
from vel_harness.middleware.time_budget import (
    TimeBudgetMiddleware,
)
from vel_harness.middleware.run_guard import (
    RunGuardMiddleware,
    RunGuardConfig,
)

__all__ = [
    "PlanningMiddleware",
    "FilesystemMiddleware",
    "SandboxMiddleware",
    "SandboxFilesystemMiddleware",
    "DatabaseMiddleware",
    "SkillsMiddleware",
    "SubagentsMiddleware",
    "TodoList",
    "TodoItem",
    # Context
    "ContextManagementMiddleware",
    "ContextConfig",
    "CompressionEvent",
    "create_context_middleware",
    # Memory
    "MemoryMiddleware",
    "create_memory_middleware",
    # Caching
    "AnthropicPromptCachingMiddleware",
    "ToolCachingMiddleware",
    "CacheConfig",
    "CacheEntry",
    "PromptCache",
    "ToolResultCache",
    "create_caching_middleware",
    # Retry
    "ToolRetryMiddleware",
    "RetryConfig",
    "RetryResult",
    "RetryAttempt",
    "CircuitBreaker",
    "CircuitBreakerMiddleware",
    "create_retry_middleware",
    # New harness-strengthening middlewares
    "LocalContextMiddleware",
    "LoopDetectionMiddleware",
    "VerificationMiddleware",
    "TracingMiddleware",
    "TraceEvent",
    "TimeBudgetMiddleware",
    "RunGuardMiddleware",
    "RunGuardConfig",
]
