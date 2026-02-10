"""
Valis CLI Configuration

Settings, paths, and project detection.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import json


# Default paths
DEFAULT_GLOBAL_DIR = Path.home() / ".valis"
DEFAULT_PROJECT_DIR = ".valis"
DEFAULT_MEMORIES_DIR = "memories"
DEFAULT_SKILLS_DIR = "skills"
DEFAULT_AGENTS_FILE = "AGENTS.md"
DEFAULT_CONFIG_FILE = "config.json"
DEFAULT_SESSION_FILE = "session.json"
DEFAULT_SETTINGS_FILE = "settings.local.json"  # Like Claude Code's settings


@dataclass
class ModelSettings:
    """Model configuration settings."""

    provider: str = "anthropic"
    model: str = "claude-sonnet-4-5-20250929"
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for agent creation."""
        d = {"provider": self.provider, "model": self.model}
        if self.temperature is not None:
            d["temperature"] = self.temperature
        if self.max_tokens is not None:
            d["max_tokens"] = self.max_tokens
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelSettings":
        """Create from dictionary."""
        return cls(
            provider=data.get("provider", "anthropic"),
            model=data.get("model", "claude-sonnet-4-5-20250929"),
            temperature=data.get("temperature"),
            max_tokens=data.get("max_tokens"),
        )


@dataclass
class ApprovalSettings:
    """Tool approval settings."""

    require_approval: bool = True
    auto_approve: List[str] = field(default_factory=lambda: [
        # Only truly safe read-only tools (like Claude Code)
        "glob",
        "grep",
        "list_tables",
        "describe_table",
        "list_skills",
        "get_skill",
        "list_memories",
        "search_memories",
        # Note: read_file, ls, write_file, edit_file, execute etc require approval
    ])
    always_deny: List[str] = field(default_factory=list)


@dataclass
class Permissions:
    """
    Tool permissions like Claude Code's settings.local.json.

    Supports pattern matching (like Claude Code):
    - "read_file" - exact tool name match
    - "read_file(*)" - tool name with any args
    - "execute(command=python*)" - match specific arg patterns
    - "Bash(pip install:*)" - Claude Code style with arg prefix
    """

    allow: List[str] = field(default_factory=list)
    deny: List[str] = field(default_factory=list)
    ask: List[str] = field(default_factory=list)

    def matches_pattern(self, tool_name: str, args: Dict[str, Any], pattern: str) -> bool:
        """Check if tool call matches a permission pattern."""
        import fnmatch
        import re

        # Parse pattern: tool_name or tool_name(args_pattern)
        match = re.match(r'^([^(]+)(?:\(([^)]*)\))?$', pattern)
        if not match:
            return False

        pattern_name = match.group(1)
        pattern_args = match.group(2)

        # Match tool name (supports wildcards)
        if not fnmatch.fnmatch(tool_name, pattern_name):
            return False

        # If no args pattern, tool name match is enough
        if pattern_args is None:
            return True

        # Match args pattern
        if pattern_args == '*':
            # Any args
            return True

        # Check if pattern_args contains '=' (key=value format)
        if '=' in pattern_args:
            # Parse key=pattern pairs
            for arg_pattern in pattern_args.split(','):
                arg_pattern = arg_pattern.strip()
                if '=' in arg_pattern:
                    key, val_pattern = arg_pattern.split('=', 1)
                    key = key.strip()
                    val_pattern = val_pattern.strip()
                    if key in args:
                        arg_val = str(args[key])
                        if not fnmatch.fnmatch(arg_val, val_pattern):
                            return False
                    else:
                        return False
            return True
        else:
            # Claude Code style: pattern is a prefix for first arg value
            # e.g., "Bash(pip install:*)" matches Bash with command starting with "pip install"
            # Check against all string arg values
            for val in args.values():
                if isinstance(val, str):
                    if fnmatch.fnmatch(val, pattern_args):
                        return True
            return False

    def check_permission(
        self,
        tool_name: str,
        args: Dict[str, Any],
    ) -> Optional[str]:
        """
        Check permission for a tool call.

        Args:
            tool_name: Name of the tool
            args: Tool arguments

        Returns:
            "allow", "deny", "ask", or None if no matching rule
        """
        # Check deny first (highest priority)
        for pattern in self.deny:
            if self.matches_pattern(tool_name, args, pattern):
                return "deny"

        # Check allow
        for pattern in self.allow:
            if self.matches_pattern(tool_name, args, pattern):
                return "allow"

        # Check ask
        for pattern in self.ask:
            if self.matches_pattern(tool_name, args, pattern):
                return "ask"

        return None

    def add_allow(self, pattern: str) -> None:
        """Add a pattern to allow list."""
        if pattern not in self.allow:
            self.allow.append(pattern)
            # Remove from other lists
            if pattern in self.deny:
                self.deny.remove(pattern)
            if pattern in self.ask:
                self.ask.remove(pattern)

    def add_deny(self, pattern: str) -> None:
        """Add a pattern to deny list."""
        if pattern not in self.deny:
            self.deny.append(pattern)
            # Remove from other lists
            if pattern in self.allow:
                self.allow.remove(pattern)
            if pattern in self.ask:
                self.ask.remove(pattern)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "allow": self.allow,
            "deny": self.deny,
            "ask": self.ask,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Permissions":
        """Create from dictionary."""
        return cls(
            allow=data.get("allow", []),
            deny=data.get("deny", []),
            ask=data.get("ask", []),
        )


@dataclass
class Config:
    """Complete CLI configuration."""

    # Paths
    global_dir: Path = field(default_factory=lambda: DEFAULT_GLOBAL_DIR)
    project_dir: Optional[Path] = None

    # Model
    model: ModelSettings = field(default_factory=ModelSettings)

    # Approval
    approval: ApprovalSettings = field(default_factory=ApprovalSettings)

    # Agent settings
    agent_name: str = "valis-agent"
    max_turns: int = 50
    sandbox_enabled: bool = False  # Use real filesystem by default
    database_enabled: bool = False

    # UI settings
    show_thinking: bool = False
    show_tool_calls: bool = True
    compact_mode: bool = False

    # Session
    session_id: Optional[str] = None

    def __post_init__(self):
        """Ensure paths are Path objects."""
        if isinstance(self.global_dir, str):
            self.global_dir = Path(self.global_dir)
        if isinstance(self.project_dir, str):
            self.project_dir = Path(self.project_dir)

    @property
    def memories_dir(self) -> Path:
        """Get memories directory (project or global)."""
        if self.project_dir and (self.project_dir / DEFAULT_MEMORIES_DIR).exists():
            return self.project_dir / DEFAULT_MEMORIES_DIR
        return self.global_dir / DEFAULT_MEMORIES_DIR

    @property
    def skills_dir(self) -> Path:
        """Get skills directory (project or global)."""
        if self.project_dir and (self.project_dir / DEFAULT_SKILLS_DIR).exists():
            return self.project_dir / DEFAULT_SKILLS_DIR
        return self.global_dir / DEFAULT_SKILLS_DIR

    @property
    def agents_file(self) -> Path:
        """Get AGENTS.md file path."""
        if self.project_dir and (self.project_dir / DEFAULT_AGENTS_FILE).exists():
            return self.project_dir / DEFAULT_AGENTS_FILE
        return self.global_dir / DEFAULT_AGENTS_FILE

    @property
    def config_file(self) -> Path:
        """Get config.json file path."""
        if self.project_dir:
            return self.project_dir / DEFAULT_CONFIG_FILE
        return self.global_dir / DEFAULT_CONFIG_FILE

    @property
    def session_file(self) -> Path:
        """Get session.json file path."""
        if self.project_dir:
            return self.project_dir / DEFAULT_SESSION_FILE
        return self.global_dir / DEFAULT_SESSION_FILE

    @property
    def settings_file(self) -> Path:
        """Get settings.local.json file path (project-level permissions)."""
        if self.project_dir:
            return self.project_dir / DEFAULT_SETTINGS_FILE
        return self.global_dir / DEFAULT_SETTINGS_FILE

    def load_permissions(self) -> Permissions:
        """Load permissions from settings.local.json."""
        if self.settings_file.exists():
            try:
                with open(self.settings_file) as f:
                    data = json.load(f)
                if "permissions" in data:
                    return Permissions.from_dict(data["permissions"])
            except (json.JSONDecodeError, IOError):
                pass
        return Permissions()

    def save_permissions(self, permissions: Permissions) -> None:
        """Save permissions to settings.local.json.

        If no project .valis directory exists, creates one in the current
        working directory (like Claude Code's .claude folder).
        """
        # Auto-create project .valis folder if none exists
        if self.project_dir is None:
            self.project_dir = Path.cwd() / DEFAULT_PROJECT_DIR
            self.project_dir.mkdir(parents=True, exist_ok=True)

        self.ensure_dirs()

        # Load existing settings or create new
        data = {}
        if self.settings_file.exists():
            try:
                with open(self.settings_file) as f:
                    data = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        data["permissions"] = permissions.to_dict()

        with open(self.settings_file, "w") as f:
            json.dump(data, f, indent=2)

    def ensure_dirs(self) -> None:
        """Create necessary directories."""
        self.global_dir.mkdir(parents=True, exist_ok=True)
        (self.global_dir / DEFAULT_MEMORIES_DIR).mkdir(exist_ok=True)
        (self.global_dir / DEFAULT_SKILLS_DIR).mkdir(exist_ok=True)

        if self.project_dir:
            self.project_dir.mkdir(parents=True, exist_ok=True)

    def save(self) -> None:
        """Save configuration to file."""
        self.ensure_dirs()
        data = {
            "model": self.model.to_dict(),
            "approval": {
                "require_approval": self.approval.require_approval,
                "auto_approve": self.approval.auto_approve,
                "always_deny": self.approval.always_deny,
            },
            "agent_name": self.agent_name,
            "max_turns": self.max_turns,
            "sandbox_enabled": self.sandbox_enabled,
            "database_enabled": self.database_enabled,
            "show_thinking": self.show_thinking,
            "show_tool_calls": self.show_tool_calls,
            "compact_mode": self.compact_mode,
        }
        with open(self.config_file, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, config_file: Path) -> "Config":
        """Load configuration from file."""
        config = cls()

        if config_file.exists():
            with open(config_file) as f:
                data = json.load(f)

            if "model" in data:
                config.model = ModelSettings.from_dict(data["model"])
            if "approval" in data:
                approval_data = data["approval"]
                config.approval = ApprovalSettings(
                    require_approval=approval_data.get("require_approval", True),
                    auto_approve=approval_data.get("auto_approve", []),
                    always_deny=approval_data.get("always_deny", []),
                )
            config.agent_name = data.get("agent_name", "valis-agent")
            config.max_turns = data.get("max_turns", 50)
            config.sandbox_enabled = data.get("sandbox_enabled", True)
            config.database_enabled = data.get("database_enabled", False)
            config.show_thinking = data.get("show_thinking", False)
            config.show_tool_calls = data.get("show_tool_calls", True)
            config.compact_mode = data.get("compact_mode", False)

        return config

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "global_dir": str(self.global_dir),
            "project_dir": str(self.project_dir) if self.project_dir else None,
            "model": self.model.to_dict(),
            "agent_name": self.agent_name,
            "max_turns": self.max_turns,
            "sandbox_enabled": self.sandbox_enabled,
            "database_enabled": self.database_enabled,
        }


def detect_project_dir(start_path: Optional[Path] = None) -> Optional[Path]:
    """
    Detect project-specific .valis directory.

    Walks up from start_path looking for .valis directory.

    Args:
        start_path: Starting directory (defaults to cwd)

    Returns:
        Path to .valis directory if found, None otherwise
    """
    if start_path is None:
        start_path = Path.cwd()

    current = start_path.resolve()

    while current != current.parent:
        valis_dir = current / DEFAULT_PROJECT_DIR
        if valis_dir.is_dir():
            return valis_dir

        # Also check for AGENTS.md as indicator
        agents_file = current / DEFAULT_AGENTS_FILE
        if agents_file.is_file():
            # Create .valis dir if AGENTS.md exists
            valis_dir.mkdir(exist_ok=True)
            return valis_dir

        current = current.parent

    return None


def get_config(
    project_dir: Optional[Path] = None,
    global_dir: Optional[Path] = None,
) -> Config:
    """
    Get configuration with project detection.

    Args:
        project_dir: Explicit project directory
        global_dir: Explicit global directory

    Returns:
        Configured Config instance
    """
    # Determine directories
    if global_dir is None:
        global_dir = DEFAULT_GLOBAL_DIR

    if project_dir is None:
        project_dir = detect_project_dir()

    # Load config
    config = Config(global_dir=global_dir, project_dir=project_dir)

    # Try to load from file
    if config.config_file.exists():
        config = Config.load(config.config_file)
        config.global_dir = global_dir
        config.project_dir = project_dir

    config.ensure_dirs()

    return config


def get_model_from_env() -> Optional[ModelSettings]:
    """Get model settings from environment variables."""
    provider = os.environ.get("VALIS_PROVIDER")
    model = os.environ.get("VALIS_MODEL")

    if provider and model:
        return ModelSettings(provider=provider, model=model)

    # Check for provider-specific env vars
    if os.environ.get("ANTHROPIC_API_KEY"):
        return ModelSettings(provider="anthropic", model="claude-sonnet-4-5-20250929")
    if os.environ.get("OPENAI_API_KEY"):
        return ModelSettings(provider="openai", model="gpt-4o")

    return None


def init_project(path: Optional[Path] = None) -> Path:
    """
    Initialize a new project with .valis directory.

    Args:
        path: Directory to initialize (defaults to cwd)

    Returns:
        Path to created .valis directory
    """
    if path is None:
        path = Path.cwd()

    valis_dir = path / DEFAULT_PROJECT_DIR
    valis_dir.mkdir(exist_ok=True)

    # Create subdirectories
    (valis_dir / DEFAULT_MEMORIES_DIR).mkdir(exist_ok=True)
    (valis_dir / DEFAULT_SKILLS_DIR).mkdir(exist_ok=True)

    # Create default config
    config = Config(project_dir=valis_dir)
    config.save()

    # Create empty AGENTS.md
    agents_file = valis_dir / DEFAULT_AGENTS_FILE
    if not agents_file.exists():
        agents_file.write_text("""# Agent Knowledge

Add project-specific knowledge here. This file is loaded at session start.

## Project Overview

[Describe the project]

## Key Conventions

[List important conventions]

## Common Tasks

[Document common tasks]
""")

    return valis_dir
