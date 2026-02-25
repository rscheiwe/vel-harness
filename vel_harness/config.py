"""
Vel Harness Configuration

Configuration classes for deep agent creation.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Union

if TYPE_CHECKING:
    from vel_harness.reasoning import ReasoningConfig


@dataclass
class ModelConfig:
    """Model configuration."""

    provider: str = "anthropic"
    model: str = "claude-sonnet-4-5-20250929"
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for vel Agent."""
        d: Dict[str, Any] = {
            "provider": self.provider,
            "model": self.model,
        }
        if self.temperature is not None:
            d["temperature"] = self.temperature
        if self.max_tokens is not None:
            d["max_tokens"] = self.max_tokens
        return d


@dataclass
class SandboxConfig:
    """Sandbox execution configuration."""

    enabled: bool = True
    working_dir: Optional[str] = None
    network: bool = False
    timeout: int = 30
    allowed_paths: List[str] = field(default_factory=list)
    fallback_unsandboxed: bool = True
    # Agent SDK parity fields
    auto_allow_execute_if_sandboxed: bool = True
    excluded_commands: List[str] = field(default_factory=list)
    allowed_commands: List[str] = field(default_factory=list)
    network_allowed_hosts: List[str] = field(default_factory=list)
    max_output_size: int = 50_000


@dataclass
class DatabaseConfig:
    """Database configuration."""

    enabled: bool = False
    host: str = "localhost"
    port: int = 5432
    database: str = "postgres"
    user: str = "postgres"
    password: str = ""
    readonly: bool = True
    max_rows: int = 100
    timeout: float = 30.0


@dataclass
class SkillsConfig:
    """Skills system configuration."""

    enabled: bool = True
    skill_dirs: List[str] = field(default_factory=list)
    auto_activate: bool = True
    max_active_skills: int = 5
    discovery_mode: str = "entrypoint_only"


@dataclass
class SubagentsConfig:
    """Subagent configuration."""

    enabled: bool = True
    max_concurrent: int = 5
    max_turns: int = 10
    timeout: float = 300.0
    default_model: Optional[Dict[str, str]] = None


@dataclass
class ContextConfig:
    """Context management configuration."""

    enabled: bool = True
    # Phase 1: Truncation (immediate)
    truncate_threshold: int = 25_000
    truncate_head_lines: int = 50
    truncate_tail_lines: int = 20
    # Phase 2: Historical offload
    history_threshold: int = 8_000
    storage_path: str = "~/.vel_harness/ctx_storage"
    # Tier 2/3
    eviction_threshold: float = 0.85  # 85% of context window
    summarization_threshold: float = 0.95  # 95% of context window
    preserve_recent_messages: int = 20


@dataclass
class MemoryConfig:
    """Long-term memory configuration."""

    enabled: bool = True
    memories_path: str = "/memories/"
    agents_md_path: Optional[str] = None  # Defaults to {memories_path}AGENTS.md
    persistent_base_path: str = "~/.vel_harness/memories"


@dataclass
class CachingConfig:
    """Caching middleware configuration.

    Controls both Anthropic prompt caching (reduced latency) and
    tool result caching (avoid redundant calls).
    """

    enabled: bool = False
    prompt_cache_enabled: bool = True
    prompt_cache_ttl: int = 300  # 5 minutes
    tool_cache_enabled: bool = True
    tool_cache_ttl: int = 60  # 1 minute
    cacheable_tools: List[str] = field(default_factory=lambda: [
        "list_tables",
        "describe_table",
        "list_skills",
        "get_skill",
        "web_search",
    ])
    max_cache_size: int = 100


@dataclass
class RetryConfig:
    """Retry middleware configuration.

    Automatically retries failed tool calls with exponential backoff.
    Optionally includes a circuit breaker to prevent cascading failures.
    """

    enabled: bool = False
    max_retries: int = 2
    backoff_base: float = 1.0
    backoff_multiplier: float = 2.0
    use_circuit_breaker: bool = False
    circuit_failure_threshold: int = 5
    circuit_reset_timeout: float = 60.0


@dataclass
class LocalContextConfig:
    """Local environment context onboarding configuration."""

    enabled: bool = True
    max_entries: int = 40
    max_depth: int = 1
    detect_tools: List[str] = field(default_factory=lambda: [
        "python",
        "python3",
        "pytest",
        "uv",
        "npm",
        "pnpm",
        "node",
        "go",
        "cargo",
        "ruff",
        "mypy",
    ])


@dataclass
class LoopDetectionConfig:
    """Loop detection configuration."""

    enabled: bool = True
    file_edit_threshold: int = 4
    failure_streak_threshold: int = 3


@dataclass
class VerificationConfig:
    """Pre-completion verification configuration."""

    enabled: bool = True
    strict: bool = True
    max_followups: int = 2


@dataclass
class TracingConfig:
    """Structured tracing configuration."""

    enabled: bool = True
    emit_langfuse: bool = False
    telemetry_mode: str = "standard"


@dataclass
class ReasoningSchedulerConfig:
    """Phase-aware reasoning scheduler configuration."""

    enabled: bool = True
    planning_budget_tokens: int = 12_000
    build_budget_tokens: int = 5_000
    verify_budget_tokens: int = 15_000


@dataclass
class TimeBudgetConfig:
    """Execution time-budget controller configuration."""

    enabled: bool = True
    soft_limit_seconds: int = 240
    hard_limit_seconds: int = 300


@dataclass
class RunGuardConfig:
    """Deterministic runtime guardrail configuration."""

    enabled: bool = True
    max_tool_calls_total: int = 60
    max_tool_calls_per_tool: Dict[str, int] = field(default_factory=lambda: {
        "read_file": 30,
        "grep": 20,
        "glob": 20,
        "write_file": 20,
        "edit_file": 30,
        "spawn_subagent": 10,
        "spawn_parallel": 6,
        "run_subagent_workflow": 4,
    })
    max_same_tool_input_repeats: int = 4
    max_failure_streak: int = 6
    max_subagent_rounds: int = 8
    max_parallel_subagents: int = 5
    require_verification_before_done: bool = True
    verification_tool_names: List[str] = field(default_factory=lambda: [
        "execute",
        "execute_python",
        "sql_query",
        "wait_subagent",
        "wait_all_subagents",
    ])
    completion_required_paths: List[str] = field(default_factory=list)
    completion_required_patterns: List[str] = field(default_factory=list)
    max_discovery_rounds_by_class: Dict[str, int] = field(default_factory=lambda: {
        "data_retrieval": 4,
        "workflow_resolution": 4,
        "code_change": 4,
        "general": 3,
    })
    max_repeated_identical_execute: int = 3
    enforce_query_evidence_for_numeric_claims: bool = True


@dataclass
class PlanningConfig:
    """Planning middleware configuration."""

    enabled: bool = True


@dataclass
class FilesystemConfig:
    """Filesystem middleware configuration."""

    enabled: bool = True
    use_sandbox: bool = True  # If True, use sandbox filesystem


@dataclass
class DeepAgentConfig:
    """
    Complete configuration for a deep agent.

    This configuration brings together all middleware components
    to create a fully-featured agent.
    """

    # Core
    name: str = "deep-agent"
    model: ModelConfig = field(default_factory=ModelConfig)
    system_prompt: Optional[str] = None
    tool_input_rewriters: List[Callable[..., Any]] = field(default_factory=list)

    # Middleware
    planning: PlanningConfig = field(default_factory=PlanningConfig)
    filesystem: FilesystemConfig = field(default_factory=FilesystemConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    skills: SkillsConfig = field(default_factory=SkillsConfig)
    subagents: SubagentsConfig = field(default_factory=SubagentsConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    caching: CachingConfig = field(default_factory=CachingConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    local_context: LocalContextConfig = field(default_factory=LocalContextConfig)
    loop_detection: LoopDetectionConfig = field(default_factory=LoopDetectionConfig)
    verification: VerificationConfig = field(default_factory=VerificationConfig)
    tracing: TracingConfig = field(default_factory=TracingConfig)
    reasoning: Any = None  # ReasoningConfig, set via from_dict or VelHarness
    reasoning_scheduler: ReasoningSchedulerConfig = field(default_factory=ReasoningSchedulerConfig)
    time_budget: TimeBudgetConfig = field(default_factory=TimeBudgetConfig)
    run_guard: RunGuardConfig = field(default_factory=RunGuardConfig)

    # Agent policies
    max_turns: int = 50
    retry_attempts: int = 2

    # Fallback model
    fallback_model: Optional[Dict[str, Any]] = None
    max_fallback_retries: int = 1

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeepAgentConfig":
        """Create config from dictionary."""
        config = cls()

        # Core settings
        if "name" in data:
            config.name = data["name"]
        if "system_prompt" in data:
            config.system_prompt = data["system_prompt"]
        if "max_turns" in data:
            config.max_turns = data["max_turns"]

        # Model
        if "model" in data:
            model_data = data["model"]
            if isinstance(model_data, dict):
                config.model = ModelConfig(
                    provider=model_data.get("provider", "anthropic"),
                    model=model_data.get("model", "claude-sonnet-4-5-20250929"),
                    temperature=model_data.get("temperature"),
                    max_tokens=model_data.get("max_tokens"),
                )

        # Planning
        if "planning" in data:
            planning_data = data["planning"]
            if isinstance(planning_data, dict):
                config.planning = PlanningConfig(
                    enabled=planning_data.get("enabled", True),
                )
            elif isinstance(planning_data, bool):
                config.planning = PlanningConfig(enabled=planning_data)

        # Filesystem
        if "filesystem" in data:
            fs_data = data["filesystem"]
            if isinstance(fs_data, dict):
                config.filesystem = FilesystemConfig(
                    enabled=fs_data.get("enabled", True),
                    use_sandbox=fs_data.get("use_sandbox", True),
                )
            elif isinstance(fs_data, bool):
                config.filesystem = FilesystemConfig(enabled=fs_data)

        # Sandbox
        if "sandbox" in data:
            sb_data = data["sandbox"]
            if isinstance(sb_data, dict):
                config.sandbox = SandboxConfig(
                    enabled=sb_data.get("enabled", True),
                    working_dir=sb_data.get("working_dir"),
                    network=sb_data.get("network", False),
                    timeout=sb_data.get("timeout", 30),
                    allowed_paths=sb_data.get("allowed_paths", []),
                    fallback_unsandboxed=sb_data.get("fallback_unsandboxed", True),
                    auto_allow_execute_if_sandboxed=sb_data.get("auto_allow_execute_if_sandboxed", True),
                    excluded_commands=sb_data.get("excluded_commands", []),
                    allowed_commands=sb_data.get("allowed_commands", []),
                    network_allowed_hosts=sb_data.get("network_allowed_hosts", []),
                    max_output_size=sb_data.get("max_output_size", 50_000),
                )
            elif isinstance(sb_data, bool):
                config.sandbox = SandboxConfig(enabled=sb_data)

        # Database
        if "database" in data:
            db_data = data["database"]
            if isinstance(db_data, dict):
                config.database = DatabaseConfig(
                    enabled=db_data.get("enabled", False),
                    host=db_data.get("host", "localhost"),
                    port=db_data.get("port", 5432),
                    database=db_data.get("database", "postgres"),
                    user=db_data.get("user", "postgres"),
                    password=db_data.get("password", ""),
                    readonly=db_data.get("readonly", True),
                    max_rows=db_data.get("max_rows", 100),
                    timeout=db_data.get("timeout", 30.0),
                )
            elif isinstance(db_data, bool):
                config.database = DatabaseConfig(enabled=db_data)

        # Skills
        if "skills" in data:
            skills_data = data["skills"]
            if isinstance(skills_data, dict):
                config.skills = SkillsConfig(
                    enabled=skills_data.get("enabled", True),
                    skill_dirs=skills_data.get("skill_dirs", []),
                    auto_activate=skills_data.get("auto_activate", True),
                    max_active_skills=skills_data.get("max_active_skills", 5),
                    discovery_mode=skills_data.get("discovery_mode", "entrypoint_only"),
                )
            elif isinstance(skills_data, bool):
                config.skills = SkillsConfig(enabled=skills_data)

        # Subagents
        if "subagents" in data:
            sa_data = data["subagents"]
            if isinstance(sa_data, dict):
                config.subagents = SubagentsConfig(
                    enabled=sa_data.get("enabled", True),
                    max_concurrent=sa_data.get("max_concurrent", 5),
                    max_turns=sa_data.get("max_turns", 10),
                    timeout=sa_data.get("timeout", 300.0),
                    default_model=sa_data.get("default_model"),
                )
            elif isinstance(sa_data, bool):
                config.subagents = SubagentsConfig(enabled=sa_data)

        # Context
        if "context" in data:
            ctx_data = data["context"]
            if isinstance(ctx_data, dict):
                config.context = ContextConfig(
                    enabled=ctx_data.get("enabled", True),
                    truncate_threshold=ctx_data.get("truncate_threshold", 25_000),
                    truncate_head_lines=ctx_data.get("truncate_head_lines", 50),
                    truncate_tail_lines=ctx_data.get("truncate_tail_lines", 20),
                    history_threshold=ctx_data.get("history_threshold", 8_000),
                    storage_path=ctx_data.get("storage_path", "~/.vel_harness/ctx_storage"),
                    eviction_threshold=ctx_data.get("eviction_threshold", 0.85),
                    summarization_threshold=ctx_data.get("summarization_threshold", 0.95),
                    preserve_recent_messages=ctx_data.get("preserve_recent_messages", 20),
                )
            elif isinstance(ctx_data, bool):
                config.context = ContextConfig(enabled=ctx_data)

        # Memory
        if "memory" in data:
            mem_data = data["memory"]
            if isinstance(mem_data, dict):
                config.memory = MemoryConfig(
                    enabled=mem_data.get("enabled", True),
                    memories_path=mem_data.get("memories_path", "/memories/"),
                    agents_md_path=mem_data.get("agents_md_path"),
                    persistent_base_path=mem_data.get("persistent_base_path", "~/.vel_harness/memories"),
                )
            elif isinstance(mem_data, bool):
                config.memory = MemoryConfig(enabled=mem_data)

        # Caching
        if "caching" in data:
            cache_data = data["caching"]
            if isinstance(cache_data, dict):
                config.caching = CachingConfig(
                    enabled=cache_data.get("enabled", False),
                    prompt_cache_enabled=cache_data.get("prompt_cache_enabled", True),
                    prompt_cache_ttl=cache_data.get("prompt_cache_ttl", 300),
                    tool_cache_enabled=cache_data.get("tool_cache_enabled", True),
                    tool_cache_ttl=cache_data.get("tool_cache_ttl", 60),
                    cacheable_tools=cache_data.get("cacheable_tools", [
                        "list_tables", "describe_table", "list_skills",
                        "get_skill", "web_search",
                    ]),
                    max_cache_size=cache_data.get("max_cache_size", 100),
                )
            elif isinstance(cache_data, bool):
                config.caching = CachingConfig(enabled=cache_data)

        # Retry
        if "retry" in data:
            retry_data = data["retry"]
            if isinstance(retry_data, dict):
                config.retry = RetryConfig(
                    enabled=retry_data.get("enabled", False),
                    max_retries=retry_data.get("max_retries", 2),
                    backoff_base=retry_data.get("backoff_base", 1.0),
                    backoff_multiplier=retry_data.get("backoff_multiplier", 2.0),
                    use_circuit_breaker=retry_data.get("use_circuit_breaker", False),
                    circuit_failure_threshold=retry_data.get("circuit_failure_threshold", 5),
                    circuit_reset_timeout=retry_data.get("circuit_reset_timeout", 60.0),
                )
            elif isinstance(retry_data, bool):
                config.retry = RetryConfig(enabled=retry_data)

        # Local context
        if "local_context" in data:
            lc_data = data["local_context"]
            if isinstance(lc_data, dict):
                config.local_context = LocalContextConfig(
                    enabled=lc_data.get("enabled", True),
                    max_entries=lc_data.get("max_entries", 40),
                    max_depth=lc_data.get("max_depth", 1),
                    detect_tools=lc_data.get("detect_tools", LocalContextConfig().detect_tools),
                )
            elif isinstance(lc_data, bool):
                config.local_context = LocalContextConfig(enabled=lc_data)

        # Loop detection
        if "loop_detection" in data:
            ld_data = data["loop_detection"]
            if isinstance(ld_data, dict):
                config.loop_detection = LoopDetectionConfig(
                    enabled=ld_data.get("enabled", True),
                    file_edit_threshold=ld_data.get("file_edit_threshold", 4),
                    failure_streak_threshold=ld_data.get("failure_streak_threshold", 3),
                )
            elif isinstance(ld_data, bool):
                config.loop_detection = LoopDetectionConfig(enabled=ld_data)

        # Verification
        if "verification" in data:
            v_data = data["verification"]
            if isinstance(v_data, dict):
                config.verification = VerificationConfig(
                    enabled=v_data.get("enabled", True),
                    strict=v_data.get("strict", True),
                    max_followups=v_data.get("max_followups", 2),
                )
            elif isinstance(v_data, bool):
                config.verification = VerificationConfig(enabled=v_data)

        # Tracing
        if "tracing" in data:
            t_data = data["tracing"]
            if isinstance(t_data, dict):
                config.tracing = TracingConfig(
                    enabled=t_data.get("enabled", True),
                    emit_langfuse=t_data.get("emit_langfuse", False),
                    telemetry_mode=t_data.get("telemetry_mode", "standard"),
                )
            elif isinstance(t_data, bool):
                config.tracing = TracingConfig(enabled=t_data)

        # Reasoning
        if "reasoning" in data:
            from vel_harness.reasoning import ReasoningConfig as RC

            config.reasoning = RC.from_value(data["reasoning"])

        # Reasoning scheduler
        if "reasoning_scheduler" in data:
            rs_data = data["reasoning_scheduler"]
            if isinstance(rs_data, dict):
                config.reasoning_scheduler = ReasoningSchedulerConfig(
                    enabled=rs_data.get("enabled", True),
                    planning_budget_tokens=rs_data.get("planning_budget_tokens", 12_000),
                    build_budget_tokens=rs_data.get("build_budget_tokens", 5_000),
                    verify_budget_tokens=rs_data.get("verify_budget_tokens", 15_000),
                )
            elif isinstance(rs_data, bool):
                config.reasoning_scheduler = ReasoningSchedulerConfig(enabled=rs_data)

        # Time budget
        if "time_budget" in data:
            tb_data = data["time_budget"]
            if isinstance(tb_data, dict):
                config.time_budget = TimeBudgetConfig(
                    enabled=tb_data.get("enabled", True),
                    soft_limit_seconds=tb_data.get("soft_limit_seconds", 240),
                    hard_limit_seconds=tb_data.get("hard_limit_seconds", 300),
                )
            elif isinstance(tb_data, bool):
                config.time_budget = TimeBudgetConfig(enabled=tb_data)

        # Run guard
        if "run_guard" in data:
            rg_data = data["run_guard"]
            if isinstance(rg_data, dict):
                config.run_guard = RunGuardConfig(
                    enabled=rg_data.get("enabled", True),
                    max_tool_calls_total=rg_data.get("max_tool_calls_total", 60),
                    max_tool_calls_per_tool=rg_data.get("max_tool_calls_per_tool", RunGuardConfig().max_tool_calls_per_tool),
                    max_same_tool_input_repeats=rg_data.get("max_same_tool_input_repeats", 4),
                    max_failure_streak=rg_data.get("max_failure_streak", 6),
                    max_subagent_rounds=rg_data.get("max_subagent_rounds", 8),
                    max_parallel_subagents=rg_data.get("max_parallel_subagents", 5),
                    require_verification_before_done=rg_data.get("require_verification_before_done", True),
                    verification_tool_names=rg_data.get("verification_tool_names", RunGuardConfig().verification_tool_names),
                    completion_required_paths=rg_data.get("completion_required_paths", []),
                    completion_required_patterns=rg_data.get("completion_required_patterns", []),
                    max_discovery_rounds_by_class=rg_data.get(
                        "max_discovery_rounds_by_class",
                        RunGuardConfig().max_discovery_rounds_by_class,
                    ),
                    max_repeated_identical_execute=rg_data.get("max_repeated_identical_execute", 3),
                    enforce_query_evidence_for_numeric_claims=rg_data.get(
                        "enforce_query_evidence_for_numeric_claims", True
                    ),
                )
            elif isinstance(rg_data, bool):
                config.run_guard = RunGuardConfig(enabled=rg_data)

        # Fallback model
        if "fallback_model" in data:
            fm = data["fallback_model"]
            if isinstance(fm, str):
                # String shorthand — resolve model name
                from vel_harness.agents.config import AgentDefinition

                config.fallback_model = AgentDefinition._resolve_model(fm)
            elif isinstance(fm, dict):
                config.fallback_model = fm
        if "max_fallback_retries" in data:
            config.max_fallback_retries = data["max_fallback_retries"]

        return config

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "name": self.name,
            "model": self.model.to_dict(),
            "system_prompt": self.system_prompt,
            "max_turns": self.max_turns,
            "planning": {"enabled": self.planning.enabled},
            "filesystem": {
                "enabled": self.filesystem.enabled,
                "use_sandbox": self.filesystem.use_sandbox,
            },
            "sandbox": {
                "enabled": self.sandbox.enabled,
                "working_dir": self.sandbox.working_dir,
                "network": self.sandbox.network,
                "timeout": self.sandbox.timeout,
                "allowed_paths": self.sandbox.allowed_paths,
                "fallback_unsandboxed": self.sandbox.fallback_unsandboxed,
                "auto_allow_execute_if_sandboxed": self.sandbox.auto_allow_execute_if_sandboxed,
                "excluded_commands": self.sandbox.excluded_commands,
                "allowed_commands": self.sandbox.allowed_commands,
                "network_allowed_hosts": self.sandbox.network_allowed_hosts,
                "max_output_size": self.sandbox.max_output_size,
            },
            "database": {
                "enabled": self.database.enabled,
                "readonly": self.database.readonly,
            },
            "skills": {
                "enabled": self.skills.enabled,
                "skill_dirs": self.skills.skill_dirs,
                "auto_activate": self.skills.auto_activate,
                "max_active_skills": self.skills.max_active_skills,
                "discovery_mode": self.skills.discovery_mode,
            },
            "subagents": {
                "enabled": self.subagents.enabled,
                "max_concurrent": self.subagents.max_concurrent,
            },
            "context": {
                "enabled": self.context.enabled,
                "truncate_threshold": self.context.truncate_threshold,
                "history_threshold": self.context.history_threshold,
                "eviction_threshold": self.context.eviction_threshold,
                "summarization_threshold": self.context.summarization_threshold,
            },
            "memory": {
                "enabled": self.memory.enabled,
                "memories_path": self.memory.memories_path,
            },
            "caching": {
                "enabled": self.caching.enabled,
                "prompt_cache_enabled": self.caching.prompt_cache_enabled,
                "prompt_cache_ttl": self.caching.prompt_cache_ttl,
                "tool_cache_enabled": self.caching.tool_cache_enabled,
                "tool_cache_ttl": self.caching.tool_cache_ttl,
                "cacheable_tools": self.caching.cacheable_tools,
                "max_cache_size": self.caching.max_cache_size,
            },
            "retry": {
                "enabled": self.retry.enabled,
                "max_retries": self.retry.max_retries,
                "backoff_base": self.retry.backoff_base,
                "backoff_multiplier": self.retry.backoff_multiplier,
                "use_circuit_breaker": self.retry.use_circuit_breaker,
                "circuit_failure_threshold": self.retry.circuit_failure_threshold,
                "circuit_reset_timeout": self.retry.circuit_reset_timeout,
            },
            "local_context": {
                "enabled": self.local_context.enabled,
                "max_entries": self.local_context.max_entries,
                "max_depth": self.local_context.max_depth,
                "detect_tools": self.local_context.detect_tools,
            },
            "loop_detection": {
                "enabled": self.loop_detection.enabled,
                "file_edit_threshold": self.loop_detection.file_edit_threshold,
                "failure_streak_threshold": self.loop_detection.failure_streak_threshold,
            },
            "verification": {
                "enabled": self.verification.enabled,
                "strict": self.verification.strict,
                "max_followups": self.verification.max_followups,
            },
            "tracing": {
                "enabled": self.tracing.enabled,
                "emit_langfuse": self.tracing.emit_langfuse,
                "telemetry_mode": self.tracing.telemetry_mode,
            },
            "reasoning": {
                "mode": self.reasoning.mode if self.reasoning else "none",
            } if self.reasoning else None,
            "reasoning_scheduler": {
                "enabled": self.reasoning_scheduler.enabled,
                "planning_budget_tokens": self.reasoning_scheduler.planning_budget_tokens,
                "build_budget_tokens": self.reasoning_scheduler.build_budget_tokens,
                "verify_budget_tokens": self.reasoning_scheduler.verify_budget_tokens,
            },
            "time_budget": {
                "enabled": self.time_budget.enabled,
                "soft_limit_seconds": self.time_budget.soft_limit_seconds,
                "hard_limit_seconds": self.time_budget.hard_limit_seconds,
            },
            "run_guard": {
                "enabled": self.run_guard.enabled,
                "max_tool_calls_total": self.run_guard.max_tool_calls_total,
                "max_tool_calls_per_tool": self.run_guard.max_tool_calls_per_tool,
                "max_same_tool_input_repeats": self.run_guard.max_same_tool_input_repeats,
                "max_failure_streak": self.run_guard.max_failure_streak,
                "max_subagent_rounds": self.run_guard.max_subagent_rounds,
                "max_parallel_subagents": self.run_guard.max_parallel_subagents,
                "require_verification_before_done": self.run_guard.require_verification_before_done,
                "verification_tool_names": self.run_guard.verification_tool_names,
                "completion_required_paths": self.run_guard.completion_required_paths,
                "completion_required_patterns": self.run_guard.completion_required_patterns,
                "max_discovery_rounds_by_class": self.run_guard.max_discovery_rounds_by_class,
                "max_repeated_identical_execute": self.run_guard.max_repeated_identical_execute,
                "enforce_query_evidence_for_numeric_claims": (
                    self.run_guard.enforce_query_evidence_for_numeric_claims
                ),
            },
            "fallback_model": self.fallback_model,
            "max_fallback_retries": self.max_fallback_retries,
        }
