# Vel Harness: PRD & Technical Specification

## Executive Summary

Build `vel-harness`, a Python package that provides Claude Code-like agent capabilities for deployment in containerized environments (Kubernetes). The harness combines the Vel runtime (for streaming and Vercel AI SDK V5 protocol compliance) with Claude Code's agent patterns, system prompts, and tools—without requiring the Claude Code CLI.

---

## Table of Contents

1. [Background & Context](#background--context)
2. [Goals & Non-Goals](#goals--non-goals)
3. [Architecture Overview](#architecture-overview)
4. [Package Structure](#package-structure)
5. [Core Components Specification](#core-components-specification)
6. [Integration Points](#integration-points)
7. [Implementation Plan](#implementation-plan)
8. [Dependencies](#dependencies)
9. [Testing Strategy](#testing-strategy)
10. [Appendix: External Resources](#appendix-external-resources)

---

## Background & Context

### Problem Statement

The user has built Vel, an AI agent runtime with:
- Multi-provider support (OpenAI, Anthropic, Gemini)
- 100% Vercel AI SDK V5 Stream Protocol compatibility
- Tool system with `ToolSpec.from_function()`
- Session/context management

The user wants to extend Vel with Claude Code-like capabilities (skills, subagents, planning) for a chat application deployed in Kubernetes. The official Claude Agent SDK requires the Claude Code CLI, which is incompatible with containerized API deployments.

### Solution

Create `vel-harness`, a separate package that:
1. Uses Vel as the underlying runtime for streaming/protocol translation
2. Implements the agent loop pattern from `learn-claude-code` (pure Python, direct Anthropic API)
3. Leverages actual Claude Code system prompts from `Piebald-AI/claude-code-system-prompts`
4. Provides a skills system where skills live in the consuming API's codebase
5. Supports subagent spawning for task delegation

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Separate package (not extending Vel) | Clean separation of concerns; Vel stays focused on runtime |
| Skills in consumer's codebase | Skills are deployment-specific; version controlled with API |
| System prompt is STATIC | Preserves Anthropic prompt caching for cost efficiency |
| Skills injected as tool_result | Not system prompt; preserves cache |
| Append-only message history | Never edit; preserves cache |
| Pure Python agent loop | No CLI dependency; Kubernetes compatible |

---

## Goals & Non-Goals

### Goals

1. **Kubernetes Compatible**: Pure Python, no CLI dependencies, deployable as container
2. **Vercel AI SDK V5 Streaming**: Full protocol compliance via Vel
3. **Skills System**: On-demand domain expertise loading from configurable directories
4. **Subagent Support**: Task delegation with isolated context (Explore, Plan, Task agents)
5. **Planning Tools**: TodoWrite for explicit task tracking
6. **Claude Code Prompts**: Use actual prompts from Piebald-AI repo
7. **Context Management**: Session handling with compaction/summarization
8. **Chat App Integration**: Easy integration with FastAPI/chat endpoints

### Non-Goals

1. CLI interface (this is for API deployment)
2. Multi-provider support in harness (Anthropic only; Vel handles multi-provider at runtime layer)
3. MCP server support (can be added later)
4. Permission system / user approval flows (chat app handles this)
5. File watching / hot reload of skills

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Your API (FastAPI)                        │
├─────────────────────────────────────────────────────────────────┤
│                           VelHarness                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ SkillLoader │  │AgentRegistry│  │    ContextManager       │  │
│  │             │  │             │  │  (sessions, compaction) │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                        Tools                              │   │
│  │  Bash │ ReadFile │ Write │ Edit │ Glob │ Grep │ TodoWrite│   │
│  │  Task (subagent) │ Skill                                  │   │
│  └──────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                      Vel Agent Runtime                           │
│            (Streaming, Protocol Translation, Providers)          │
├─────────────────────────────────────────────────────────────────┤
│                       Anthropic API                              │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    Your API's /skills Directory                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │ code-review │  │  debugging  │  │  your-domain│  ...         │
│  │  SKILL.md   │  │  SKILL.md   │  │  SKILL.md   │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. User message arrives at API endpoint
2. VelHarness receives message, appends to session context
3. Agent loop runs:
   - Send messages + tools to Anthropic API
   - If `stop_reason == "tool_use"`: execute tools, append results, continue
   - If `stop_reason != "tool_use"`: return response
4. For streaming: Vel translates Anthropic events → Vercel AI SDK V5 events
5. Events streamed to frontend via SSE

### Subagent Flow

1. Main agent calls `Task` tool with description and agent type
2. TaskTool spawns child agent with:
   - Fresh message history (isolated context)
   - Agent-specific system prompt (from registry)
   - Agent-specific tool set
3. Child agent runs to completion
4. Result returned to parent agent as tool_result

---

## Package Structure

```
vel-harness/
├── pyproject.toml
├── README.md
├── LICENSE
│
├── vel_harness/
│   ├── __init__.py                    # Public API exports
│   ├── harness.py                     # Main VelHarness class
│   ├── config.py                      # Configuration dataclasses
│   │
│   ├── prompts/                       # System prompts (from Piebald-AI)
│   │   ├── __init__.py
│   │   ├── system.md                  # Main system prompt (2972 tks)
│   │   ├── summarization.md           # Context compaction (1121 tks)
│   │   └── agents/
│   │       ├── explore.md             # Explore subagent (516 tks)
│   │       ├── plan.md                # Plan subagent (633 tks)
│   │       └── task.md                # Task subagent (294 tks)
│   │
│   ├── tools/
│   │   ├── __init__.py                # Tool exports
│   │   ├── definitions.py             # Tool descriptions (from Piebald-AI)
│   │   ├── bash.py                    # Bash execution
│   │   ├── file_ops.py                # Read, Write, Edit
│   │   ├── search.py                  # Glob, Grep
│   │   ├── todo.py                    # TodoWrite
│   │   ├── task.py                    # Subagent spawning
│   │   └── skill.py                   # Skill loading tool
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── registry.py                # AgentRegistry class
│   │   └── config.py                  # AgentConfig dataclass
│   │
│   ├── skills/
│   │   ├── __init__.py
│   │   └── loader.py                  # SkillLoader class
│   │
│   ├── context/
│   │   ├── __init__.py
│   │   ├── manager.py                 # ContextManager class
│   │   ├── session.py                 # SessionState dataclass
│   │   └── compaction.py              # Conversation summarization
│   │
│   └── streaming/
│       ├── __init__.py
│       └── adapter.py                 # Vel streaming integration
│
└── tests/
    ├── __init__.py
    ├── test_harness.py
    ├── test_tools.py
    ├── test_skills.py
    ├── test_agents.py
    └── test_context.py
```

---

## Core Components Specification

### 1. VelHarness (Main Class)

**File**: `vel_harness/harness.py`

```python
class VelHarness:
    """
    Claude Code-style harness built on Vel runtime.
    
    Combines:
    - Vel for streaming/protocol translation
    - Claude Code system prompts
    - Skills pattern for on-demand knowledge
    - Subagent spawning for task delegation
    """
    
    def __init__(
        self,
        model: dict,                              # {"provider": "anthropic", "model": "...", "api_key": "..."}
        skill_dirs: Optional[list[Path]] = None,  # Directories containing SKILL.md files
        custom_agents: Optional[dict[str, AgentConfig]] = None,  # Additional subagent configs
        system_prompt: Optional[str] = None,      # Override default system prompt
        max_turns: int = 100,                     # Max tool-use iterations
        working_directory: Optional[Path] = None, # CWD for file operations
    ):
        ...
    
    async def run(
        self,
        message: str,
        session_id: Optional[str] = None
    ) -> str:
        """Non-streaming execution. Returns final response text."""
        ...
    
    async def run_stream(
        self,
        message: str,
        session_id: Optional[str] = None
    ) -> AsyncIterator[dict]:
        """
        Streaming execution.
        Yields Vercel AI SDK V5 protocol events:
        - text-start, text-delta, text-end
        - tool-input-start, tool-input-delta, tool-input-available
        - tool-output-available
        - start-step, finish-step
        - finish-message
        """
        ...
    
    async def run_agent_loop(
        self,
        messages: list[dict],
        system_prompt: str,
        tools: list[str],
        max_turns: int
    ) -> str:
        """
        Core agent loop used by both main agent and subagents.
        Pure Anthropic API calls, no CLI dependency.
        """
        ...
```

**Initialization Flow**:
1. Create Anthropic client
2. Initialize SkillLoader with skill_dirs
3. Initialize AgentRegistry with default + custom agents
4. Initialize ContextManager
5. Build tool list from definitions + handlers
6. Create Vel Agent for streaming support

### 2. Tool Definitions

**File**: `vel_harness/tools/definitions.py`

Source: `Piebald-AI/claude-code-system-prompts/system-prompts/tool-description-*.md`

```python
TOOL_DEFINITIONS: dict[str, ToolDefinition] = {
    "bash": ToolDefinition(
        name="Bash",
        description="...",  # 1074 tokens from tool-description-bash.md
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The bash command to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 120}
            },
            "required": ["command"]
        }
    ),
    
    "read_file": ToolDefinition(
        name="ReadFile",
        description="...",  # 439 tokens from tool-description-readfile.md
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative path"},
                "offset": {"type": "integer", "description": "Line offset", "default": 0},
                "limit": {"type": "integer", "description": "Max lines to read", "default": 2000}
            },
            "required": ["path"]
        }
    ),
    
    "write_file": ToolDefinition(
        name="Write",
        description="...",  # 159 tokens from tool-description-write.md
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["path", "content"]
        }
    ),
    
    "edit_file": ToolDefinition(
        name="Edit",
        description="...",  # 278 tokens from tool-description-edit.md
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_string": {"type": "string", "description": "Exact string to find (must be unique)"},
                "new_string": {"type": "string", "description": "Replacement string"}
            },
            "required": ["path", "old_string", "new_string"]
        }
    ),
    
    "glob": ToolDefinition(
        name="Glob",
        description="...",  # 122 tokens from tool-description-glob.md
        input_schema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern (e.g., **/*.py)"},
                "path": {"type": "string", "description": "Base directory", "default": "."}
            },
            "required": ["pattern"]
        }
    ),
    
    "grep": ToolDefinition(
        name="Grep",
        description="...",  # 300 tokens from tool-description-grep.md
        input_schema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Search pattern (regex)"},
                "path": {"type": "string", "description": "Directory to search", "default": "."},
                "include": {"type": "string", "description": "File pattern to include"}
            },
            "required": ["pattern"]
        }
    ),
    
    "todo_write": ToolDefinition(
        name="TodoWrite",
        description="...",  # 2167 tokens from tool-description-todowrite.md
        input_schema={
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "content": {"type": "string"},
                            "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
                            "priority": {"type": "string", "enum": ["high", "medium", "low"]}
                        },
                        "required": ["id", "content", "status"]
                    }
                }
            },
            "required": ["todos"]
        }
    ),
    
    "task": ToolDefinition(
        name="Task",
        description="...",  # 1055 tokens from tool-description-task.md
        input_schema={
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "Detailed task description for the subagent"},
                "agent": {
                    "type": "string",
                    "description": "Agent type to use",
                    "enum": ["default", "explore", "plan"],
                    "default": "default"
                }
            },
            "required": ["description"]
        }
    ),
    
    "skill": ToolDefinition(
        name="Skill",
        description="...",  # 279 tokens from tool-description-skill.md (+ dynamic skill list)
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the skill to load"}
            },
            "required": ["name"]
        }
    )
}
```

### 3. Tool Implementations

**File**: `vel_harness/tools/bash.py`

```python
import asyncio
import shlex
from typing import Optional

class BashTool:
    """Execute bash commands with timeout and output truncation."""
    
    def __init__(
        self,
        working_directory: Optional[Path] = None,
        max_output_chars: int = 50000,
        default_timeout: int = 120
    ):
        self.working_directory = working_directory or Path.cwd()
        self.max_output_chars = max_output_chars
        self.default_timeout = default_timeout
    
    async def execute(self, command: str, timeout: Optional[int] = None) -> str:
        """
        Execute bash command.
        
        Returns:
            Command output (stdout + stderr), truncated if necessary
        """
        timeout = timeout or self.default_timeout
        
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_directory
            )
            
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout
            )
            
            output = stdout.decode('utf-8', errors='replace')
            if stderr:
                output += "\n" + stderr.decode('utf-8', errors='replace')
            
            # Truncate if necessary
            if len(output) > self.max_output_chars:
                output = output[:self.max_output_chars] + f"\n\n[Output truncated at {self.max_output_chars} chars]"
            
            return output.strip() or "(no output)"
            
        except asyncio.TimeoutError:
            proc.kill()
            return f"Error: Command timed out after {timeout} seconds"
        except Exception as e:
            return f"Error executing command: {e}"
```

**File**: `vel_harness/tools/file_ops.py`

```python
from pathlib import Path
from typing import Optional

class FileOperations:
    """File read, write, and edit operations."""
    
    def __init__(self, working_directory: Optional[Path] = None):
        self.working_directory = working_directory or Path.cwd()
    
    def _resolve_path(self, path: str) -> Path:
        """Resolve path relative to working directory."""
        p = Path(path)
        if not p.is_absolute():
            p = self.working_directory / p
        return p.resolve()
    
    async def read_file(
        self,
        path: str,
        offset: int = 0,
        limit: int = 2000
    ) -> str:
        """Read file contents with optional line offset and limit."""
        try:
            resolved = self._resolve_path(path)
            content = resolved.read_text(encoding='utf-8', errors='replace')
            lines = content.split('\n')
            
            total_lines = len(lines)
            selected = lines[offset:offset + limit]
            result = '\n'.join(selected)
            
            if offset > 0 or offset + limit < total_lines:
                result += f"\n\n[Showing lines {offset+1}-{min(offset+limit, total_lines)} of {total_lines}]"
            
            return result
        except FileNotFoundError:
            return f"Error: File not found: {path}"
        except Exception as e:
            return f"Error reading file: {e}"
    
    async def write_file(self, path: str, content: str) -> str:
        """Write content to file, creating directories if needed."""
        try:
            resolved = self._resolve_path(path)
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding='utf-8')
            return f"Successfully wrote {len(content)} characters to {path}"
        except Exception as e:
            return f"Error writing file: {e}"
    
    async def edit_file(self, path: str, old_string: str, new_string: str) -> str:
        """
        Replace exact string in file.
        old_string must appear exactly once.
        """
        try:
            resolved = self._resolve_path(path)
            content = resolved.read_text(encoding='utf-8')
            
            count = content.count(old_string)
            if count == 0:
                return f"Error: String not found in {path}"
            if count > 1:
                return f"Error: String appears {count} times in {path}. Must be unique."
            
            new_content = content.replace(old_string, new_string)
            resolved.write_text(new_content, encoding='utf-8')
            return f"Successfully edited {path}"
        except FileNotFoundError:
            return f"Error: File not found: {path}"
        except Exception as e:
            return f"Error editing file: {e}"
```

**File**: `vel_harness/tools/search.py`

```python
import subprocess
from pathlib import Path
from typing import Optional

class SearchTools:
    """Glob and grep operations."""
    
    def __init__(
        self,
        working_directory: Optional[Path] = None,
        max_results: int = 100,
        max_output_chars: int = 20000
    ):
        self.working_directory = working_directory or Path.cwd()
        self.max_results = max_results
        self.max_output_chars = max_output_chars
    
    async def glob(self, pattern: str, path: str = ".") -> str:
        """Find files matching glob pattern."""
        try:
            base = self.working_directory / path
            matches = list(base.glob(pattern))[:self.max_results]
            
            if not matches:
                return f"No files matching '{pattern}' in {path}"
            
            result = '\n'.join(str(m.relative_to(self.working_directory)) for m in matches)
            
            if len(matches) == self.max_results:
                result += f"\n\n[Results limited to {self.max_results} files]"
            
            return result
        except Exception as e:
            return f"Error in glob: {e}"
    
    async def grep(
        self,
        pattern: str,
        path: str = ".",
        include: Optional[str] = None
    ) -> str:
        """Search file contents using ripgrep (or grep fallback)."""
        try:
            # Try ripgrep first, fall back to grep
            cmd = ["rg", "-n", "--no-heading", pattern, path]
            if include:
                cmd.extend(["-g", include])
            
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=self.working_directory
                )
            except FileNotFoundError:
                # Fallback to grep
                cmd = ["grep", "-rn", pattern, path]
                if include:
                    cmd.extend(["--include", include])
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=self.working_directory
                )
            
            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr
            
            if len(output) > self.max_output_chars:
                output = output[:self.max_output_chars] + f"\n\n[Output truncated]"
            
            return output.strip() or f"No matches for '{pattern}'"
        except subprocess.TimeoutExpired:
            return "Error: Search timed out"
        except Exception as e:
            return f"Error in grep: {e}"
```

**File**: `vel_harness/tools/todo.py`

```python
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

class TodoStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

class TodoPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

@dataclass
class TodoItem:
    id: str
    content: str
    status: TodoStatus
    priority: TodoPriority = TodoPriority.MEDIUM

class TodoManager:
    """Manages task list for planning."""
    
    def __init__(self):
        self._todos: dict[str, TodoItem] = {}
    
    async def write(self, todos: list[dict]) -> str:
        """Update todo list."""
        self._todos.clear()
        
        for item in todos:
            todo = TodoItem(
                id=item["id"],
                content=item["content"],
                status=TodoStatus(item["status"]),
                priority=TodoPriority(item.get("priority", "medium"))
            )
            self._todos[todo.id] = todo
        
        return self._format_todos()
    
    def _format_todos(self) -> str:
        """Format todos for display."""
        if not self._todos:
            return "No todos."
        
        lines = ["Current todos:"]
        for todo in self._todos.values():
            status_icon = {
                TodoStatus.PENDING: "⬜",
                TodoStatus.IN_PROGRESS: "🔄",
                TodoStatus.COMPLETED: "✅"
            }[todo.status]
            lines.append(f"{status_icon} [{todo.id}] {todo.content} ({todo.priority.value})")
        
        return '\n'.join(lines)
    
    def get_todos(self) -> list[TodoItem]:
        """Get current todos."""
        return list(self._todos.values())
    
    def get_state_summary(self) -> str:
        """Get summary for context injection."""
        return self._format_todos()
```

**File**: `vel_harness/tools/task.py`

```python
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from vel_harness.harness import VelHarness

class TaskTool:
    """
    Spawns isolated subagents for complex tasks.
    
    Key principle: Subagents get FRESH context.
    This prevents context pollution and allows focused work.
    """
    
    def __init__(self, harness: "VelHarness"):
        self.harness = harness
    
    async def execute(
        self,
        description: str,
        agent: str = "default"
    ) -> str:
        """
        Spawn a subagent with isolated context.
        
        Args:
            description: Detailed task description for the subagent
            agent: Agent type from registry ("default", "explore", "plan", or custom)
        
        Returns:
            Subagent's result wrapped in XML tags
        """
        config = self.harness.agent_registry.get(agent)
        
        # Fresh context for subagent (this is the whole point)
        child_messages = [{"role": "user", "content": description}]
        
        try:
            result = await self.harness.run_agent_loop(
                messages=child_messages,
                system_prompt=config.system_prompt,
                tools=config.tools,
                max_turns=config.max_turns
            )
            
            return f"""<task-result agent="{agent}" status="success">
{result}
</task-result>"""
            
        except Exception as e:
            return f"""<task-result agent="{agent}" status="error">
Error: {e}
</task-result>"""
```

**File**: `vel_harness/tools/skill.py`

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vel_harness.skills.loader import SkillLoader

class SkillTool:
    """
    Loads domain expertise on-demand.
    
    Key principle: Skill content is returned as tool_result,
    NOT injected into system prompt. This preserves prompt caching.
    """
    
    def __init__(self, loader: "SkillLoader"):
        self.loader = loader
    
    def execute(self, name: str) -> str:
        """
        Load a skill by name.
        
        Args:
            name: Skill name (matches directory name or frontmatter name)
        
        Returns:
            Skill content wrapped in XML tags with instruction to follow
        """
        return self.loader.get_skill_content(name)
    
    def get_description_with_skills(self, base_description: str) -> str:
        """Get tool description with current available skills listed."""
        skills = self.loader.list_skills()
        
        if not skills:
            return base_description + "\n\nNo skills currently available."
        
        skills_list = '\n'.join(
            f"- {s['name']}: {s['description']}" 
            for s in skills
        )
        
        return f"""{base_description}

Available skills:
{skills_list}"""
```

### 4. Skill Loader

**File**: `vel_harness/skills/loader.py`

```python
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
import re
import yaml

@dataclass
class Skill:
    """Loaded skill data."""
    name: str
    description: str
    content: str
    path: Path

class SkillLoader:
    """
    Discovers and loads SKILL.md files from configured directories.
    
    Skill format:
    ```
    ---
    name: skill-name
    description: What this skill does
    ---
    
    # Skill content (markdown)
    ...
    ```
    
    Or without frontmatter (name derived from directory).
    """
    
    def __init__(self, skill_dirs: list[Path]):
        """
        Args:
            skill_dirs: List of directories to scan for SKILL.md files
        """
        self.skill_dirs = skill_dirs
        self._cache: dict[str, Skill] = {}
        self._discover()
    
    def _discover(self):
        """Scan directories for SKILL.md files."""
        for skill_dir in self.skill_dirs:
            if not skill_dir.exists():
                continue
            
            for skill_path in skill_dir.rglob("SKILL.md"):
                try:
                    skill = self._parse_skill(skill_path)
                    if skill:
                        self._cache[skill.name] = skill
                except Exception:
                    # Skip malformed skills
                    continue
    
    def _parse_skill(self, path: Path) -> Optional[Skill]:
        """Parse SKILL.md file with optional YAML frontmatter."""
        content = path.read_text(encoding='utf-8')
        
        # Try to parse YAML frontmatter
        frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n'
        match = re.match(frontmatter_pattern, content, re.DOTALL)
        
        if match:
            try:
                meta = yaml.safe_load(match.group(1))
                body = content[match.end():].strip()
                return Skill(
                    name=meta.get("name", path.parent.name),
                    description=meta.get("description", ""),
                    content=body,
                    path=path
                )
            except yaml.YAMLError:
                pass
        
        # Fallback: use directory name, entire file as content
        return Skill(
            name=path.parent.name,
            description="",
            content=content.strip(),
            path=path
        )
    
    def list_skills(self) -> list[dict]:
        """
        List available skills.
        
        Returns:
            List of {"name": str, "description": str}
        """
        return [
            {"name": s.name, "description": s.description}
            for s in self._cache.values()
        ]
    
    def get_skill_content(self, name: str) -> str:
        """
        Get skill content formatted for injection.
        
        Args:
            name: Skill name
        
        Returns:
            Skill content wrapped in XML tags, or error message
        """
        if name not in self._cache:
            available = list(self._cache.keys())
            return f"Error: Skill '{name}' not found. Available skills: {available}"
        
        skill = self._cache[name]
        
        # Format as tool_result (this becomes part of conversation history)
        return f"""<skill-loaded name="{name}">
{skill.content}
</skill-loaded>

Follow the instructions in the skill above."""
    
    def reload(self):
        """Re-scan skill directories."""
        self._cache.clear()
        self._discover()
```

### 5. Agent Registry

**File**: `vel_harness/agents/config.py`

```python
from dataclasses import dataclass, field

@dataclass
class AgentConfig:
    """Configuration for a subagent."""
    name: str
    system_prompt: str
    tools: list[str]
    max_turns: int = 50
    description: str = ""
```

**File**: `vel_harness/agents/registry.py`

```python
from pathlib import Path
from typing import Optional
from .config import AgentConfig

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

def _load_prompt(filename: str) -> str:
    """Load prompt file content."""
    return (PROMPTS_DIR / filename).read_text(encoding='utf-8')

# Default agent configurations using Claude Code prompts
DEFAULT_AGENTS = {
    "default": AgentConfig(
        name="default",
        system_prompt=_load_prompt("agents/task.md"),  # 294 tokens
        tools=["bash", "read_file", "write_file", "edit_file", "glob", "grep"],
        max_turns=50,
        description="General-purpose agent for task execution"
    ),
    "explore": AgentConfig(
        name="explore",
        system_prompt=_load_prompt("agents/explore.md"),  # 516 tokens
        tools=["read_file", "glob", "grep", "bash"],  # Read-heavy, limited writes
        max_turns=30,
        description="Explores codebase to gather information"
    ),
    "plan": AgentConfig(
        name="plan",
        system_prompt=_load_prompt("agents/plan.md"),  # 633 tokens
        tools=["read_file", "glob", "grep", "todo_write"],  # Planning focused
        max_turns=20,
        description="Creates structured plans for complex tasks"
    ),
}

class AgentRegistry:
    """
    Registry of available subagent configurations.
    
    Includes default agents (default, explore, plan) and supports custom agents.
    """
    
    def __init__(self, custom_agents: Optional[dict[str, AgentConfig]] = None):
        """
        Args:
            custom_agents: Additional agent configurations to register
        """
        self._agents = dict(DEFAULT_AGENTS)
        
        if custom_agents:
            self._agents.update(custom_agents)
    
    def get(self, agent_id: str) -> AgentConfig:
        """
        Get agent configuration by ID.
        
        Falls back to 'default' if not found.
        """
        return self._agents.get(agent_id, self._agents["default"])
    
    def register(self, agent_id: str, config: AgentConfig):
        """Register a new agent configuration."""
        self._agents[agent_id] = config
    
    def list_agents(self) -> list[str]:
        """List available agent IDs."""
        return list(self._agents.keys())
    
    def get_agent_descriptions(self) -> str:
        """Get formatted descriptions for tool description."""
        lines = []
        for agent_id, config in self._agents.items():
            lines.append(f"- {agent_id}: {config.description}")
        return '\n'.join(lines)
```

### 6. Context Manager

**File**: `vel_harness/context/session.py`

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class SessionState:
    """State for a conversation session."""
    messages: list[dict] = field(default_factory=list)
    todos: list[dict] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    token_estimate: int = 0
```

**File**: `vel_harness/context/compaction.py`

```python
from anthropic import Anthropic
from pathlib import Path

# Load summarization prompt from Piebald-AI
SUMMARIZATION_PROMPT = (
    Path(__file__).parent.parent / "prompts" / "summarization.md"
).read_text()

class ContextCompactor:
    """
    Summarizes conversation history to free up context window.
    
    Uses Claude to create a summary of older messages,
    preserving recent messages for immediate context.
    """
    
    def __init__(
        self,
        client: Anthropic,
        model: str = "claude-sonnet-4-20250514",
        keep_recent: int = 6
    ):
        self.client = client
        self.model = model
        self.keep_recent = keep_recent
    
    async def compact(self, messages: list[dict]) -> list[dict]:
        """
        Compact message history by summarizing older messages.
        
        Args:
            messages: Full message history
        
        Returns:
            Compacted messages: [summary, ack, ...recent]
        """
        if len(messages) <= self.keep_recent + 2:
            return messages
        
        # Split messages
        to_summarize = messages[:-self.keep_recent]
        recent = messages[-self.keep_recent:]
        
        # Generate summary
        summary = await self._summarize(to_summarize)
        
        # Return compacted history
        return [
            {
                "role": "user",
                "content": f"<context-summary>\n{summary}\n</context-summary>"
            },
            {
                "role": "assistant",
                "content": "I understand the previous context. Continuing with the conversation."
            },
            *recent
        ]
    
    async def _summarize(self, messages: list[dict]) -> str:
        """Generate summary of messages."""
        # Format messages for summarization
        formatted = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if isinstance(content, list):
                # Handle tool results
                content = str(content)
            formatted.append(f"[{role}]: {content}")
        
        conversation_text = '\n\n'.join(formatted)
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            system=SUMMARIZATION_PROMPT,
            messages=[{
                "role": "user",
                "content": f"Summarize this conversation:\n\n{conversation_text}"
            }]
        )
        
        return response.content[0].text
```

**File**: `vel_harness/context/manager.py`

```python
from typing import Optional
from anthropic import Anthropic
from .session import SessionState
from .compaction import ContextCompactor

class ContextManager:
    """
    Manages conversation context across sessions.
    
    Key principles:
    - Append-only message history (never edit, for cache efficiency)
    - Automatic compaction when approaching token limits
    - Per-session state isolation
    """
    
    def __init__(
        self,
        client: Anthropic,
        max_tokens: int = 180000,
        compaction_threshold: float = 0.8,
        compaction_model: str = "claude-sonnet-4-20250514"
    ):
        """
        Args:
            client: Anthropic client for summarization
            max_tokens: Maximum context window to use
            compaction_threshold: Trigger compaction at this % of max_tokens
            compaction_model: Model to use for summarization
        """
        self.client = client
        self.max_tokens = max_tokens
        self.compaction_threshold = compaction_threshold
        self.compactor = ContextCompactor(client, compaction_model)
        self._sessions: dict[str, SessionState] = {}
    
    def get_session(self, session_id: str) -> SessionState:
        """Get or create session state."""
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionState()
        return self._sessions[session_id]
    
    def append_message(self, session_id: str, message: dict):
        """
        Append message to session history.
        
        NEVER edit existing messages (cache efficiency).
        """
        session = self.get_session(session_id)
        session.messages.append(message)
        
        # Rough token estimate (4 chars ≈ 1 token)
        session.token_estimate += len(str(message)) // 4
    
    async def get_messages(self, session_id: str) -> list[dict]:
        """
        Get messages for session, compacting if necessary.
        """
        session = self.get_session(session_id)
        
        # Check if compaction needed
        threshold = int(self.max_tokens * self.compaction_threshold)
        if session.token_estimate > threshold:
            session.messages = await self.compactor.compact(session.messages)
            session.token_estimate = len(str(session.messages)) // 4
        
        return session.messages
    
    def clear_session(self, session_id: str):
        """Clear session state."""
        if session_id in self._sessions:
            del self._sessions[session_id]
    
    def update_todos(self, session_id: str, todos: list[dict]):
        """Update todo state for session."""
        session = self.get_session(session_id)
        session.todos = todos
    
    def get_todos(self, session_id: str) -> list[dict]:
        """Get todos for session."""
        return self.get_session(session_id).todos
```

### 7. Streaming Adapter

**File**: `vel_harness/streaming/adapter.py`

```python
from typing import AsyncIterator
from vel import Agent

class VelStreamingAdapter:
    """
    Adapter for Vel's streaming to ensure Vercel AI SDK V5 compliance.
    
    Vel already provides 100% V5 protocol parity, so this is mainly
    for any harness-specific event additions.
    """
    
    def __init__(self, vel_agent: Agent):
        self.vel_agent = vel_agent
    
    async def stream(
        self,
        message: str,
        session_id: str
    ) -> AsyncIterator[dict]:
        """
        Stream events from Vel agent.
        
        Yields Vercel AI SDK V5 protocol events:
        - text-start, text-delta, text-end
        - tool-input-start, tool-input-delta, tool-input-available
        - tool-output-available
        - start-step, finish-step
        - finish-message (with usage)
        """
        async for event in self.vel_agent.run_stream(
            {"message": message},
            session_id=session_id
        ):
            # Vel events are already V5 compliant
            yield event
    
    @staticmethod
    def create_custom_event(event_type: str, data: dict, transient: bool = False) -> dict:
        """
        Create a custom data event.
        
        Args:
            event_type: Event type (will be prefixed with 'data-')
            data: Event payload
            transient: If True, event is for UI only (not persisted)
        """
        return {
            "type": f"data-{event_type}",
            "data": data,
            "transient": transient
        }
```

### 8. Main Harness Implementation

**File**: `vel_harness/harness.py`

```python
import asyncio
from pathlib import Path
from typing import AsyncIterator, Optional, Any
from anthropic import Anthropic
from vel import Agent, ToolSpec

from .config import HarnessConfig
from .tools.definitions import TOOL_DEFINITIONS
from .tools.bash import BashTool
from .tools.file_ops import FileOperations
from .tools.search import SearchTools
from .tools.todo import TodoManager
from .tools.task import TaskTool
from .tools.skill import SkillTool
from .skills.loader import SkillLoader
from .agents.registry import AgentRegistry
from .agents.config import AgentConfig
from .context.manager import ContextManager
from .streaming.adapter import VelStreamingAdapter

# Load main system prompt
MAIN_SYSTEM_PROMPT = (
    Path(__file__).parent / "prompts" / "system.md"
).read_text()


class VelHarness:
    """
    Claude Code-style agent harness built on Vel runtime.
    
    Provides:
    - Skills system for on-demand domain expertise
    - Subagent spawning for task delegation
    - Planning tools (TodoWrite)
    - Context management with compaction
    - Vercel AI SDK V5 streaming via Vel
    
    All without CLI dependencies - pure Python, Kubernetes compatible.
    """
    
    def __init__(
        self,
        model: dict,
        skill_dirs: Optional[list[Path]] = None,
        custom_agents: Optional[dict[str, AgentConfig]] = None,
        system_prompt: Optional[str] = None,
        max_turns: int = 100,
        working_directory: Optional[Path] = None,
    ):
        """
        Initialize the harness.
        
        Args:
            model: Model configuration dict with keys:
                   - provider: "anthropic"
                   - model: Model name (e.g., "claude-sonnet-4-20250514")
                   - api_key: Optional API key (defaults to env var)
            skill_dirs: Directories containing SKILL.md files
            custom_agents: Additional subagent configurations
            system_prompt: Override default system prompt (use sparingly)
            max_turns: Maximum tool-use iterations
            working_directory: Base directory for file operations
        """
        self.model_config = model
        self.max_turns = max_turns
        self.working_directory = working_directory or Path.cwd()
        
        # Anthropic client
        self.client = Anthropic(api_key=model.get("api_key"))
        
        # System prompt (STATIC for cache efficiency)
        self.system_prompt = system_prompt or MAIN_SYSTEM_PROMPT
        
        # Initialize components
        self.skill_loader = SkillLoader(skill_dirs or [Path("./skills")])
        self.agent_registry = AgentRegistry(custom_agents)
        self.context_manager = ContextManager(self.client)
        self.todo_manager = TodoManager()
        
        # Initialize tool implementations
        self._bash_tool = BashTool(self.working_directory)
        self._file_ops = FileOperations(self.working_directory)
        self._search_tools = SearchTools(self.working_directory)
        self._task_tool = TaskTool(self)
        self._skill_tool = SkillTool(self.skill_loader)
        
        # Build tool specs
        self._tools = self._build_tools()
        self._tool_handlers = self._build_tool_handlers()
        
        # Vel agent for streaming
        self._vel_agent = Agent(
            id="vel-harness:v1",
            model=model,
            tools=self._tools,
            system_prompt=self.system_prompt,
            policies={"max_steps": max_turns}
        )
        
        self._streaming_adapter = VelStreamingAdapter(self._vel_agent)
    
    def _build_tools(self) -> list[ToolSpec]:
        """Build tool specifications for Vel/Anthropic."""
        tools = []
        
        for tool_id, defn in TOOL_DEFINITIONS.items():
            # Special handling for skill tool (add available skills)
            if tool_id == "skill":
                description = self._skill_tool.get_description_with_skills(defn.description)
            else:
                description = defn.description
            
            tools.append(ToolSpec(
                name=defn.name,
                description=description,
                input_schema=defn.input_schema,
                handler=lambda **kwargs, tid=tool_id: self._execute_tool(tid, kwargs)
            ))
        
        return tools
    
    def _build_tool_handlers(self) -> dict[str, callable]:
        """Map tool names to handler methods."""
        return {
            "Bash": self._bash_tool.execute,
            "ReadFile": self._file_ops.read_file,
            "Write": self._file_ops.write_file,
            "Edit": self._file_ops.edit_file,
            "Glob": self._search_tools.glob,
            "Grep": self._search_tools.grep,
            "TodoWrite": self._handle_todo_write,
            "Task": self._task_tool.execute,
            "Skill": self._skill_tool.execute,
        }
    
    async def _execute_tool(self, tool_id: str, inputs: dict) -> str:
        """Execute a tool by ID."""
        # Map tool_id to tool name
        tool_name = TOOL_DEFINITIONS[tool_id].name
        handler = self._tool_handlers.get(tool_name)
        
        if not handler:
            return f"Error: Unknown tool {tool_name}"
        
        # Execute (handle both sync and async)
        if asyncio.iscoroutinefunction(handler):
            return await handler(**inputs)
        else:
            return handler(**inputs)
    
    async def _handle_todo_write(self, todos: list[dict]) -> str:
        """Handle TodoWrite tool."""
        result = await self.todo_manager.write(todos)
        return result
    
    # =========================================================================
    # Public API
    # =========================================================================
    
    async def run(
        self,
        message: str,
        session_id: Optional[str] = None
    ) -> str:
        """
        Run agent (non-streaming).
        
        Args:
            message: User message
            session_id: Session ID for context continuity
        
        Returns:
            Agent's final response text
        """
        session_id = session_id or "default"
        
        # Append user message
        self.context_manager.append_message(
            session_id,
            {"role": "user", "content": message}
        )
        
        # Get messages (with potential compaction)
        messages = await self.context_manager.get_messages(session_id)
        
        # Run agent loop
        result = await self.run_agent_loop(
            messages=messages,
            system_prompt=self.system_prompt,
            tools=list(TOOL_DEFINITIONS.keys()),
            max_turns=self.max_turns
        )
        
        # Append assistant response
        self.context_manager.append_message(
            session_id,
            {"role": "assistant", "content": result}
        )
        
        return result
    
    async def run_stream(
        self,
        message: str,
        session_id: Optional[str] = None
    ) -> AsyncIterator[dict]:
        """
        Run agent with streaming.
        
        Yields Vercel AI SDK V5 protocol events.
        
        Args:
            message: User message
            session_id: Session ID for context continuity
        
        Yields:
            Event dicts (text-delta, tool-input-*, etc.)
        """
        session_id = session_id or "default"
        
        # Append user message
        self.context_manager.append_message(
            session_id,
            {"role": "user", "content": message}
        )
        
        # Stream via Vel
        async for event in self._streaming_adapter.stream(message, session_id):
            yield event
    
    async def run_agent_loop(
        self,
        messages: list[dict],
        system_prompt: str,
        tools: list[str],
        max_turns: int
    ) -> str:
        """
        Core agent loop.
        
        Used by both main agent and subagents.
        Pure Anthropic API calls - no CLI dependency.
        
        Args:
            messages: Conversation history
            system_prompt: System prompt for this agent
            tools: List of tool IDs to make available
            max_turns: Maximum iterations
        
        Returns:
            Final response text
        """
        # Build tool specs for API
        tool_specs = [
            {
                "name": TOOL_DEFINITIONS[t].name,
                "description": TOOL_DEFINITIONS[t].description,
                "input_schema": TOOL_DEFINITIONS[t].input_schema
            }
            for t in tools
            if t in TOOL_DEFINITIONS
        ]
        
        for turn in range(max_turns):
            # Call Anthropic API
            response = self.client.messages.create(
                model=self.model_config.get("model", "claude-sonnet-4-20250514"),
                max_tokens=8192,
                system=system_prompt,
                messages=messages,
                tools=tool_specs
            )
            
            # Check if done (no more tool use)
            if response.stop_reason != "tool_use":
                # Extract text response
                for block in response.content:
                    if hasattr(block, "text"):
                        return block.text
                return ""
            
            # Execute tools
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = await self._execute_tool_by_name(
                        block.name,
                        block.input
                    )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })
            
            # Append to history (APPEND-ONLY for cache efficiency)
            messages.append({
                "role": "assistant",
                "content": [b.model_dump() for b in response.content]
            })
            messages.append({
                "role": "user",
                "content": tool_results
            })
        
        return "Error: Maximum turns reached without completion"
    
    async def _execute_tool_by_name(self, tool_name: str, inputs: dict) -> str:
        """Execute tool by Anthropic tool name."""
        handler = self._tool_handlers.get(tool_name)
        
        if not handler:
            return f"Error: Unknown tool {tool_name}"
        
        try:
            if asyncio.iscoroutinefunction(handler):
                return await handler(**inputs)
            else:
                return handler(**inputs)
        except Exception as e:
            return f"Error executing {tool_name}: {e}"
```

### 9. Package Configuration

**File**: `pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "vel-harness"
version = "0.1.0"
description = "Claude Code-style agent harness built on Vel runtime"
readme = "README.md"
license = "MIT"
requires-python = ">=3.10"
authors = [
    { name = "Your Name", email = "you@example.com" }
]
keywords = [
    "ai",
    "agent",
    "claude",
    "anthropic",
    "vel",
    "llm"
]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]
dependencies = [
    "vel-ai>=0.3.0",
    "anthropic>=0.30.0",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "pytest-cov>=4.0",
    "black>=23.0",
    "ruff>=0.1.0",
    "mypy>=1.0",
]

[project.urls]
Homepage = "https://github.com/yourname/vel-harness"
Documentation = "https://github.com/yourname/vel-harness#readme"
Repository = "https://github.com/yourname/vel-harness"

[tool.hatch.build.targets.wheel]
packages = ["vel_harness"]

[tool.black]
line-length = 100
target-version = ["py310"]

[tool.ruff]
line-length = 100
select = ["E", "F", "I", "W"]

[tool.mypy]
python_version = "3.10"
strict = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**File**: `vel_harness/__init__.py`

```python
"""
Vel Harness: Claude Code-style agent capabilities for Kubernetes deployments.
"""

from .harness import VelHarness
from .agents.config import AgentConfig
from .agents.registry import AgentRegistry
from .skills.loader import SkillLoader, Skill
from .context.manager import ContextManager
from .tools.todo import TodoManager, TodoItem

__version__ = "0.1.0"

__all__ = [
    "VelHarness",
    "AgentConfig",
    "AgentRegistry",
    "SkillLoader",
    "Skill",
    "ContextManager",
    "TodoManager",
    "TodoItem",
]
```

---

## Integration Points

### Usage in Consuming API

```python
# your-api/api/chat.py
import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from vel_harness import VelHarness, AgentConfig
import json

app = FastAPI()

# Initialize harness
harness = VelHarness(
    model={
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
        "api_key": os.environ["ANTHROPIC_API_KEY"]
    },
    skill_dirs=[
        Path("./skills"),
        Path("./skills/company"),
    ],
    custom_agents={
        "researcher": AgentConfig(
            name="researcher",
            system_prompt="You are a research specialist...",
            tools=["read_file", "grep", "glob"],
            max_turns=30,
            description="Researches codebase and documentation"
        )
    },
    working_directory=Path("/workspace"),
    max_turns=100
)

@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    message = body.get("message", "")
    session_id = body.get("session_id", "default")
    
    async def event_stream():
        async for event in harness.run_stream(message, session_id):
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

@app.post("/api/chat/sync")
async def chat_sync(request: Request):
    body = await request.json()
    message = body.get("message", "")
    session_id = body.get("session_id", "default")
    
    result = await harness.run(message, session_id)
    return {"response": result}
```

### Skill Definition Format

```markdown
# your-api/skills/code-review/SKILL.md
---
name: code-review
description: Expert code review with security and performance focus
---

## Code Review Guidelines

When reviewing code, analyze these dimensions:

### Security
- Input validation and sanitization
- SQL injection risks
- XSS vulnerabilities
- Authentication/authorization checks
- Sensitive data exposure

### Performance
- Algorithm complexity (Big O)
- Database query efficiency (N+1 problems)
- Memory usage patterns
- Caching opportunities

### Maintainability
- Code clarity and readability
- Test coverage
- Documentation completeness
- SOLID principles adherence

## Output Format

Provide feedback as:
1. Summary (1-2 sentences)
2. Critical issues (must fix)
3. Suggestions (should consider)
4. Positive observations

Use severity levels: 🔴 Critical, 🟡 Warning, 🟢 Info
```

---

## Implementation Plan

### Phase 1: Foundation (Week 1)
1. [ ] Set up package structure
2. [ ] Copy prompts from Piebald-AI repo
3. [ ] Implement tool definitions
4. [ ] Implement basic tools (bash, file ops, search)
5. [ ] Write unit tests for tools

### Phase 2: Core Features (Week 2)
1. [ ] Implement SkillLoader
2. [ ] Implement AgentRegistry
3. [ ] Implement TaskTool (subagents)
4. [ ] Implement TodoManager
5. [ ] Write integration tests

### Phase 3: Context & Streaming (Week 3)
1. [ ] Implement ContextManager
2. [ ] Implement context compaction
3. [ ] Implement VelHarness main class
4. [ ] Implement streaming adapter
5. [ ] End-to-end tests

### Phase 4: Polish & Documentation (Week 4)
1. [ ] Error handling improvements
2. [ ] Logging and observability
3. [ ] Documentation
4. [ ] Example API integration
5. [ ] Performance testing

---

## Dependencies

### Runtime Dependencies
- `vel-ai>=0.3.0` - Agent runtime with streaming
- `anthropic>=0.30.0` - Anthropic API client
- `pyyaml>=6.0` - YAML parsing for skill frontmatter

### Development Dependencies
- `pytest>=7.0` - Testing
- `pytest-asyncio>=0.21` - Async test support
- `pytest-cov>=4.0` - Coverage reporting
- `black>=23.0` - Code formatting
- `ruff>=0.1.0` - Linting
- `mypy>=1.0` - Type checking

### System Requirements
- Python 3.10+
- `ripgrep` (optional, for faster grep - falls back to grep)

---

## Testing Strategy

### Unit Tests
- Tool implementations (bash, file ops, search)
- SkillLoader parsing
- AgentRegistry configuration
- TodoManager state management

### Integration Tests
- Full agent loop execution
- Subagent spawning and isolation
- Skill loading and injection
- Context compaction

### End-to-End Tests
- Complete chat interactions
- Multi-turn conversations
- Streaming event verification

---

## Reference Implementation: learn-claude-code

The agent loop and skills pattern should follow the implementation in `shareAI-lab/learn-claude-code`, specifically `v4_skills_agent.py` (~550 lines).

**Repository**: https://github.com/shareAI-lab/learn-claude-code

### Core Agent Loop Pattern

```python
# From v4_skills_agent.py - this is the pattern to follow
def agent_loop(messages: list) -> str:
    """The entire agent is this loop."""
    while True:
        response = client.messages.create(
            model=MODEL,
            system=SYSTEM,  # STATIC - never changes (cache efficiency)
            messages=messages,
            tools=ALL_TOOLS,
        )
        
        # Done when no more tool use
        if response.stop_reason != "tool_use":
            return response.content[0].text
        
        # Execute tools, append results
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = execute_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result
                })
        
        # APPEND-ONLY (never edit history - cache efficiency)
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})
```

### Skill Injection Pattern

```python
# From v4_skills_agent.py - skills as tool_result, NOT system prompt
def run_skill(skill_name: str) -> str:
    """
    Load skill content.
    
    KEY INSIGHT: Returns content as tool_result, which becomes part of
    conversation history. Does NOT modify system prompt.
    This preserves prompt caching.
    """
    content = SKILLS.get_skill_content(skill_name)
    return f"""<skill-loaded name="{skill_name}">
{content}
</skill-loaded>

Follow the instructions in the skill above."""
```

### Subagent Pattern (Task Tool)

```python
# From v3_subagent.py (included in v4) - isolated context is the key
def run_task(task: str, agent_id: str = "default") -> str:
    """
    Spawn subagent with FRESH context.
    
    KEY INSIGHT: Child agent starts with empty message history.
    This prevents context pollution and allows focused work.
    """
    # Get agent config (system prompt, tools) from registry
    config = AGENT_REGISTRY.get(agent_id)
    
    # FRESH context - this is the whole point
    child_messages = [{"role": "user", "content": task}]
    
    # Run same loop with different config
    return agent_loop(
        messages=child_messages,
        system_prompt=config.system_prompt,
        tools=config.tools
    )
```

### SkillLoader Pattern

```python
# From v4_skills_agent.py
class SkillLoader:
    """Discovers SKILL.md files from configured directories."""
    
    def __init__(self, skill_dirs: list[Path]):
        self.skill_dirs = skill_dirs
        self._cache = {}
        self._discover()
    
    def _discover(self):
        """Scan for SKILL.md files."""
        for skill_dir in self.skill_dirs:
            for skill_path in skill_dir.rglob("SKILL.md"):
                skill = self._parse_skill(skill_path)
                self._cache[skill.name] = skill
    
    def _parse_skill(self, path: Path):
        """Parse SKILL.md with optional YAML frontmatter."""
        content = path.read_text()
        # Parse frontmatter for name/description
        # Fallback to directory name
        ...
    
    def list_skills(self) -> list[dict]:
        """Return skill metadata for tool description."""
        return [{"name": s.name, "description": s.description} for s in self._cache.values()]
    
    def get_skill_content(self, name: str) -> str:
        """Get full skill content for injection."""
        return self._cache[name].content
```

### Key Principles from learn-claude-code

| Principle | Implementation |
|-----------|----------------|
| System prompt is STATIC | Never put dynamic state in system prompt |
| Messages are append-only | Never edit history, only append |
| Skills as tool_result | Inject into conversation, not system prompt |
| Subagents get fresh context | Empty message history for isolation |
| Model is 80%, code is 20% | Keep orchestration simple, let model work |

### File Reference

```
learn-claude-code/
├── v0_bash_agent.py       # ~50 lines: proves core is tiny
├── v1_basic_agent.py      # ~200 lines: 4 tools, core loop
├── v2_todo_agent.py       # ~300 lines: + TodoManager
├── v3_subagent.py         # ~450 lines: + Task tool, agent registry
├── v4_skills_agent.py     # ~550 lines: + Skill tool, SkillLoader ← REFERENCE THIS
└── docs/
    └── v4-skills-mechanism.md  # Detailed explanation of skills pattern
```

**Instruction for Claude Code**: Clone `https://github.com/shareAI-lab/learn-claude-code` and study `v4_skills_agent.py` before implementing. The harness should follow these patterns exactly, with Vel providing the streaming layer on top.

---

## Subagent Mechanism (Deep Dive)

The Task tool spawns isolated subagents. This is critical for complex tasks that benefit from fresh context.

### Piebald-AI Prompt Files

From `Piebald-AI/claude-code-system-prompts`, copy these to `vel_harness/prompts/agents/`:

| File | Tokens | Purpose |
|------|--------|---------|
| `agent-prompt-task-tool.md` | 294 | System prompt for spawned Task subagent |
| `agent-prompt-explore.md` | 516 | System prompt for Explore subagent |
| `agent-prompt-plan-mode-enhanced.md` | 633 | System prompt for Plan subagent |
| `tool-description-task.md` | 1055 | Task tool description (goes in tool schema) |
| `tool-description-task-async-return-note.md` | 202 | Message returned when subagent launches |

### Task Tool Description

The Task tool description from Piebald-AI (`tool-description-task.md`, 1055 tokens) should be used verbatim. Key elements:

```markdown
# From tool-description-task.md (Piebald-AI)

Launch a sub-agent to handle a specific task independently.

## When to use Task:
- Complex operations requiring multiple steps
- Work that benefits from isolated context
- Parallel-friendly tasks that don't need your current context
- Exploratory work (use agent="explore")
- Planning work (use agent="plan")

## Agent Types:
- "default": General purpose, has all tools
- "explore": Read-only exploration, gathers information
- "plan": Planning focused, creates structured plans

## Important:
- Subagent has FRESH context (doesn't see your conversation)
- Provide ALL necessary context in the description
- Subagent result returns to you as tool_result
- Use for delegation, not for simple tasks
```

### Subagent System Prompts

**Task Agent** (`agent-prompt-task-tool.md`, 294 tokens):
```markdown
You are a focused sub-agent spawned to complete a specific task.

Your context is ISOLATED - you don't have access to the parent conversation.
Everything you need should be in the task description provided.

Guidelines:
- Complete the task thoroughly
- Return a clear, concise result
- If you lack information, say so explicitly
- Don't ask clarifying questions - work with what you have
```

**Explore Agent** (`agent-prompt-explore.md`, 516 tokens):
```markdown
You are an exploration agent. Your job is to gather information.

You have READ-ONLY tools: ReadFile, Glob, Grep, Bash (for read operations)
You CANNOT modify files.

Guidelines:
- Systematically explore the codebase
- Build understanding of architecture and patterns
- Report findings clearly and structured
- Identify relevant files for the parent task
```

**Plan Agent** (`agent-prompt-plan-mode-enhanced.md`, 633 tokens):
```markdown
You are a planning agent. Your job is to create structured plans.

Guidelines:
- Break complex tasks into steps
- Identify dependencies between steps
- Consider edge cases and risks
- Output a clear, actionable plan
- Use TodoWrite to structure the plan
```

### Implementation Pattern

```python
# vel_harness/tools/task.py

class TaskTool:
    """
    Spawns isolated subagents for task delegation.
    
    KEY PRINCIPLES:
    1. Fresh context - subagent starts with empty history
    2. Provide everything - subagent can't see parent conversation
    3. Typed agents - different prompts/tools for different purposes
    """
    
    def __init__(self, harness: "VelHarness"):
        self.harness = harness
    
    async def execute(self, description: str, agent: str = "default") -> str:
        """
        Spawn subagent.
        
        Args:
            description: COMPLETE task description (subagent sees ONLY this)
            agent: "default" | "explore" | "plan"
        
        Returns:
            Subagent result wrapped in XML
        """
        config = self.harness.agent_registry.get(agent)
        
        # FRESH CONTEXT - this is the entire point
        # Subagent cannot see parent conversation
        child_messages = [{"role": "user", "content": description}]
        
        result = await self.harness.run_agent_loop(
            messages=child_messages,
            system_prompt=config.system_prompt,
            tools=config.tools,
            max_turns=config.max_turns
        )
        
        # Return as tool_result to parent
        return f"""<task-result agent="{agent}" status="success">
{result}
</task-result>"""
```

### Agent Registry Configuration

```python
# vel_harness/agents/registry.py

DEFAULT_AGENTS = {
    "default": AgentConfig(
        name="default",
        system_prompt=load_prompt("agents/task.md"),
        tools=["bash", "read_file", "write_file", "edit_file", "glob", "grep"],
        max_turns=50,
        description="General-purpose task execution"
    ),
    "explore": AgentConfig(
        name="explore", 
        system_prompt=load_prompt("agents/explore.md"),
        tools=["read_file", "glob", "grep", "bash"],  # NO write tools
        max_turns=30,
        description="Read-only codebase exploration"
    ),
    "plan": AgentConfig(
        name="plan",
        system_prompt=load_prompt("agents/plan.md"),
        tools=["read_file", "glob", "grep", "todo_write"],  # Planning tools
        max_turns=20,
        description="Structured planning and task breakdown"
    ),
}
```

### Usage Example

When the main agent encounters a complex task:

```
User: "Refactor the authentication module to use JWT"

Main Agent thinks: This is complex, I should explore first, then plan, then execute.

Main Agent: [calls Task tool]
{
  "description": "Explore the current authentication module. Find all auth-related files, understand the current flow, identify dependencies. Report: 1) Current auth mechanism, 2) Files involved, 3) External dependencies, 4) Test coverage",
  "agent": "explore"
}

[Explore subagent runs with fresh context, returns findings]

Main Agent: [calls Task tool]  
{
  "description": "Based on this analysis: [paste explore results]. Create a refactoring plan to migrate from session-based auth to JWT. Include: 1) Steps in order, 2) Files to modify, 3) New files needed, 4) Migration strategy, 5) Testing approach",
  "agent": "plan"
}

[Plan subagent runs, returns structured plan]

Main Agent: Now I'll execute the plan step by step...
```

### Subagent Context Isolation

```
┌─────────────────────────────────────────────────┐
│ Main Agent Context                              │
│                                                 │
│ messages: [user, assistant, user, assistant...] │
│ ↓                                               │
│ Calls Task tool                                 │
└─────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────┐
│ Subagent Context (FRESH)                        │
│                                                 │
│ messages: [{"role": "user", "content": task}]   │
│                                                 │
│ Cannot see parent's conversation                │
│ Has only the task description                   │
└─────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────┐
│ Result returned to Main Agent                   │
│                                                 │
│ <task-result agent="explore">                   │
│   [subagent's findings]                         │
│ </task-result>                                  │
└─────────────────────────────────────────────────┘
```

This isolation is **intentional** - it prevents context pollution and allows subagents to focus on their specific task without being influenced by irrelevant parent context.

---

## Appendix: External Resources

### Repositories to Clone/Reference

1. **Claude Code System Prompts**
   - URL: https://github.com/Piebald-AI/claude-code-system-prompts
   - Purpose: All system prompts, tool descriptions, subagent prompts
   - Files needed:
     - `system-prompts/system-prompt-main-system-prompt.md`
     - `system-prompts/agent-prompt-explore.md`
     - `system-prompts/agent-prompt-plan-mode-enhanced.md`
     - `system-prompts/agent-prompt-task-tool.md`
     - `system-prompts/agent-prompt-conversation-summarization.md`
     - `system-prompts/tool-description-*.md` (all tool descriptions)

2. **Learn Claude Code**
   - URL: https://github.com/shareAI-lab/learn-claude-code
   - Purpose: Reference implementation for agent loop pattern
   - Key insight: Pure Python agent loop without CLI dependency

3. **Vel**
   - URL: https://github.com/rscheiwe/vel
   - Purpose: Runtime dependency for streaming and protocol translation
   - Install: `pip install vel-ai`

### Key Documentation

1. **Anthropic Messages API**
   - https://docs.anthropic.com/en/api/messages
   - Tool use, streaming, prompt caching

2. **Vercel AI SDK V5 Stream Protocol**
   - https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol
   - Event types and format specification

3. **Anthropic Prompt Caching**
   - https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
   - Why system prompt must be static, append-only messages

---

## Success Criteria

1. ✅ Deploys in Kubernetes (no CLI dependency)
2. ✅ Streams Vercel AI SDK V5 compliant events
3. ✅ Skills loaded from API codebase directories
4. ✅ Subagents spawn with isolated context
5. ✅ Planning via TodoWrite tool
6. ✅ Context compaction for long conversations
7. ✅ Uses actual Claude Code prompts from Piebald-AI
8. ✅ Works with Vel runtime for streaming