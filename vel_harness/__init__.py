"""
Vel Harness - Claude Code-style Agent Framework

A production-ready agent harness built on Vel (agent runtime).
Provides Claude Code-style capabilities for deployment in containerized
environments (Kubernetes).

Primary API:
    from vel_harness import VelHarness

    harness = VelHarness(
        model={"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
        skill_dirs=["./skills"],
    )

    result = await harness.run("Analyze the codebase")

Features:
- Skills system with tool_result injection (preserves prompt caching)
- Subagent spawning with typed agents (default, explore, plan)
- Planning tools (TodoWrite)
- Context management with compaction
- Vercel AI SDK V5 streaming via Vel
"""

# Primary API - VelHarness
from vel_harness.harness import (
    VelHarness,
    create_harness,
    create_research_harness,
    create_coding_harness,
)

# Agent Registry
from vel_harness.agents import (
    AgentConfig,
    AgentDefinition,
    AgentRegistry,
)

# Approval Management
from vel_harness.approval import (
    ApprovalManager,
    PendingApproval,
)

# Legacy Factory (deprecated - use VelHarness instead)
from vel_harness.factory import (
    DeepAgent,
    create_deep_agent,
    create_research_agent,
    create_data_agent,
    create_coding_agent,
)

# Configuration
from vel_harness.config import (
    DeepAgentConfig,
    ModelConfig,
    SandboxConfig,
    DatabaseConfig,
    SkillsConfig,
    SubagentsConfig,
    PlanningConfig,
    FilesystemConfig,
    CachingConfig,
    RetryConfig,
)

# Hooks
from vel_harness.hooks import (
    HookEngine,
    HookMatcher,
    HookResult,
    PreToolUseEvent,
    PostToolUseEvent,
    PostToolUseFailureEvent,
)

# Reasoning
from vel_harness.reasoning import (
    ReasoningConfig,
    ReasoningDelimiters,
    PromptedReasoningParser,
)

# Fallback
from vel_harness.fallback import (
    FallbackStreamWrapper,
)

# Session
from vel_harness.session import (
    HarnessSession,
)

# Checkpoint
from vel_harness.checkpoint import (
    FileCheckpointManager,
    FileChange,
    Checkpoint,
)

# Middleware
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

# Backends
from vel_harness.backends.state import (
    StateFilesystemBackend,
)
from vel_harness.backends.protocol import (
    FilesystemBackend,
)
from vel_harness.backends.sandbox import (
    BaseSandbox,
    SandboxFilesystemBackend,
    SandboxNotAvailableError,
    ExecutionResult,
    create_sandbox,
)
from vel_harness.backends.database import (
    DatabaseBackend,
    MockDatabaseBackend,
    QueryResult,
)

# Skills
from vel_harness.skills import (
    Skill,
    SkillsRegistry,
)

# Subagents
from vel_harness.subagents import (
    SubagentSpawner,
    SubagentResult,
    SubagentConfig,
    SubagentStatus,
)

__version__ = "0.2.0"

__all__ = [
    # Version
    "__version__",
    # Primary API (VelHarness)
    "VelHarness",
    "create_harness",
    "create_research_harness",
    "create_coding_harness",
    # Agent Registry
    "AgentConfig",
    "AgentDefinition",
    "AgentRegistry",
    # Approval Management
    "ApprovalManager",
    "PendingApproval",
    # Legacy Factory (deprecated)
    "DeepAgent",
    "create_deep_agent",
    "create_research_agent",
    "create_data_agent",
    "create_coding_agent",
    # Configuration
    "DeepAgentConfig",
    "ModelConfig",
    "SandboxConfig",
    "DatabaseConfig",
    "SkillsConfig",
    "SubagentsConfig",
    "PlanningConfig",
    "FilesystemConfig",
    "CachingConfig",
    "RetryConfig",
    # Reasoning
    "ReasoningConfig",
    "ReasoningDelimiters",
    "PromptedReasoningParser",
    # Fallback
    "FallbackStreamWrapper",
    # Session
    "HarnessSession",
    # Checkpoint
    "FileCheckpointManager",
    "FileChange",
    "Checkpoint",
    # Middleware
    "PlanningMiddleware",
    "FilesystemMiddleware",
    "SandboxMiddleware",
    "SandboxFilesystemMiddleware",
    "DatabaseMiddleware",
    "SkillsMiddleware",
    "SubagentsMiddleware",
    # Backends
    "StateFilesystemBackend",
    "FilesystemBackend",
    "SandboxFilesystemBackend",
    "BaseSandbox",
    "SandboxNotAvailableError",
    "ExecutionResult",
    "create_sandbox",
    "DatabaseBackend",
    "MockDatabaseBackend",
    "QueryResult",
    # Skills
    "Skill",
    "SkillsRegistry",
    # Subagents
    "SubagentSpawner",
    "SubagentResult",
    "SubagentConfig",
    "SubagentStatus",
    # Data structures
    "TodoList",
    "TodoItem",
]
