# Vel Harness PRD: Deep Agent Framework

**Version:** 1.0  
**Date:** January 2025  
**Author:** Product  
**Status:** Ready for Implementation

---

## Executive Summary

Vel Harness is a deep agent framework built on Mesh (graph orchestration) and Vel (agent runtime). It provides Claude Code-style capabilities—planning, file system access, sandboxed execution, subagent spawning—with a skills system optimized for data analysis, decision workflows, research, and general-purpose automation.

### What Vel Harness Is

A production-ready agent harness that can:
- Plan and execute complex, multi-step tasks
- Read, write, and edit files locally
- Execute Python and shell commands in a secure sandbox
- Query databases and visualize data
- Spawn parallel subagents for deep research
- Route decisions through approval workflows
- Generate reports, charts, and documents

### What Vel Harness Is NOT

- A coding-specific agent (though it can write code)
- A replacement for Claude Code (different focus)
- An IDE integration

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Project Structure](#2-project-structure)
3. [Feature 1: Planning Middleware](#3-feature-1-planning-middleware)
4. [Feature 2: Filesystem Middleware](#4-feature-2-filesystem-middleware)
5. [Feature 3: Local Sandbox Backend](#5-feature-3-local-sandbox-backend)
6. [Feature 4: Skills System](#6-feature-4-skills-system)
7. [Feature 5: Database Backend](#7-feature-5-database-backend)
8. [Feature 6: Subagent System](#8-feature-6-subagent-system)
9. [Feature 7: Deep Agent Factory](#9-feature-7-deep-agent-factory)
10. [Built-in Skills](#10-built-in-skills)
11. [System Prompt](#11-system-prompt)
12. [CLI Interface](#12-cli-interface)
13. [Implementation Order](#13-implementation-order)
14. [Testing Requirements](#14-testing-requirements)
15. [API Reference](#15-api-reference)

---

## 1. Architecture Overview

### 1.1 Stack Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User Application                             │
│                    (CLI, API, Web Interface)                        │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        VEL HARNESS                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                   create_deep_agent()                        │    │
│  │                                                              │    │
│  │  Assembles Mesh graph with:                                  │    │
│  │  • PlanningMiddleware → TodoList node                        │    │
│  │  • FilesystemMiddleware → File tool nodes                    │    │
│  │  • SandboxBackend → Execution backend                        │    │
│  │  • SkillsMiddleware → Skill loader                           │    │
│  │  • SubagentMiddleware → Parallel subgraph spawning           │    │
│  │  • DatabaseBackend → SQL execution                           │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                      Skills System                           │    │
│  │                                                              │    │
│  │  /skills/data-query/SKILL.md                                │    │
│  │  /skills/decision-workflow/SKILL.md                         │    │
│  │  /skills/research/SKILL.md                                  │    │
│  │  /skills/reporting/SKILL.md                                 │    │
│  │  /skills/[user-defined]/SKILL.md                            │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                            MESH                                      │
│                   (Graph Orchestration)                             │
├─────────────────────────────────────────────────────────────────────┤
│  • Parallel execution (fan-out/fan-in)                              │
│  • Interrupts (human-in-the-loop)                                   │
│  • Checkpointing (persistence)                                      │
│  • Subgraph composition (isolation)                                 │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                             VEL                                      │
│                      (Agent Runtime)                                │
├─────────────────────────────────────────────────────────────────────┤
│  • LLM providers (OpenAI, Anthropic, Google)                        │
│  • Tool execution                                                   │
│  • Stream protocol (Vercel AI SDK V5)                               │
│  • Message aggregation                                              │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 Execution Flow

```
User Input
    │
    ▼
┌─────────────┐
│  Planning   │──────▶ Creates/updates todo list
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Skills    │──────▶ Loads relevant SKILL.md
└──────┬──────┘
       │
       ▼
┌─────────────┐        ┌─────────────┐
│    Agent    │◄──────▶│    Tools    │
│   (LLM)     │        │ (files, db, │
└──────┬──────┘        │  sandbox)   │
       │               └─────────────┘
       │
       ▼
┌─────────────┐
│   Router    │
└──────┬──────┘
       │
       ├──────────▶ Continue (more work needed)
       │
       ├──────────▶ Subagent (spawn isolated task)
       │
       ├──────────▶ Interrupt (human approval needed)
       │
       └──────────▶ Done (return result)
```

### 1.3 Dependencies

```toml
[project]
name = "vel-harness"
version = "0.1.0"
description = "Deep agent harness for data, decisions, and research"
dependencies = [
    "vel-ai>=0.3.0",
    "mesh>=0.2.0",
]

[project.optional-dependencies]
sandbox = []  # No extra deps - uses OS primitives
database = ["asyncpg>=0.29.0", "sqlalchemy>=2.0.0"]
all = ["vel-harness[database]"]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "black", "ruff", "mypy"]
```

---

## 2. Project Structure

```
vel-harness/
├── pyproject.toml
├── README.md
├── LICENSE
│
├── vel/
│   ├── __init__.py              # Public exports
│   ├── agent.py                 # create_deep_agent() factory
│   ├── config.py                # Configuration classes
│   │
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── base.py              # Middleware protocol
│   │   ├── planning.py          # TodoListMiddleware
│   │   ├── filesystem.py        # FilesystemMiddleware
│   │   ├── skills.py            # SkillsMiddleware
│   │   ├── subagents.py         # SubagentMiddleware
│   │   └── hitl.py              # HumanInTheLoopMiddleware
│   │
│   ├── backends/
│   │   ├── __init__.py
│   │   ├── protocol.py          # Backend protocols
│   │   ├── state.py             # In-memory StateBackend
│   │   ├── sandbox.py           # Local OS sandbox
│   │   ├── database.py          # SQL database backend
│   │   └── composite.py         # Route-based composite
│   │
│   ├── skills/
│   │   ├── __init__.py
│   │   ├── loader.py            # Skill loader
│   │   ├── registry.py          # Skill registry
│   │   └── builtin/             # Built-in skills
│   │       ├── data-query/
│   │       │   └── SKILL.md
│   │       ├── decision-workflow/
│   │       │   └── SKILL.md
│   │       ├── research/
│   │       │   └── SKILL.md
│   │       └── reporting/
│   │           └── SKILL.md
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── filesystem.py        # File tools
│   │   ├── sandbox.py           # Execution tools
│   │   ├── database.py          # SQL tools
│   │   └── planning.py          # Todo tools
│   │
│   ├── prompts/
│   │   ├── __init__.py
│   │   └── system.py            # System prompt builder
│   │
│   └── cli/
│       ├── __init__.py
│       └── main.py              # CLI entry point
│
├── skills/                      # User skills directory (gitignored template)
│   └── .gitkeep
│
├── examples/
│   ├── data_analysis.py
│   ├── decision_workflow.py
│   ├── research_report.py
│   └── custom_skill.py
│
└── tests/
    ├── test_planning.py
    ├── test_filesystem.py
    ├── test_sandbox.py
    ├── test_skills.py
    ├── test_database.py
    ├── test_subagents.py
    └── integration/
        └── test_deep_agent.py
```

---

## 3. Feature 1: Planning Middleware

### 3.1 Overview

The planning middleware provides a `write_todos` tool that enables the agent to:
- Break down complex tasks into discrete steps
- Track progress on multi-step workflows
- Adapt plans as new information emerges

This mirrors Claude Code's planning behavior.

### 3.2 Implementation

```python
# vel/middleware/planning.py

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
from vel import ToolSpec

@dataclass
class TodoItem:
    """A single todo item"""
    id: str
    task: str
    status: str = "pending"  # pending, in_progress, done, blocked
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task": self.task,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "notes": self.notes,
        }


@dataclass
class TodoList:
    """Manages the todo list state"""
    items: list[TodoItem] = field(default_factory=list)
    current_task: str = ""
    
    def add(self, task: str) -> TodoItem:
        item = TodoItem(
            id=f"todo_{len(self.items)}",
            task=task,
        )
        self.items.append(item)
        return item
    
    def complete(self, todo_id: str, notes: Optional[str] = None) -> bool:
        for item in self.items:
            if item.id == todo_id:
                item.status = "done"
                item.completed_at = datetime.utcnow().isoformat()
                if notes:
                    item.notes = notes
                return True
        return False
    
    def block(self, todo_id: str, reason: str) -> bool:
        for item in self.items:
            if item.id == todo_id:
                item.status = "blocked"
                item.notes = reason
                return True
        return False
    
    def get_pending(self) -> list[TodoItem]:
        return [t for t in self.items if t.status == "pending"]
    
    def get_completed(self) -> list[TodoItem]:
        return [t for t in self.items if t.status == "done"]
    
    def to_markdown(self) -> str:
        """Render todo list as markdown"""
        lines = ["## Current Task", f"{self.current_task}", "", "## Todo List"]
        
        for item in self.items:
            checkbox = "x" if item.status == "done" else " "
            status_emoji = {
                "pending": "⏳",
                "in_progress": "🔄",
                "done": "✅",
                "blocked": "🚫",
            }.get(item.status, "")
            
            lines.append(f"- [{checkbox}] {status_emoji} {item.task}")
            if item.notes:
                lines.append(f"  - Note: {item.notes}")
        
        return "\n".join(lines)


class PlanningMiddleware:
    """
    Middleware that provides planning capabilities via a todo list.
    
    Adds the `write_todos` tool to the agent.
    """
    
    def __init__(self):
        self.todo_list = TodoList()
    
    def get_tools(self) -> list[ToolSpec]:
        """Return planning tools"""
        return [
            ToolSpec.from_function(
                self.write_todos,
                name="write_todos",
                description="""
                Update the todo list with current progress and next steps.
                Use this tool to:
                - Plan out complex tasks before starting
                - Track progress on multi-step work
                - Mark items complete as you finish them
                - Adapt your plan when new information emerges
                
                Always create a plan before starting complex work.
                """,
            )
        ]
    
    def write_todos(
        self,
        current_task: str,
        next_steps: list[str],
        completed: Optional[list[str]] = None,
        blocked: Optional[list[dict]] = None,
    ) -> dict:
        """
        Update the todo list with current progress and next steps.
        
        Args:
            current_task: What you're working on right now
            next_steps: List of upcoming tasks to add
            completed: List of todo IDs that are now done
            blocked: List of {"id": str, "reason": str} for blocked items
        
        Returns:
            Current state of the todo list
        """
        # Update current task
        self.todo_list.current_task = current_task
        
        # Mark completed
        if completed:
            for todo_id in completed:
                self.todo_list.complete(todo_id)
        
        # Mark blocked
        if blocked:
            for item in blocked:
                self.todo_list.block(item["id"], item.get("reason", ""))
        
        # Add new steps
        new_items = []
        for step in next_steps:
            item = self.todo_list.add(step)
            new_items.append(item.to_dict())
        
        return {
            "current_task": current_task,
            "new_items": new_items,
            "pending_count": len(self.todo_list.get_pending()),
            "completed_count": len(self.todo_list.get_completed()),
            "todo_list": self.todo_list.to_markdown(),
        }
    
    def get_system_prompt_segment(self) -> str:
        """Return system prompt segment for planning"""
        return """
## Planning

You have a `write_todos` tool for planning and tracking complex tasks.

**When to use planning:**
- Before starting any task that requires multiple steps
- When you need to break down a complex request
- To track progress on ongoing work
- When you need to adapt your approach based on new information

**How to plan effectively:**
1. Start by identifying the high-level goal
2. Break it down into concrete, actionable steps
3. Update the plan as you learn more
4. Mark items complete as you finish them

**Example:**
User asks: "Analyze our Q4 sales data and create a report"

You should first call write_todos:
```
write_todos(
    current_task="Analyzing Q4 sales data",
    next_steps=[
        "Load and examine the sales data structure",
        "Calculate key metrics (total revenue, growth, top products)",
        "Create visualizations for trends",
        "Write executive summary",
        "Compile final report"
    ]
)
```

Then work through each step, updating the plan as needed.
"""
    
    def get_state(self) -> dict:
        """Get current planning state for persistence"""
        return {
            "current_task": self.todo_list.current_task,
            "items": [item.to_dict() for item in self.todo_list.items],
        }
    
    def load_state(self, state: dict) -> None:
        """Load planning state from persistence"""
        self.todo_list.current_task = state.get("current_task", "")
        self.todo_list.items = [
            TodoItem(**item) for item in state.get("items", [])
        ]
```

### 3.3 Acceptance Criteria

- [ ] `write_todos` tool is available to agent
- [ ] Todo items can be added, completed, and blocked
- [ ] Todo list renders as markdown
- [ ] State can be persisted and restored
- [ ] System prompt segment explains planning usage
- [ ] Integration with Mesh state management

---

## 4. Feature 2: Filesystem Middleware

### 4.1 Overview

Provides file system tools for reading, writing, and editing files. This enables:
- Context management (offload large content to files)
- Document generation (reports, markdown, etc.)
- Working with user-provided files
- Persistent storage of findings

### 4.2 Implementation

```python
# vel/middleware/filesystem.py

from dataclasses import dataclass, field
from typing import Optional, Protocol
from pathlib import Path
from datetime import datetime
from vel import ToolSpec
import fnmatch
import re


class FilesystemBackend(Protocol):
    """Protocol for filesystem backends"""
    
    def ls(self, path: str) -> dict: ...
    def read_file(self, path: str, offset: int, limit: int) -> dict: ...
    def write_file(self, path: str, content: str) -> dict: ...
    def edit_file(self, path: str, old_text: str, new_text: str) -> dict: ...
    def glob(self, pattern: str) -> dict: ...
    def grep(self, pattern: str, path: str, include: Optional[str]) -> dict: ...


@dataclass
class FileData:
    """Metadata and content for a file"""
    content: list[str]  # Lines
    created_at: str
    modified_at: str
    size_bytes: int = 0
    
    @classmethod
    def from_content(cls, content: str) -> "FileData":
        lines = content.split("\n")
        now = datetime.utcnow().isoformat()
        return cls(
            content=lines,
            created_at=now,
            modified_at=now,
            size_bytes=len(content.encode("utf-8")),
        )


class StateFilesystemBackend:
    """
    In-memory filesystem backend.
    Files are stored in state and don't persist across sessions.
    """
    
    def __init__(self):
        self._files: dict[str, FileData] = {}
    
    def ls(self, path: str = "/") -> dict:
        """List files and directories"""
        path = path.rstrip("/")
        if not path:
            path = "/"
        
        entries = []
        dirs_seen = set()
        
        for file_path in self._files.keys():
            if path == "/" or file_path.startswith(path + "/"):
                # Get relative path
                if path == "/":
                    rel_path = file_path
                else:
                    rel_path = file_path[len(path) + 1:]
                
                # Check if it's a direct child
                parts = rel_path.split("/")
                if len(parts) == 1:
                    # Direct file
                    entries.append({
                        "name": parts[0],
                        "type": "file",
                        "path": file_path,
                        "size": self._files[file_path].size_bytes,
                    })
                else:
                    # Directory
                    dir_name = parts[0]
                    if dir_name not in dirs_seen:
                        dirs_seen.add(dir_name)
                        entries.append({
                            "name": dir_name,
                            "type": "directory",
                            "path": f"{path}/{dir_name}" if path != "/" else f"/{dir_name}",
                        })
        
        return {
            "path": path,
            "entries": sorted(entries, key=lambda x: (x["type"], x["name"])),
        }
    
    def read_file(self, path: str, offset: int = 0, limit: int = 100) -> dict:
        """Read file contents with pagination"""
        if path not in self._files:
            return {"error": f"File not found: {path}"}
        
        file_data = self._files[path]
        total_lines = len(file_data.content)
        
        # Apply pagination
        lines = file_data.content[offset:offset + limit]
        
        # Add line numbers
        numbered_lines = [
            f"{i + offset + 1:6d} | {line}"
            for i, line in enumerate(lines)
        ]
        
        return {
            "path": path,
            "content": "\n".join(numbered_lines),
            "lines_returned": len(lines),
            "total_lines": total_lines,
            "offset": offset,
            "has_more": offset + limit < total_lines,
        }
    
    def write_file(self, path: str, content: str) -> dict:
        """Write content to file (creates or overwrites)"""
        # Ensure path starts with /
        if not path.startswith("/"):
            path = "/" + path
        
        self._files[path] = FileData.from_content(content)
        
        return {
            "status": "ok",
            "path": path,
            "lines": len(content.split("\n")),
            "size_bytes": len(content.encode("utf-8")),
        }
    
    def edit_file(self, path: str, old_text: str, new_text: str) -> dict:
        """Edit file by replacing old_text with new_text"""
        if path not in self._files:
            return {"error": f"File not found: {path}"}
        
        content = "\n".join(self._files[path].content)
        
        if old_text not in content:
            return {"error": "old_text not found in file"}
        
        count = content.count(old_text)
        if count > 1:
            return {"error": f"old_text appears {count} times. Must be unique."}
        
        new_content = content.replace(old_text, new_text)
        self._files[path] = FileData.from_content(new_content)
        self._files[path].created_at = self._files[path].created_at  # Preserve
        
        return {
            "status": "ok",
            "path": path,
            "lines_changed": abs(new_text.count("\n") - old_text.count("\n")),
        }
    
    def glob(self, pattern: str) -> dict:
        """Find files matching glob pattern"""
        matches = []
        for path in self._files.keys():
            if fnmatch.fnmatch(path, pattern):
                matches.append(path)
        
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
    ) -> dict:
        """Search for pattern in files"""
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return {"error": f"Invalid regex: {e}"}
        
        matches = []
        files_searched = 0
        
        for file_path, file_data in self._files.items():
            # Check path filter
            if not file_path.startswith(path):
                continue
            
            # Check include filter
            if include and not fnmatch.fnmatch(file_path, include):
                continue
            
            files_searched += 1
            
            for line_num, line in enumerate(file_data.content, 1):
                if regex.search(line):
                    matches.append({
                        "file": file_path,
                        "line": line_num,
                        "content": line.strip(),
                    })
        
        return {
            "pattern": pattern,
            "path": path,
            "files_searched": files_searched,
            "matches": matches[:100],  # Limit results
            "total_matches": len(matches),
            "truncated": len(matches) > 100,
        }


class FilesystemMiddleware:
    """
    Middleware providing filesystem tools.
    
    Supports multiple backends:
    - StateFilesystemBackend: In-memory (default)
    - SandboxFilesystemBackend: Real filesystem in sandbox
    - CompositeBackend: Route different paths to different backends
    """
    
    def __init__(self, backend: Optional[FilesystemBackend] = None):
        self.backend = backend or StateFilesystemBackend()
    
    def get_tools(self) -> list[ToolSpec]:
        """Return filesystem tools"""
        return [
            ToolSpec.from_function(
                self._ls,
                name="ls",
                description="List files and directories at a path",
            ),
            ToolSpec.from_function(
                self._read_file,
                name="read_file",
                description="""
                Read contents of a file with optional pagination.
                Use offset and limit for large files.
                """,
            ),
            ToolSpec.from_function(
                self._write_file,
                name="write_file",
                description="""
                Write content to a file. Creates the file if it doesn't exist,
                or overwrites if it does. Use for creating new documents,
                saving results, or storing data.
                """,
            ),
            ToolSpec.from_function(
                self._edit_file,
                name="edit_file",
                description="""
                Edit a file by replacing specific text. The old_text must
                appear exactly once in the file. Use for making targeted
                changes to existing files.
                """,
            ),
            ToolSpec.from_function(
                self._glob,
                name="glob",
                description="Find files matching a glob pattern (e.g., '**/*.md')",
            ),
            ToolSpec.from_function(
                self._grep,
                name="grep",
                description="Search for a regex pattern in files",
            ),
        ]
    
    def _ls(self, path: str = "/") -> dict:
        """List files and directories"""
        return self.backend.ls(path)
    
    def _read_file(
        self,
        path: str,
        offset: int = 0,
        limit: int = 100,
    ) -> dict:
        """Read file contents"""
        return self.backend.read_file(path, offset, limit)
    
    def _write_file(self, path: str, content: str) -> dict:
        """Write file"""
        return self.backend.write_file(path, content)
    
    def _edit_file(self, path: str, old_text: str, new_text: str) -> dict:
        """Edit file"""
        return self.backend.edit_file(path, old_text, new_text)
    
    def _glob(self, pattern: str) -> dict:
        """Glob files"""
        return self.backend.glob(pattern)
    
    def _grep(
        self,
        pattern: str,
        path: str = "/",
        include: Optional[str] = None,
    ) -> dict:
        """Grep files"""
        return self.backend.grep(pattern, path, include)
    
    def get_system_prompt_segment(self) -> str:
        """Return system prompt segment for filesystem"""
        return """
## File System

You have tools for working with files:

- `ls(path)` - List directory contents
- `read_file(path, offset, limit)` - Read file contents (paginated)
- `write_file(path, content)` - Create or overwrite a file
- `edit_file(path, old_text, new_text)` - Make targeted edits
- `glob(pattern)` - Find files by pattern
- `grep(pattern, path, include)` - Search file contents

**When to use files:**
- Save important findings or intermediate results
- Create reports, documents, or exports
- Offload large content from context
- Store data for later steps

**File paths:**
- All paths start with `/`
- Use descriptive names: `/reports/q4_analysis.md`
- Organize by purpose: `/data/`, `/reports/`, `/notes/`

**Best practices:**
- Write findings to files as you work
- Use files to manage large outputs
- Create markdown files for reports
- Save code to files before executing
"""
```

### 4.3 Acceptance Criteria

- [ ] `ls` lists files and directories
- [ ] `read_file` supports pagination with offset/limit
- [ ] `write_file` creates new files and overwrites existing
- [ ] `edit_file` replaces unique text occurrences
- [ ] `glob` finds files by pattern
- [ ] `grep` searches file contents with regex
- [ ] StateFilesystemBackend works entirely in memory
- [ ] Backend is swappable (sandbox, composite)
- [ ] System prompt explains file usage

---

## 5. Feature 3: Local Sandbox Backend

### 5.1 Overview

Provides secure code execution using OS-level sandboxing:
- **macOS**: Seatbelt (sandbox-exec)
- **Linux**: bubblewrap + seccomp BPF

This enables Python and shell execution without risking the host system.

### 5.2 Implementation

```python
# vel/backends/sandbox.py

import subprocess
import platform
import shutil
import tempfile
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class ExecutionResult:
    """Result of sandbox execution"""
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False
    
    def to_dict(self) -> dict:
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "success": self.exit_code == 0 and not self.timed_out,
        }


class SandboxNotAvailableError(Exception):
    """Raised when sandbox is not available on this platform"""
    pass


class BaseSandbox:
    """Base class for sandbox implementations"""
    
    def __init__(
        self,
        working_dir: str,
        allowed_paths: Optional[list[str]] = None,
        network: bool = False,
        timeout: int = 30,
    ):
        self.working_dir = Path(working_dir).resolve()
        self.allowed_paths = allowed_paths or []
        self.network = network
        self.timeout = timeout
        
        # Ensure working directory exists
        self.working_dir.mkdir(parents=True, exist_ok=True)
    
    def execute(self, command: str, timeout: Optional[int] = None) -> ExecutionResult:
        """Execute command in sandbox"""
        raise NotImplementedError
    
    def execute_python(
        self,
        code: str,
        timeout: Optional[int] = None,
    ) -> ExecutionResult:
        """Execute Python code in sandbox"""
        # Write code to temp file
        script_path = self.working_dir / "_temp_script.py"
        script_path.write_text(code)
        
        try:
            result = self.execute(f"python3 {script_path}", timeout)
        finally:
            # Clean up
            script_path.unlink(missing_ok=True)
        
        return result


class BubblewrapSandbox(BaseSandbox):
    """
    Linux sandbox using bubblewrap.
    
    Provides filesystem and network isolation via Linux namespaces.
    """
    
    def __init__(self, **kwargs):
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
    
    def _build_command(self, command: str) -> list[str]:
        """Build bwrap command with arguments"""
        args = [
            "bwrap",
            # Read-only system directories
            "--ro-bind", "/usr", "/usr",
            "--ro-bind", "/lib", "/lib",
            "--ro-bind", "/lib64", "/lib64",
            "--ro-bind", "/bin", "/bin",
            "--ro-bind", "/sbin", "/sbin",
            "--symlink", "/usr/lib", "/lib",
            "--symlink", "/usr/bin", "/bin",
            
            # Required virtual filesystems
            "--proc", "/proc",
            "--dev", "/dev",
            
            # Temp directory
            "--tmpfs", "/tmp",
            
            # Working directory (read-write)
            "--bind", str(self.working_dir), str(self.working_dir),
            "--chdir", str(self.working_dir),
            
            # Isolation
            "--unshare-all",
            "--die-with-parent",
        ]
        
        # Network isolation
        if not self.network:
            args.append("--unshare-net")
        
        # Additional allowed paths (read-only)
        for path in self.allowed_paths:
            if Path(path).exists():
                args.extend(["--ro-bind", path, path])
        
        # Command to execute
        args.extend(["--", "bash", "-c", command])
        
        return args
    
    def execute(self, command: str, timeout: Optional[int] = None) -> ExecutionResult:
        """Execute command in bubblewrap sandbox"""
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


class SeatbeltSandbox(BaseSandbox):
    """
    macOS sandbox using Seatbelt (sandbox-exec).
    
    Provides filesystem and network isolation via macOS sandbox profiles.
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        if platform.system() != "Darwin":
            raise SandboxNotAvailableError("SeatbeltSandbox requires macOS")
    
    def _build_profile(self) -> str:
        """Build Seatbelt profile (SBPL)"""
        # Base profile
        profile = """
(version 1)
(deny default)

;; Allow process operations
(allow process-fork)
(allow process-exec)
(allow signal)

;; Allow reading system libraries and binaries
(allow file-read*
    (subpath "/usr")
    (subpath "/System")
    (subpath "/Library")
    (subpath "/bin")
    (subpath "/sbin")
    (subpath "/private/var/db")
    (subpath "/Applications/Xcode.app")
    (subpath "/Library/Developer")
)

;; Allow /dev access (null, urandom, etc.)
(allow file-read* file-write*
    (subpath "/dev")
)

;; Allow temp directories
(allow file-read* file-write*
    (subpath "/tmp")
    (subpath "/private/tmp")
    (subpath "/var/folders")
)

;; Allow working directory (read-write)
(allow file-read* file-write*
    (subpath "{working_dir}")
)

;; Allow Python/Homebrew paths
(allow file-read*
    (subpath "/opt/homebrew")
    (subpath "/usr/local")
)
""".format(working_dir=self.working_dir)
        
        # Additional allowed paths
        for path in self.allowed_paths:
            profile += f'\n(allow file-read* (subpath "{path}"))'
        
        # Network policy
        if self.network:
            profile += "\n(allow network*)"
        else:
            profile += "\n(deny network*)"
        
        return profile
    
    def execute(self, command: str, timeout: Optional[int] = None) -> ExecutionResult:
        """Execute command in Seatbelt sandbox"""
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


def create_sandbox(
    working_dir: str,
    allowed_paths: Optional[list[str]] = None,
    network: bool = False,
    timeout: int = 30,
) -> BaseSandbox:
    """
    Factory function to create appropriate sandbox for current OS.
    
    Args:
        working_dir: Directory for sandboxed file operations
        allowed_paths: Additional paths to allow read access
        network: Whether to allow network access
        timeout: Default command timeout in seconds
    
    Returns:
        Sandbox instance for current platform
    
    Raises:
        SandboxNotAvailableError: If no sandbox available for platform
    """
    system = platform.system()
    
    if system == "Linux":
        return BubblewrapSandbox(
            working_dir=working_dir,
            allowed_paths=allowed_paths,
            network=network,
            timeout=timeout,
        )
    elif system == "Darwin":
        return SeatbeltSandbox(
            working_dir=working_dir,
            allowed_paths=allowed_paths,
            network=network,
            timeout=timeout,
        )
    else:
        raise SandboxNotAvailableError(
            f"No sandbox available for {system}. "
            "Supported platforms: Linux (bubblewrap), macOS (Seatbelt)"
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
    ):
        self.working_dir = Path(working_dir).resolve()
        self.sandbox = create_sandbox(
            working_dir=str(self.working_dir),
            network=network,
            timeout=timeout,
        )
    
    def ls(self, path: str = "/") -> dict:
        """List directory contents via sandbox"""
        full_path = self._resolve_path(path)
        result = self.sandbox.execute(f'ls -la "{full_path}"')
        
        if result.exit_code != 0:
            return {"error": result.stderr}
        
        return {
            "path": path,
            "listing": result.stdout,
        }
    
    def read_file(self, path: str, offset: int = 0, limit: int = 100) -> dict:
        """Read file via sandbox"""
        full_path = self._resolve_path(path)
        
        # Use sed for pagination
        start_line = offset + 1
        end_line = offset + limit
        result = self.sandbox.execute(
            f'sed -n "{start_line},{end_line}p" "{full_path}"'
        )
        
        if result.exit_code != 0:
            return {"error": result.stderr}
        
        # Get total line count
        wc_result = self.sandbox.execute(f'wc -l < "{full_path}"')
        total_lines = int(wc_result.stdout.strip()) if wc_result.exit_code == 0 else 0
        
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
    
    def write_file(self, path: str, content: str) -> dict:
        """Write file via sandbox"""
        full_path = self._resolve_path(path)
        
        # Ensure parent directory exists
        parent = Path(full_path).parent
        self.sandbox.execute(f'mkdir -p "{parent}"')
        
        # Write using heredoc to handle special characters
        result = self.sandbox.execute(
            f"cat << 'VEL_EOF' > \"{full_path}\"\n{content}\nVEL_EOF"
        )
        
        if result.exit_code != 0:
            return {"error": result.stderr}
        
        return {
            "status": "ok",
            "path": path,
            "lines": len(content.split("\n")),
        }
    
    def edit_file(self, path: str, old_text: str, new_text: str) -> dict:
        """Edit file via sandbox"""
        # Read current content
        full_path = self._resolve_path(path)
        result = self.sandbox.execute(f'cat "{full_path}"')
        
        if result.exit_code != 0:
            return {"error": f"Cannot read file: {result.stderr}"}
        
        content = result.stdout
        
        if old_text not in content:
            return {"error": "old_text not found in file"}
        
        if content.count(old_text) > 1:
            return {"error": "old_text appears multiple times. Must be unique."}
        
        new_content = content.replace(old_text, new_text)
        return self.write_file(path, new_content)
    
    def glob(self, pattern: str) -> dict:
        """Find files matching pattern"""
        result = self.sandbox.execute(
            f'find "{self.working_dir}" -path "{self.working_dir}/{pattern}"'
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
    ) -> dict:
        """Search files via sandbox"""
        full_path = self._resolve_path(path)
        
        cmd = f'grep -rn "{pattern}" "{full_path}"'
        if include:
            cmd = f'grep -rn --include="{include}" "{pattern}" "{full_path}"'
        
        result = self.sandbox.execute(cmd)
        
        matches = []
        for line in result.stdout.strip().split("\n"):
            if line and ":" in line:
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    matches.append({
                        "file": parts[0].replace(str(self.working_dir), ""),
                        "line": int(parts[1]),
                        "content": parts[2].strip(),
                    })
        
        return {
            "pattern": pattern,
            "path": path,
            "matches": matches[:100],
            "total_matches": len(matches),
            "truncated": len(matches) > 100,
        }
    
    def execute(self, command: str, timeout: Optional[int] = None) -> dict:
        """Execute shell command in sandbox"""
        result = self.sandbox.execute(command, timeout)
        return result.to_dict()
    
    def execute_python(self, code: str, timeout: Optional[int] = None) -> dict:
        """Execute Python code in sandbox"""
        result = self.sandbox.execute_python(code, timeout)
        return result.to_dict()
    
    def _resolve_path(self, path: str) -> str:
        """Resolve path relative to working directory"""
        if path.startswith("/"):
            path = path[1:]
        return str(self.working_dir / path)
```

### 5.3 Execution Tools

```python
# vel/tools/sandbox.py

from vel import ToolSpec
from vel.backends.sandbox import SandboxFilesystemBackend


def create_execution_tools(backend: SandboxFilesystemBackend) -> list[ToolSpec]:
    """Create execution tools for sandbox backend"""
    
    def execute(command: str, timeout: int = 30) -> dict:
        """
        Execute a shell command in the sandbox.
        
        Args:
            command: Shell command to execute
            timeout: Maximum execution time in seconds
        
        Returns:
            Dict with stdout, stderr, exit_code, success
        """
        return backend.execute(command, timeout)
    
    def execute_python(code: str, timeout: int = 60) -> dict:
        """
        Execute Python code in the sandbox.
        
        Args:
            code: Python code to execute
            timeout: Maximum execution time in seconds
        
        Returns:
            Dict with stdout, stderr, exit_code, success
        """
        return backend.execute_python(code, timeout)
    
    return [
        ToolSpec.from_function(
            execute,
            name="execute",
            description="""
            Execute a shell command in a secure sandbox.
            
            The sandbox isolates execution from your system:
            - Filesystem access limited to working directory
            - No network access (by default)
            - Process isolation
            
            Use for: running scripts, installing packages (in sandbox),
            file operations, data processing.
            """,
        ),
        ToolSpec.from_function(
            execute_python,
            name="execute_python",
            description="""
            Execute Python code in a secure sandbox.
            
            The code runs in an isolated environment with:
            - Standard library available
            - Common packages (pandas, numpy, matplotlib if installed)
            - Access to files in working directory
            
            Use for: data analysis, file processing, calculations,
            generating charts, any Python task.
            
            Example:
            ```python
            import pandas as pd
            df = pd.read_csv('data.csv')
            print(df.describe())
            ```
            """,
        ),
    ]
```

### 5.4 Acceptance Criteria

- [ ] `BubblewrapSandbox` works on Linux
- [ ] `SeatbeltSandbox` works on macOS
- [ ] `create_sandbox()` auto-detects platform
- [ ] `execute()` runs shell commands with timeout
- [ ] `execute_python()` runs Python code
- [ ] Filesystem operations work through sandbox
- [ ] Network is blocked by default
- [ ] Working directory is writable
- [ ] System directories are protected
- [ ] Appropriate errors for unsupported platforms

---

## 6. Feature 4: Skills System

### 6.1 Overview

Skills are procedural knowledge documents (SKILL.md) that teach the agent how to approach specific domains. Unlike tools (which are functions), skills are instructions loaded on-demand.

### 6.2 SKILL.md Format

```markdown
---
name: skill-name
description: Brief description of what this skill does
version: 1.0.0
author: optional
tools_required:
  - tool_name_1
  - tool_name_2
tags:
  - category1
  - category2
---

# Skill Name

## When to Use

Describe when this skill should be activated...

## Approach

Step-by-step methodology...

## Examples

Concrete examples of using this skill...

## Constraints

Limitations and safety considerations...

## Reference

Additional reference material...
```

### 6.3 Implementation

```python
# vel/skills/loader.py

from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
import yaml
import re


@dataclass
class Skill:
    """A loaded skill with metadata and content"""
    name: str
    description: str
    content: str
    path: Path
    
    version: str = "1.0.0"
    author: Optional[str] = None
    tools_required: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    
    def get_full_context(self) -> str:
        """
        Load skill content plus any supporting files in the skill directory.
        """
        context_parts = [f"# Skill: {self.name}\n\n{self.content}"]
        
        # Load supporting files (schema.md, examples/, etc.)
        skill_dir = self.path.parent
        for file_path in skill_dir.rglob("*.md"):
            if file_path.name != "SKILL.md":
                relative = file_path.relative_to(skill_dir)
                file_content = file_path.read_text()
                context_parts.append(f"\n## {relative}\n\n{file_content}")
        
        return "\n".join(context_parts)
    
    def matches_query(self, query: str) -> float:
        """
        Score how well this skill matches a query.
        Returns 0.0-1.0 relevance score.
        """
        query_lower = query.lower()
        score = 0.0
        
        # Name match (highest weight)
        if self.name.lower() in query_lower:
            score += 0.5
        
        # Tag matches
        for tag in self.tags:
            if tag.lower() in query_lower:
                score += 0.2
        
        # Description keyword match
        desc_words = set(self.description.lower().split())
        query_words = set(query_lower.split())
        overlap = len(desc_words & query_words)
        if overlap > 0:
            score += min(0.3, overlap * 0.1)
        
        return min(1.0, score)


def parse_skill_file(path: Path) -> Skill:
    """Parse a SKILL.md file into a Skill object"""
    content = path.read_text()
    
    # Parse YAML frontmatter
    frontmatter = {}
    body = content
    
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                frontmatter = yaml.safe_load(parts[1])
            except yaml.YAMLError:
                pass
            body = parts[2].strip()
    
    return Skill(
        name=frontmatter.get("name", path.parent.name),
        description=frontmatter.get("description", ""),
        content=body,
        path=path,
        version=frontmatter.get("version", "1.0.0"),
        author=frontmatter.get("author"),
        tools_required=frontmatter.get("tools_required", []),
        tags=frontmatter.get("tags", []),
    )


class SkillRegistry:
    """
    Registry of available skills.
    
    Loads skills from multiple directories:
    - Built-in skills (vel/skills/builtin/)
    - User skills (./skills/ or custom path)
    """
    
    def __init__(
        self,
        skill_dirs: Optional[list[str]] = None,
        include_builtin: bool = True,
    ):
        self.skills: dict[str, Skill] = {}
        
        # Load built-in skills
        if include_builtin:
            builtin_dir = Path(__file__).parent / "builtin"
            if builtin_dir.exists():
                self._load_from_directory(builtin_dir)
        
        # Load user skills
        for skill_dir in (skill_dirs or []):
            path = Path(skill_dir)
            if path.exists():
                self._load_from_directory(path)
    
    def _load_from_directory(self, directory: Path) -> None:
        """Load all skills from a directory"""
        for skill_path in directory.rglob("SKILL.md"):
            try:
                skill = parse_skill_file(skill_path)
                self.skills[skill.name] = skill
            except Exception as e:
                print(f"Warning: Failed to load skill from {skill_path}: {e}")
    
    def get(self, name: str) -> Optional[Skill]:
        """Get skill by name"""
        return self.skills.get(name)
    
    def list_skills(self) -> list[dict]:
        """List all available skills"""
        return [
            {
                "name": skill.name,
                "description": skill.description,
                "tags": skill.tags,
            }
            for skill in self.skills.values()
        ]
    
    def find_skill(self, query: str, threshold: float = 0.2) -> Optional[Skill]:
        """
        Find the best matching skill for a query.
        
        Args:
            query: User query or task description
            threshold: Minimum score to consider a match
        
        Returns:
            Best matching skill, or None if no match above threshold
        """
        best_skill = None
        best_score = threshold
        
        for skill in self.skills.values():
            score = skill.matches_query(query)
            if score > best_score:
                best_score = score
                best_skill = skill
        
        return best_skill
    
    def find_skills_by_tag(self, tag: str) -> list[Skill]:
        """Find all skills with a given tag"""
        return [
            skill for skill in self.skills.values()
            if tag.lower() in [t.lower() for t in skill.tags]
        ]


# vel/middleware/skills.py

from vel import ToolSpec
from vel.skills.loader import SkillRegistry, Skill
from typing import Optional


class SkillsMiddleware:
    """
    Middleware that provides skill loading capabilities.
    
    Adds tools for listing and loading skills.
    """
    
    def __init__(
        self,
        skill_dirs: Optional[list[str]] = None,
        include_builtin: bool = True,
        auto_load: bool = True,
    ):
        self.registry = SkillRegistry(
            skill_dirs=skill_dirs,
            include_builtin=include_builtin,
        )
        self.auto_load = auto_load
        self._loaded_skill: Optional[Skill] = None
    
    def get_tools(self) -> list[ToolSpec]:
        """Return skill tools"""
        return [
            ToolSpec.from_function(
                self._list_skills,
                name="list_skills",
                description="List all available skills with descriptions",
            ),
            ToolSpec.from_function(
                self._load_skill,
                name="load_skill",
                description="""
                Load a skill's full instructions and context.
                
                Skills provide detailed guidance for specific domains like
                data analysis, research, or decision workflows.
                
                Always load the relevant skill before starting specialized work.
                """,
            ),
        ]
    
    def _list_skills(self) -> list[dict]:
        """List all available skills"""
        return self.registry.list_skills()
    
    def _load_skill(self, skill_name: str) -> str:
        """Load a skill's full context"""
        skill = self.registry.get(skill_name)
        
        if not skill:
            available = [s["name"] for s in self.registry.list_skills()]
            return f"Skill '{skill_name}' not found. Available skills: {available}"
        
        self._loaded_skill = skill
        return skill.get_full_context()
    
    def get_system_prompt_segment(self) -> str:
        """Return system prompt segment for skills"""
        skill_list = "\n".join([
            f"- **{s['name']}**: {s['description']}"
            for s in self.registry.list_skills()
        ])
        
        return f"""
## Skills

You have access to specialized skills that provide detailed guidance for specific domains.

**Available Skills:**
{skill_list}

**Using Skills:**
1. Use `list_skills()` to see available skills
2. Use `load_skill(name)` to load detailed instructions
3. Follow the skill's methodology for best results

**When to load a skill:**
- Before starting data analysis → load "data-query"
- Before making decisions → load "decision-workflow"
- Before research tasks → load "research"
- Before creating reports → load "reporting"

Skills contain best practices, examples, and constraints. Always load the relevant skill before specialized work.
"""
    
    def auto_detect_skill(self, query: str) -> Optional[str]:
        """
        Automatically detect which skill to load based on query.
        Returns skill content if found, None otherwise.
        """
        if not self.auto_load:
            return None
        
        skill = self.registry.find_skill(query)
        if skill:
            self._loaded_skill = skill
            return skill.get_full_context()
        
        return None
```

### 6.4 Acceptance Criteria

- [ ] SKILL.md files parse correctly with YAML frontmatter
- [ ] Skills load from built-in and user directories
- [ ] `list_skills()` returns all available skills
- [ ] `load_skill(name)` returns full skill context
- [ ] Supporting files (schema.md, etc.) are included
- [ ] Skill matching works for queries
- [ ] Tag-based skill filtering works
- [ ] Auto-detection suggests skills based on query

---

## 7. Feature 5: Database Backend

### 7.1 Overview

Provides SQL execution capabilities for data query skills. Supports:
- Read-only queries (safety default)
- Multiple database connections
- Query timeout and row limits
- Schema introspection

### 7.2 Implementation

```python
# vel/backends/database.py

from dataclasses import dataclass
from typing import Optional, Any
import asyncio


@dataclass
class QueryResult:
    """Result of a SQL query"""
    columns: list[str]
    rows: list[dict]
    row_count: int
    truncated: bool = False
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "columns": self.columns,
            "rows": self.rows,
            "row_count": self.row_count,
            "truncated": self.truncated,
            "error": self.error,
            "success": self.error is None,
        }
    
    def to_markdown_table(self, max_rows: int = 20) -> str:
        """Render as markdown table"""
        if self.error:
            return f"Error: {self.error}"
        
        if not self.rows:
            return "No results"
        
        # Header
        lines = [
            "| " + " | ".join(self.columns) + " |",
            "| " + " | ".join(["---"] * len(self.columns)) + " |",
        ]
        
        # Rows
        for row in self.rows[:max_rows]:
            values = [str(row.get(col, ""))[:50] for col in self.columns]
            lines.append("| " + " | ".join(values) + " |")
        
        if len(self.rows) > max_rows:
            lines.append(f"\n*Showing {max_rows} of {len(self.rows)} rows*")
        
        return "\n".join(lines)


class DatabaseBackend:
    """
    SQL database backend for data query skills.
    
    Supports multiple database connections with safety controls.
    """
    
    def __init__(
        self,
        connections: dict[str, str],  # name -> connection string
        read_only: bool = True,
        query_timeout: int = 30,
        row_limit: int = 10000,
    ):
        """
        Args:
            connections: Map of database name to connection string
            read_only: If True, block write operations
            query_timeout: Maximum query execution time
            row_limit: Maximum rows to return
        """
        self.connections = connections
        self.read_only = read_only
        self.query_timeout = query_timeout
        self.row_limit = row_limit
        self._pools: dict[str, Any] = {}
    
    async def _get_pool(self, database: str):
        """Get or create connection pool"""
        if database not in self._pools:
            if database not in self.connections:
                raise ValueError(f"Unknown database: {database}")
            
            import asyncpg
            self._pools[database] = await asyncpg.create_pool(
                self.connections[database],
                min_size=1,
                max_size=5,
            )
        
        return self._pools[database]
    
    def _check_query_safety(self, query: str) -> Optional[str]:
        """
        Check if query is safe to execute.
        Returns error message if unsafe, None if safe.
        """
        if not self.read_only:
            return None
        
        # Normalize query
        query_upper = query.upper().strip()
        
        # Block write operations
        write_keywords = [
            "INSERT", "UPDATE", "DELETE", "DROP", "ALTER",
            "TRUNCATE", "CREATE", "GRANT", "REVOKE", "EXEC",
        ]
        
        for keyword in write_keywords:
            if query_upper.startswith(keyword) or f" {keyword} " in query_upper:
                return f"Write operation '{keyword}' not allowed in read-only mode"
        
        return None
    
    async def execute(
        self,
        query: str,
        database: str = "default",
        params: Optional[dict] = None,
    ) -> QueryResult:
        """
        Execute a SQL query.
        
        Args:
            query: SQL query to execute
            database: Database connection name
            params: Optional query parameters
        
        Returns:
            QueryResult with columns, rows, and metadata
        """
        # Safety check
        error = self._check_query_safety(query)
        if error:
            return QueryResult(
                columns=[],
                rows=[],
                row_count=0,
                error=error,
            )
        
        # Add LIMIT if not present
        if "LIMIT" not in query.upper():
            query = f"{query.rstrip(';')} LIMIT {self.row_limit}"
        
        try:
            pool = await self._get_pool(database)
            
            async with pool.acquire() as conn:
                # Execute with timeout
                rows = await asyncio.wait_for(
                    conn.fetch(query),
                    timeout=self.query_timeout,
                )
                
                if not rows:
                    return QueryResult(
                        columns=[],
                        rows=[],
                        row_count=0,
                    )
                
                columns = list(rows[0].keys())
                row_dicts = [dict(row) for row in rows]
                
                return QueryResult(
                    columns=columns,
                    rows=row_dicts,
                    row_count=len(row_dicts),
                    truncated=len(row_dicts) >= self.row_limit,
                )
        
        except asyncio.TimeoutError:
            return QueryResult(
                columns=[],
                rows=[],
                row_count=0,
                error=f"Query timed out after {self.query_timeout}s",
            )
        except Exception as e:
            return QueryResult(
                columns=[],
                rows=[],
                row_count=0,
                error=str(e),
            )
    
    async def get_schema(self, database: str = "default") -> QueryResult:
        """Get database schema information"""
        query = """
            SELECT 
                table_schema,
                table_name,
                column_name,
                data_type,
                is_nullable
            FROM information_schema.columns
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
            ORDER BY table_schema, table_name, ordinal_position
        """
        return await self.execute(query, database)
    
    async def get_tables(self, database: str = "default") -> QueryResult:
        """List all tables in database"""
        query = """
            SELECT 
                table_schema,
                table_name,
                table_type
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
            ORDER BY table_schema, table_name
        """
        return await self.execute(query, database)
    
    async def describe_table(
        self,
        table: str,
        database: str = "default",
    ) -> QueryResult:
        """Get column information for a table"""
        query = f"""
            SELECT 
                column_name,
                data_type,
                is_nullable,
                column_default
            FROM information_schema.columns
            WHERE table_name = '{table}'
            ORDER BY ordinal_position
        """
        return await self.execute(query, database)
    
    async def close(self):
        """Close all connection pools"""
        for pool in self._pools.values():
            await pool.close()
        self._pools.clear()


# vel/tools/database.py

from vel import ToolSpec
from vel.backends.database import DatabaseBackend
from typing import Optional


def create_database_tools(backend: DatabaseBackend) -> list[ToolSpec]:
    """Create database tools"""
    
    async def execute_sql(
        query: str,
        database: str = "default",
    ) -> dict:
        """
        Execute a SQL query against the database.
        
        Args:
            query: SQL query to execute (SELECT only in read-only mode)
            database: Database connection name (default: "default")
        
        Returns:
            Dict with columns, rows, row_count, success, error
        """
        result = await backend.execute(query, database)
        return result.to_dict()
    
    async def get_schema(database: str = "default") -> dict:
        """
        Get the database schema (tables and columns).
        
        Args:
            database: Database connection name
        
        Returns:
            Schema information as table
        """
        result = await backend.get_schema(database)
        return result.to_dict()
    
    async def list_tables(database: str = "default") -> dict:
        """
        List all tables in the database.
        
        Args:
            database: Database connection name
        
        Returns:
            List of tables with schema and type
        """
        result = await backend.get_tables(database)
        return result.to_dict()
    
    async def describe_table(table: str, database: str = "default") -> dict:
        """
        Get detailed information about a table's columns.
        
        Args:
            table: Table name
            database: Database connection name
        
        Returns:
            Column information (name, type, nullable, default)
        """
        result = await backend.describe_table(table, database)
        return result.to_dict()
    
    return [
        ToolSpec.from_function(
            execute_sql,
            name="execute_sql",
            description="""
            Execute a SQL query against the database.
            
            In read-only mode (default), only SELECT queries are allowed.
            Results are automatically limited to prevent memory issues.
            
            Use for: data retrieval, aggregations, joins, analysis.
            """,
        ),
        ToolSpec.from_function(
            get_schema,
            name="get_schema",
            description="Get the full database schema (all tables and columns)",
        ),
        ToolSpec.from_function(
            list_tables,
            name="list_tables",
            description="List all tables in the database",
        ),
        ToolSpec.from_function(
            describe_table,
            name="describe_table",
            description="Get detailed column information for a specific table",
        ),
    ]
```

### 7.3 Acceptance Criteria

- [ ] SQL queries execute with timeout
- [ ] Read-only mode blocks write operations
- [ ] Row limit prevents memory issues
- [ ] Multiple database connections supported
- [ ] Schema introspection works
- [ ] Connection pooling works correctly
- [ ] Errors are handled gracefully
- [ ] Results convert to markdown tables

---

## 8. Feature 6: Subagent System

### 8.1 Overview

Enables spawning isolated subagents for:
- Context isolation (keep main agent context clean)
- Parallel research (multiple subagents working simultaneously)
- Specialized tasks (subagents with different tools/skills)

Built on Mesh's subgraph composition.

### 8.2 Implementation

```python
# vel/middleware/subagents.py

from dataclasses import dataclass, field
from typing import Optional, Any, Callable
from vel import Agent, ToolSpec
from mesh import StateGraph, Subgraph, SubgraphConfig, Send


@dataclass
class SubagentConfig:
    """Configuration for a subagent"""
    name: str
    description: str
    system_prompt: Optional[str] = None
    tools: list[ToolSpec] = field(default_factory=list)
    model: Optional[dict] = None  # Override main agent model
    skills: list[str] = field(default_factory=list)  # Skills to auto-load
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "skills": self.skills,
        }


class SubagentMiddleware:
    """
    Middleware for spawning and managing subagents.
    
    Subagents run in isolated contexts via Mesh subgraphs.
    """
    
    def __init__(
        self,
        default_model: dict,
        default_tools: list[ToolSpec] = None,
        subagents: list[SubagentConfig] = None,
        max_concurrent: int = 5,
    ):
        self.default_model = default_model
        self.default_tools = default_tools or []
        self.subagents = {s.name: s for s in (subagents or [])}
        self.max_concurrent = max_concurrent
        
        # Always include general-purpose subagent
        if "general" not in self.subagents:
            self.subagents["general"] = SubagentConfig(
                name="general",
                description="General-purpose subagent with same capabilities as main agent",
            )
    
    def get_tools(self) -> list[ToolSpec]:
        """Return subagent tools"""
        return [
            ToolSpec.from_function(
                self._spawn_subagent,
                name="task",
                description=self._build_task_description(),
            ),
            ToolSpec.from_function(
                self._spawn_parallel_subagents,
                name="parallel_tasks",
                description="""
                Spawn multiple subagents to work in parallel.
                
                Use when you need to:
                - Research multiple topics simultaneously
                - Process multiple items concurrently
                - Get diverse perspectives on a question
                
                All subagents run concurrently and results are collected.
                """,
            ),
        ]
    
    def _build_task_description(self) -> str:
        """Build description listing available subagents"""
        subagent_list = "\n".join([
            f"- {name}: {config.description}"
            for name, config in self.subagents.items()
        ])
        
        return f"""
Delegate a task to a subagent for isolated execution.

Available subagents:
{subagent_list}

Use subagents for:
- Deep dives that would clutter main context
- Specialized tasks requiring different tools
- Isolating exploratory work

The subagent works independently and returns its findings.
"""
    
    async def _spawn_subagent(
        self,
        subagent: str,
        task: str,
        context: Optional[str] = None,
    ) -> dict:
        """
        Spawn a subagent to handle a task.
        
        Args:
            subagent: Name of subagent to use (or "general")
            task: Task description for the subagent
            context: Optional context to provide
        
        Returns:
            Subagent's response and findings
        """
        if subagent not in self.subagents:
            available = list(self.subagents.keys())
            return {"error": f"Unknown subagent: {subagent}. Available: {available}"}
        
        config = self.subagents[subagent]
        
        # Build subagent
        agent = Agent(
            id=f"subagent-{config.name}",
            model=config.model or self.default_model,
            tools=config.tools or self.default_tools,
            system_prompt=config.system_prompt,
        )
        
        # Build message
        message = task
        if context:
            message = f"Context:\n{context}\n\nTask: {task}"
        
        # Execute
        result = await agent.run({"message": message})
        
        return {
            "subagent": subagent,
            "task": task,
            "result": result,
        }
    
    async def _spawn_parallel_subagents(
        self,
        tasks: list[dict],
    ) -> dict:
        """
        Spawn multiple subagents in parallel.
        
        Args:
            tasks: List of {"subagent": str, "task": str, "context": str?}
        
        Returns:
            Results from all subagents
        """
        import asyncio
        
        # Limit concurrency
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def run_task(task_config: dict, index: int):
            async with semaphore:
                result = await self._spawn_subagent(
                    subagent=task_config.get("subagent", "general"),
                    task=task_config["task"],
                    context=task_config.get("context"),
                )
                return index, result
        
        # Run all tasks
        coroutines = [
            run_task(task, i) for i, task in enumerate(tasks)
        ]
        results = await asyncio.gather(*coroutines, return_exceptions=True)
        
        # Collect results in order
        ordered_results = [None] * len(tasks)
        errors = []
        
        for result in results:
            if isinstance(result, Exception):
                errors.append(str(result))
            else:
                index, value = result
                ordered_results[index] = value
        
        return {
            "results": ordered_results,
            "errors": errors if errors else None,
            "task_count": len(tasks),
            "success_count": len([r for r in ordered_results if r]),
        }
    
    def get_system_prompt_segment(self) -> str:
        """Return system prompt segment for subagents"""
        subagent_list = "\n".join([
            f"- **{name}**: {config.description}"
            for name, config in self.subagents.items()
        ])
        
        return f"""
## Subagents

You can delegate tasks to subagents using the `task` tool:

{subagent_list}

**When to use subagents:**
- Deep research that would fill up context
- Parallel investigation of multiple topics
- Specialized tasks requiring different approaches
- Isolating experimental or exploratory work

**Parallel execution:**
Use `parallel_tasks` to run multiple subagents simultaneously:
```
parallel_tasks([
    {{"subagent": "general", "task": "Research topic A"}},
    {{"subagent": "general", "task": "Research topic B"}},
    {{"subagent": "general", "task": "Research topic C"}},
])
```

Subagent results are returned for you to synthesize.
"""
    
    def create_mesh_subgraph(self, config: SubagentConfig) -> Subgraph:
        """Create a Mesh subgraph for a subagent configuration"""
        from mesh import StateGraph
        
        graph = StateGraph()
        
        # Simple agent node
        agent = Agent(
            id=f"subagent-{config.name}",
            model=config.model or self.default_model,
            tools=config.tools or self.default_tools,
            system_prompt=config.system_prompt,
        )
        
        graph.add_node("agent", agent, node_type="agent")
        graph.add_edge("START", "agent")
        graph.add_edge("agent", "END")
        
        return Subgraph(
            graph.compile(),
            config=SubgraphConfig(
                isolated=True,
                input_mapping={"task": "message"},
                output_mapping={"response": "result"},
            ),
            name=config.name,
        )
```

### 8.3 Acceptance Criteria

- [ ] `task` tool spawns single subagent
- [ ] `parallel_tasks` spawns multiple subagents concurrently
- [ ] Subagent context is isolated from main agent
- [ ] Custom subagent configurations work
- [ ] Default "general" subagent always available
- [ ] Concurrency limit is respected
- [ ] Results are collected correctly
- [ ] Errors in one subagent don't crash others
- [ ] Integration with Mesh subgraphs works

---

## 9. Feature 7: Deep Agent Factory

### 9.1 Overview

The `create_deep_agent()` factory assembles all components into a complete deep agent using Mesh for orchestration.

### 9.2 Implementation

```python
# vel/agent.py

from dataclasses import dataclass, field
from typing import Optional, Any, AsyncIterator
from pathlib import Path

from vel import Agent, ToolSpec
from mesh import (
    StateGraph,
    Executor,
    ExecutionContext,
    Subgraph,
    StreamMode,
)
from mesh.backends import SQLiteBackend, MemoryBackend

from vel.middleware.planning import PlanningMiddleware
from vel.middleware.filesystem import FilesystemMiddleware, StateFilesystemBackend
from vel.middleware.skills import SkillsMiddleware
from vel.middleware.subagents import SubagentMiddleware, SubagentConfig
from vel.middleware.hitl import HumanInTheLoopMiddleware
from vel.backends.sandbox import SandboxFilesystemBackend, create_sandbox
from vel.backends.database import DatabaseBackend
from vel.tools.sandbox import create_execution_tools
from vel.tools.database import create_database_tools
from vel.prompts.system import build_system_prompt


@dataclass
class DeepAgentConfig:
    """Configuration for create_deep_agent()"""
    
    # Model configuration
    model: dict = field(default_factory=lambda: {
        "provider": "anthropic",
        "model": "claude-sonnet-4-5-20250929",
    })
    
    # Tools
    tools: list[ToolSpec] = field(default_factory=list)
    
    # Skills
    skill_dirs: list[str] = field(default_factory=lambda: ["./skills"])
    include_builtin_skills: bool = True
    auto_load_skills: bool = True
    
    # Sandbox
    sandbox_enabled: bool = True
    sandbox_working_dir: str = "./workspace"
    sandbox_network: bool = False
    sandbox_timeout: int = 30
    
    # Database
    databases: dict[str, str] = field(default_factory=dict)
    database_read_only: bool = True
    
    # Subagents
    subagents: list[SubagentConfig] = field(default_factory=list)
    max_concurrent_subagents: int = 5
    
    # Human-in-the-loop
    interrupt_on: dict[str, bool] = field(default_factory=dict)
    
    # Persistence
    persistence_path: Optional[str] = None  # SQLite path, None for memory
    
    # Execution
    max_steps: int = 50
    checkpoint_interval: int = 5


class DeepAgent:
    """
    A deep agent with planning, filesystem, skills, and subagent capabilities.
    
    Built on Mesh for graph orchestration and Vel for LLM interaction.
    """
    
    def __init__(self, config: DeepAgentConfig):
        self.config = config
        self._setup_components()
        self._build_graph()
    
    def _setup_components(self):
        """Initialize all middleware and backends"""
        
        # Planning
        self.planning = PlanningMiddleware()
        
        # Filesystem
        if self.config.sandbox_enabled:
            self.filesystem_backend = SandboxFilesystemBackend(
                working_dir=self.config.sandbox_working_dir,
                network=self.config.sandbox_network,
                timeout=self.config.sandbox_timeout,
            )
        else:
            self.filesystem_backend = StateFilesystemBackend()
        
        self.filesystem = FilesystemMiddleware(backend=self.filesystem_backend)
        
        # Skills
        self.skills = SkillsMiddleware(
            skill_dirs=self.config.skill_dirs,
            include_builtin=self.config.include_builtin_skills,
            auto_load=self.config.auto_load_skills,
        )
        
        # Database
        self.database = None
        if self.config.databases:
            self.database = DatabaseBackend(
                connections=self.config.databases,
                read_only=self.config.database_read_only,
            )
        
        # Subagents
        self.subagents = SubagentMiddleware(
            default_model=self.config.model,
            default_tools=self._collect_tools(),
            subagents=self.config.subagents,
            max_concurrent=self.config.max_concurrent_subagents,
        )
        
        # Human-in-the-loop
        self.hitl = None
        if self.config.interrupt_on:
            self.hitl = HumanInTheLoopMiddleware(
                interrupt_on=self.config.interrupt_on,
            )
        
        # Persistence backend
        if self.config.persistence_path:
            self.backend = SQLiteBackend(self.config.persistence_path)
        else:
            self.backend = MemoryBackend()
    
    def _collect_tools(self) -> list[ToolSpec]:
        """Collect all tools from middleware and config"""
        tools = list(self.config.tools)
        
        # Planning tools
        tools.extend(self.planning.get_tools())
        
        # Filesystem tools
        tools.extend(self.filesystem.get_tools())
        
        # Skills tools
        tools.extend(self.skills.get_tools())
        
        # Execution tools (if sandbox enabled)
        if self.config.sandbox_enabled:
            tools.extend(create_execution_tools(self.filesystem_backend))
        
        # Database tools
        if self.database:
            tools.extend(create_database_tools(self.database))
        
        # Subagent tools
        tools.extend(self.subagents.get_tools())
        
        return tools
    
    def _build_system_prompt(self) -> str:
        """Build complete system prompt from all middleware"""
        segments = [
            self.planning.get_system_prompt_segment(),
            self.filesystem.get_system_prompt_segment(),
            self.skills.get_system_prompt_segment(),
            self.subagents.get_system_prompt_segment(),
        ]
        
        return build_system_prompt(segments)
    
    def _build_graph(self):
        """Build the Mesh execution graph"""
        from mesh import StateGraph
        from mesh.nodes import Condition
        
        graph = StateGraph()
        
        # Create main agent
        self.agent = Agent(
            id="vel-deep-agent",
            model=self.config.model,
            tools=self._collect_tools(),
            system_prompt=self._build_system_prompt(),
        )
        
        # === Nodes ===
        
        # Planning node (updates todos)
        graph.add_node("planning", self._planning_node, node_type="tool")
        
        # Skill detection node
        graph.add_node("skill_loader", self._skill_loader_node, node_type="tool")
        
        # Main agent node
        graph.add_node("agent", self.agent, node_type="agent")
        
        # Router node (decides next action)
        graph.add_node("router", [
            Condition("continue", self._should_continue, "agent"),
            Condition("done", self._is_complete, "END"),
        ], node_type="condition")
        
        # === Edges ===
        
        graph.add_edge("START", "planning")
        graph.add_edge("planning", "skill_loader")
        graph.add_edge("skill_loader", "agent")
        graph.add_edge("agent", "router")
        
        # === Interrupts ===
        
        if self.hitl:
            for tool_name in self.config.interrupt_on:
                graph.set_interrupt_before(
                    "agent",
                    condition=lambda s, t=tool_name: s.get("_pending_tool") == t,
                )
        
        # Compile
        self.graph = graph.compile()
        self.executor = Executor(
            self.graph,
            self.backend,
            max_concurrency=self.config.max_concurrent_subagents,
        )
    
    def _planning_node(self, state: dict) -> dict:
        """Initialize planning for new task"""
        # Planning happens via tool calls during agent execution
        return {"_planning_initialized": True}
    
    def _skill_loader_node(self, state: dict) -> dict:
        """Auto-detect and load relevant skill"""
        query = state.get("input", "")
        skill_content = self.skills.auto_detect_skill(query)
        
        if skill_content:
            return {"_loaded_skill": skill_content}
        return {}
    
    def _should_continue(self, state: dict) -> bool:
        """Check if agent should continue (has pending actions)"""
        return state.get("_has_tool_calls", False) and not state.get("_is_complete", False)
    
    def _is_complete(self, state: dict) -> bool:
        """Check if agent has finished"""
        return state.get("_is_complete", False) or state.get("_step_count", 0) >= self.config.max_steps
    
    async def run(
        self,
        message: str,
        session_id: Optional[str] = None,
    ) -> str:
        """
        Run agent to completion.
        
        Args:
            message: User message/task
            session_id: Optional session ID for persistence
        
        Returns:
            Final agent response
        """
        import uuid
        
        context = ExecutionContext(
            graph_id="vel-deep-agent",
            session_id=session_id or str(uuid.uuid4()),
            chat_history=[],
            variables={"input": message},
            state={},
        )
        
        final_response = ""
        
        async for event in self.executor.execute(
            message,
            context,
            checkpoint_interval=self.config.checkpoint_interval,
        ):
            if event.type == "token" and event.node_id == "agent":
                final_response += event.content
        
        return final_response
    
    async def run_stream(
        self,
        message: str,
        session_id: Optional[str] = None,
        mode: StreamMode = StreamMode.EVENTS,
    ) -> AsyncIterator[Any]:
        """
        Run agent with streaming.
        
        Args:
            message: User message/task
            session_id: Optional session ID
            mode: Streaming mode (events, values, updates, etc.)
        
        Yields:
            Stream events based on mode
        """
        import uuid
        
        context = ExecutionContext(
            graph_id="vel-deep-agent",
            session_id=session_id or str(uuid.uuid4()),
            chat_history=[],
            variables={"input": message},
            state={},
        )
        
        async for event in self.executor.stream(
            message,
            context,
            mode=mode,
        ):
            yield event
    
    async def resume(
        self,
        session_id: str,
        modified_state: Optional[dict] = None,
    ) -> AsyncIterator[Any]:
        """Resume from interrupt"""
        context = await self.executor.restore_latest(session_id)
        
        async for event in self.executor.resume(context, modified_state=modified_state):
            yield event
    
    async def reject(
        self,
        session_id: str,
        reason: str = "",
    ) -> AsyncIterator[Any]:
        """Reject interrupt and end execution"""
        context = await self.executor.restore_latest(session_id)
        
        async for event in self.executor.reject(context, reason=reason):
            yield event


def create_deep_agent(
    model: Optional[dict] = None,
    tools: Optional[list[ToolSpec]] = None,
    skill_dirs: Optional[list[str]] = None,
    sandbox: bool = True,
    sandbox_working_dir: str = "./workspace",
    databases: Optional[dict[str, str]] = None,
    subagents: Optional[list[SubagentConfig]] = None,
    interrupt_on: Optional[dict[str, bool]] = None,
    persistence_path: Optional[str] = None,
    **kwargs,
) -> DeepAgent:
    """
    Create a deep agent with full capabilities.
    
    Args:
        model: LLM configuration (default: Claude Sonnet)
        tools: Additional custom tools
        skill_dirs: Directories to load skills from
        sandbox: Enable sandboxed execution
        sandbox_working_dir: Working directory for sandbox
        databases: Database connections {"name": "connection_string"}
        subagents: Custom subagent configurations
        interrupt_on: Tools requiring human approval {"tool_name": True}
        persistence_path: SQLite path for persistence (None for memory)
        **kwargs: Additional DeepAgentConfig options
    
    Returns:
        Configured DeepAgent instance
    
    Example:
        agent = create_deep_agent(
            model={"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
            skill_dirs=["./skills"],
            sandbox=True,
            databases={"analytics": "postgresql://..."},
            interrupt_on={"execute": True},
        )
        
        result = await agent.run("Analyze Q4 sales data")
    """
    config = DeepAgentConfig(
        model=model or {"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
        tools=tools or [],
        skill_dirs=skill_dirs or ["./skills"],
        sandbox_enabled=sandbox,
        sandbox_working_dir=sandbox_working_dir,
        databases=databases or {},
        subagents=subagents or [],
        interrupt_on=interrupt_on or {},
        persistence_path=persistence_path,
        **kwargs,
    )
    
    return DeepAgent(config)
```

### 9.3 Public API

```python
# vel/__init__.py

from vel.agent import (
    DeepAgent,
    DeepAgentConfig,
    create_deep_agent,
)
from vel.middleware.planning import PlanningMiddleware, TodoList, TodoItem
from vel.middleware.filesystem import FilesystemMiddleware, StateFilesystemBackend
from vel.middleware.skills import SkillsMiddleware
from vel.middleware.subagents import SubagentMiddleware, SubagentConfig
from vel.middleware.hitl import HumanInTheLoopMiddleware
from vel.backends.sandbox import (
    create_sandbox,
    BaseSandbox,
    BubblewrapSandbox,
    SeatbeltSandbox,
    SandboxFilesystemBackend,
)
from vel.backends.database import DatabaseBackend, QueryResult
from vel.skills.loader import Skill, SkillRegistry

__all__ = [
    # Main API
    "create_deep_agent",
    "DeepAgent",
    "DeepAgentConfig",
    
    # Middleware
    "PlanningMiddleware",
    "FilesystemMiddleware",
    "SkillsMiddleware",
    "SubagentMiddleware",
    "SubagentConfig",
    "HumanInTheLoopMiddleware",
    
    # Backends
    "create_sandbox",
    "SandboxFilesystemBackend",
    "StateFilesystemBackend",
    "DatabaseBackend",
    
    # Skills
    "Skill",
    "SkillRegistry",
    
    # Data structures
    "TodoList",
    "TodoItem",
    "QueryResult",
]
```

### 9.4 Acceptance Criteria

- [ ] `create_deep_agent()` returns working agent
- [ ] All middleware integrates correctly
- [ ] Tools from all middleware are available
- [ ] System prompt includes all middleware segments
- [ ] Mesh graph executes correctly
- [ ] Streaming works with all modes
- [ ] Interrupts pause and resume correctly
- [ ] Persistence saves and restores state
- [ ] Checkpointing works during execution

---

## 10. Built-in Skills

### 10.1 Data Query Skill

```markdown
# vel/skills/builtin/data-query/SKILL.md

---
name: data-query
description: Query databases, analyze data, and create visualizations
version: 1.0.0
tools_required:
  - execute_sql
  - execute_python
  - write_file
tags:
  - data
  - sql
  - analysis
  - visualization
---

# Data Query Skill

## When to Use

Use this skill when the user asks to:
- Query data from databases
- Analyze datasets
- Generate charts or visualizations
- Create data exports
- Answer questions requiring data lookup

## Approach

1. **Understand the request**
   - What data is needed?
   - What format should results be in?
   - Are there any filters or conditions?

2. **Explore the schema**
   - Use `list_tables()` to see available tables
   - Use `describe_table(name)` for column details
   - Understand relationships between tables

3. **Write and test queries incrementally**
   - Start with simple SELECT to verify data
   - Add filters, joins, aggregations step by step
   - Validate intermediate results

4. **Process and visualize**
   - Use Python for complex transformations
   - Create charts with matplotlib/seaborn
   - Format results as tables or reports

5. **Save and present results**
   - Write data to CSV/JSON files
   - Save visualizations as PNG
   - Create markdown reports

## Query Patterns

### Basic aggregation
```sql
SELECT 
    category,
    COUNT(*) as count,
    SUM(amount) as total,
    AVG(amount) as average
FROM transactions
WHERE date >= '2024-01-01'
GROUP BY category
ORDER BY total DESC
```

### Time series
```sql
SELECT 
    DATE_TRUNC('month', created_at) as month,
    COUNT(*) as count
FROM events
GROUP BY month
ORDER BY month
```

### Joins
```sql
SELECT 
    u.name,
    COUNT(o.id) as order_count,
    SUM(o.total) as total_spent
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
GROUP BY u.id, u.name
```

## Visualization with Python

```python
import pandas as pd
import matplotlib.pyplot as plt

# Load query results
df = pd.read_csv('/data/results.csv')

# Create visualization
fig, ax = plt.subplots(figsize=(10, 6))
df.plot(kind='bar', x='category', y='total', ax=ax)
ax.set_title('Total by Category')
ax.set_xlabel('Category')
ax.set_ylabel('Total')

# Save
plt.tight_layout()
plt.savefig('/reports/category_chart.png', dpi=150)
print("Chart saved to /reports/category_chart.png")
```

## Constraints

- **Read-only access**: Cannot modify data
- **Row limits**: Queries return max 10,000 rows
- **Timeout**: Queries timeout after 30 seconds
- **No PII**: Some columns may be masked

## Output Format

Always provide:
1. Summary of findings in plain language
2. Key numbers/metrics highlighted
3. Data files saved for reference
4. Visualizations when appropriate
```

### 10.2 Decision Workflow Skill

```markdown
# vel/skills/builtin/decision-workflow/SKILL.md

---
name: decision-workflow
description: Route decisions through approval chains and policy evaluation
version: 1.0.0
tools_required:
  - write_file
  - read_file
tags:
  - decisions
  - approval
  - workflow
  - policy
---

# Decision Workflow Skill

## When to Use

Use this skill when the user needs to:
- Evaluate a request against policies
- Route something for approval
- Make a recommendation with justification
- Document a decision

## Approach

1. **Parse the request**
   - What type of decision is this?
   - Who is requesting?
   - What are the key parameters?

2. **Identify applicable policies**
   - What rules govern this decision?
   - What are the thresholds?
   - Who has authority to approve?

3. **Evaluate against criteria**
   - Does it meet automatic approval criteria?
   - What risk level does it represent?
   - Are there any red flags?

4. **Make recommendation**
   - Approve, deny, or escalate
   - Provide clear rationale
   - Document the decision

5. **Generate decision record**
   - Structured record for audit trail
   - Include all relevant factors
   - Timestamp and reference

## Decision Types

### Expense Approval
| Amount | Approval Level |
|--------|---------------|
| < $500 | Auto-approve |
| $500 - $5,000 | Manager |
| $5,000 - $25,000 | Director |
| > $25,000 | VP + Finance |

### Access Request
| Access Level | Approval |
|-------------|----------|
| Standard | Auto with logging |
| Elevated | Manager + Security review |
| Admin | CISO approval required |

### Vendor Selection
| Contract Value | Process |
|---------------|---------|
| < $10,000 | Single quote |
| $10,000 - $50,000 | 3 quotes |
| > $50,000 | RFP required |

## Decision Record Format

```json
{
  "decision_id": "DEC-2024-001234",
  "type": "expense_approval",
  "timestamp": "2024-01-15T10:30:00Z",
  
  "request": {
    "requester": "John Smith",
    "department": "Engineering",
    "amount": 3500,
    "description": "Cloud infrastructure upgrade",
    "justification": "Required for Q1 scaling"
  },
  
  "evaluation": {
    "policy_applied": "expense_policy_v2",
    "risk_level": "low",
    "approval_level_required": "manager",
    "factors_considered": [
      "Amount within manager threshold",
      "Budget available in department",
      "Aligned with Q1 objectives"
    ]
  },
  
  "decision": {
    "outcome": "approved",
    "approver": "Jane Doe (Manager)",
    "conditions": [],
    "rationale": "Request is within policy and budget"
  }
}
```

## Constraints

- Always document the reasoning
- Never approve outside policy without escalation
- Flag any conflicts of interest
- Maintain audit trail

## Output

Provide:
1. Clear decision (approved/denied/escalate)
2. Rationale in plain language
3. Next steps if any
4. Decision record saved to file
```

### 10.3 Research Skill

```markdown
# vel/skills/builtin/research/SKILL.md

---
name: research
description: Deep research with source synthesis and report generation
version: 1.0.0
tools_required:
  - task
  - parallel_tasks
  - write_file
  - read_file
tags:
  - research
  - analysis
  - synthesis
  - reports
---

# Research Skill

## When to Use

Use this skill when the user asks to:
- Research a topic in depth
- Compare multiple options or approaches
- Gather information from various sources
- Create a research report or summary

## Approach

1. **Define the scope**
   - What specific questions need answering?
   - What's the depth required?
   - What format should output take?

2. **Plan the research**
   - Break into sub-questions
   - Identify what sources to consult
   - Allocate effort appropriately

3. **Gather information**
   - Use parallel subagents for breadth
   - Take notes as you go
   - Track sources

4. **Synthesize findings**
   - Identify patterns and themes
   - Note contradictions
   - Draw conclusions

5. **Create output**
   - Executive summary first
   - Detailed findings
   - Sources and citations

## Research Methodology

### Parallel Research Pattern

```
parallel_tasks([
    {"subagent": "general", "task": "Research aspect A of topic"},
    {"subagent": "general", "task": "Research aspect B of topic"},
    {"subagent": "general", "task": "Research aspect C of topic"},
])
```

Then synthesize results into coherent report.

### Note-Taking Structure

Save notes to files as you research:

```markdown
# Research Notes: [Topic]

## Source 1: [Name]
- Key point 1
- Key point 2
- Relevant quote or data

## Source 2: [Name]
...
```

### Synthesis Framework

1. **Convergence**: Where do sources agree?
2. **Divergence**: Where do they disagree?
3. **Gaps**: What's not covered?
4. **Implications**: What does this mean?

## Output Format

### Executive Summary
- 2-3 paragraph overview
- Key findings highlighted
- Recommendation if applicable

### Detailed Findings
- Organized by theme or question
- Evidence and sources cited
- Balanced presentation

### Appendix
- Full notes
- Source list
- Methodology description

## Constraints

- Always cite sources
- Note confidence levels
- Acknowledge limitations
- Separate fact from interpretation
```

### 10.4 Reporting Skill

```markdown
# vel/skills/builtin/reporting/SKILL.md

---
name: reporting
description: Generate professional reports and documents
version: 1.0.0
tools_required:
  - write_file
  - read_file
  - execute_python
tags:
  - reports
  - documents
  - writing
  - formatting
---

# Reporting Skill

## When to Use

Use this skill when the user needs to:
- Create a formal report
- Generate a document from data/findings
- Format information professionally
- Produce deliverables

## Report Types

### Executive Summary
- 1 page max
- Key metrics highlighted
- Recommendation prominent
- Action items clear

### Analysis Report
- Methodology section
- Data and findings
- Visualizations
- Conclusions

### Status Report
- Progress against goals
- Blockers and risks
- Next steps
- Timeline

### Technical Documentation
- Clear structure
- Code examples if relevant
- Step-by-step where needed

## Approach

1. **Understand the audience**
   - Who will read this?
   - What do they need to know?
   - What decisions will they make?

2. **Gather content**
   - Collect all relevant data
   - Identify key points
   - Prepare visualizations

3. **Structure the document**
   - Choose appropriate format
   - Create outline
   - Determine length

4. **Write and format**
   - Lead with conclusions
   - Support with evidence
   - Use clear language

5. **Review and polish**
   - Check for clarity
   - Verify data accuracy
   - Ensure completeness

## Markdown Report Template

```markdown
# [Report Title]

**Date:** [Date]  
**Author:** [Author]  
**Status:** [Draft/Final]

---

## Executive Summary

[2-3 paragraphs summarizing key findings and recommendations]

## Background

[Context needed to understand the report]

## Methodology

[How information was gathered/analyzed]

## Findings

### Finding 1: [Title]

[Details with supporting data]

### Finding 2: [Title]

[Details with supporting data]

## Recommendations

1. [Recommendation 1]
2. [Recommendation 2]
3. [Recommendation 3]

## Next Steps

| Action | Owner | Due Date |
|--------|-------|----------|
| [Action 1] | [Owner] | [Date] |
| [Action 2] | [Owner] | [Date] |

## Appendix

[Supporting materials, raw data, etc.]
```

## Visualization Guidelines

- Use charts for trends
- Use tables for comparisons
- Use diagrams for processes
- Keep visuals simple and clear

## Constraints

- Match formality to audience
- Be concise but complete
- Cite sources
- Date all documents
```

---

## 11. System Prompt

### 11.1 System Prompt Builder

```python
# vel/prompts/system.py

BASE_SYSTEM_PROMPT = """You are a capable AI assistant with advanced capabilities for handling complex tasks.

You have access to:
- **Planning tools** for breaking down and tracking multi-step work
- **File system tools** for reading, writing, and managing files
- **Execution tools** for running Python code and shell commands (sandboxed)
- **Database tools** for querying data (if configured)
- **Subagent tools** for delegating tasks and parallel research
- **Skills** providing domain expertise for specific task types

## Core Principles

1. **Plan before acting**: Use `write_todos` to break down complex tasks
2. **Work incrementally**: Validate intermediate results before proceeding
3. **Use files effectively**: Save findings, offload large content, create deliverables
4. **Load relevant skills**: Check for applicable skills before specialized work
5. **Delegate appropriately**: Use subagents for deep dives and parallel work

## Working Style

- Be thorough but efficient
- Explain your reasoning when helpful
- Ask clarifying questions when the task is ambiguous
- Provide concrete outputs (files, reports, data) not just descriptions
- Adapt your approach based on what you learn

## Safety

- Execution is sandboxed for safety
- Database access is read-only by default
- Some operations may require approval (you'll be notified)
- Never attempt to access files outside the working directory

"""


def build_system_prompt(middleware_segments: list[str]) -> str:
    """
    Build complete system prompt from base + middleware segments.
    
    Args:
        middleware_segments: List of prompt segments from middleware
    
    Returns:
        Complete system prompt
    """
    parts = [BASE_SYSTEM_PROMPT]
    
    for segment in middleware_segments:
        if segment and segment.strip():
            parts.append(segment.strip())
    
    return "\n\n".join(parts)
```

---

## 12. CLI Interface

### 12.1 Implementation

```python
# vel/cli/main.py

import asyncio
import argparse
import sys
from pathlib import Path

from vel import create_deep_agent


def main():
    parser = argparse.ArgumentParser(
        description="Vel Harness - Deep Agent CLI"
    )
    
    parser.add_argument(
        "task",
        nargs="?",
        help="Task to execute (or interactive mode if not provided)"
    )
    
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-5-20250929",
        help="Model to use (default: claude-sonnet-4-5-20250929)"
    )
    
    parser.add_argument(
        "--provider",
        default="anthropic",
        choices=["anthropic", "openai", "google"],
        help="Model provider (default: anthropic)"
    )
    
    parser.add_argument(
        "--skills",
        default="./skills",
        help="Skills directory (default: ./skills)"
    )
    
    parser.add_argument(
        "--workspace",
        default="./workspace",
        help="Working directory for files (default: ./workspace)"
    )
    
    parser.add_argument(
        "--no-sandbox",
        action="store_true",
        help="Disable sandboxed execution"
    )
    
    parser.add_argument(
        "--database",
        action="append",
        metavar="NAME=URL",
        help="Database connection (can specify multiple)"
    )
    
    parser.add_argument(
        "--approve",
        action="append",
        metavar="TOOL",
        help="Require approval for tool (can specify multiple)"
    )
    
    parser.add_argument(
        "--session",
        help="Session ID for persistence"
    )
    
    parser.add_argument(
        "--persist",
        metavar="PATH",
        help="SQLite path for persistence"
    )
    
    args = parser.parse_args()
    
    # Parse databases
    databases = {}
    if args.database:
        for db in args.database:
            name, url = db.split("=", 1)
            databases[name] = url
    
    # Parse interrupt tools
    interrupt_on = {}
    if args.approve:
        for tool in args.approve:
            interrupt_on[tool] = True
    
    # Create agent
    agent = create_deep_agent(
        model={"provider": args.provider, "model": args.model},
        skill_dirs=[args.skills],
        sandbox=not args.no_sandbox,
        sandbox_working_dir=args.workspace,
        databases=databases,
        interrupt_on=interrupt_on,
        persistence_path=args.persist,
    )
    
    # Run task or interactive mode
    if args.task:
        asyncio.run(run_task(agent, args.task, args.session))
    else:
        asyncio.run(interactive_mode(agent, args.session))


async def run_task(agent, task: str, session_id: str = None):
    """Run a single task"""
    print(f"\n🚀 Running task: {task}\n")
    print("-" * 50)
    
    async for event in agent.run_stream(task, session_id=session_id):
        if event.type == "token":
            print(event.content, end="", flush=True)
        elif event.type == "tool_call":
            print(f"\n🔧 {event.metadata.get('tool_name', 'tool')}()")
        elif event.type == "interrupt":
            print(f"\n\n⚠️  Approval required: {event.metadata}")
            response = input("Approve? [y/n]: ")
            if response.lower() == "y":
                async for e in agent.resume(session_id):
                    if e.type == "token":
                        print(e.content, end="", flush=True)
            else:
                async for e in agent.reject(session_id, reason="User declined"):
                    pass
                print("\n❌ Task cancelled")
                return
    
    print("\n\n✅ Complete")


async def interactive_mode(agent, session_id: str = None):
    """Interactive chat mode"""
    print("\n🤖 Vel Harness - Interactive Mode")
    print("Type 'exit' to quit, 'clear' to reset\n")
    
    import uuid
    session_id = session_id or str(uuid.uuid4())
    
    while True:
        try:
            user_input = input("\n> ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() == "exit":
                print("Goodbye!")
                break
            
            if user_input.lower() == "clear":
                session_id = str(uuid.uuid4())
                print("Session cleared")
                continue
            
            await run_task(agent, user_input, session_id)
            
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")


def cli_entry():
    """Entry point for console script"""
    main()


if __name__ == "__main__":
    main()
```

### 12.2 Package Entry Point

```toml
# pyproject.toml addition

[project.scripts]
vel = "vel.cli.main:cli_entry"
```

---

## 13. Implementation Order

### Phase 1: Foundation (Week 1)

1. **Project scaffolding**
   - Create package structure
   - Set up pyproject.toml
   - Configure tests

2. **Filesystem middleware**
   - StateFilesystemBackend (in-memory)
   - FilesystemMiddleware with all tools
   - Tests

3. **Planning middleware**
   - TodoList and TodoItem classes
   - PlanningMiddleware with write_todos
   - Tests

### Phase 2: Execution (Week 2)

4. **Sandbox backend**
   - BubblewrapSandbox (Linux)
   - SeatbeltSandbox (macOS)
   - SandboxFilesystemBackend
   - Execution tools
   - Tests

5. **Database backend**
   - DatabaseBackend with asyncpg
   - Database tools
   - Tests

### Phase 3: Intelligence (Week 3)

6. **Skills system**
   - Skill and SkillRegistry classes
   - SkillsMiddleware
   - Built-in skills (data-query, decision-workflow, research, reporting)
   - Tests

7. **Subagent system**
   - SubagentMiddleware
   - Parallel execution
   - Mesh integration
   - Tests

### Phase 4: Integration (Week 4)

8. **Deep agent factory**
   - DeepAgentConfig
   - DeepAgent class
   - create_deep_agent() function
   - System prompt builder
   - Integration tests

9. **CLI**
   - CLI implementation
   - Interactive mode
   - Documentation

### Phase 5: Polish (Week 5)

10. **Human-in-the-loop**
    - HumanInTheLoopMiddleware
    - Interrupt handling
    - Tests

11. **Documentation and examples**
    - README
    - API documentation
    - Example scripts

---

## 14. Testing Requirements

### 14.1 Unit Tests

```python
# tests/test_planning.py
class TestPlanningMiddleware:
    def test_write_todos_creates_items(self): ...
    def test_complete_marks_done(self): ...
    def test_todo_list_markdown_render(self): ...
    def test_state_persistence(self): ...

# tests/test_filesystem.py
class TestFilesystemMiddleware:
    def test_write_and_read_file(self): ...
    def test_edit_file_unique_match(self): ...
    def test_edit_file_multiple_matches_error(self): ...
    def test_glob_pattern_matching(self): ...
    def test_grep_regex_search(self): ...

# tests/test_sandbox.py
class TestSandbox:
    def test_execute_command(self): ...
    def test_execute_python(self): ...
    def test_timeout_handling(self): ...
    def test_filesystem_isolation(self): ...
    def test_network_blocked(self): ...

# tests/test_skills.py
class TestSkills:
    def test_skill_parsing(self): ...
    def test_skill_registry_loading(self): ...
    def test_skill_matching(self): ...
    def test_skill_full_context(self): ...

# tests/test_database.py
class TestDatabase:
    async def test_execute_query(self): ...
    async def test_read_only_blocks_writes(self): ...
    async def test_query_timeout(self): ...
    async def test_row_limit(self): ...

# tests/test_subagents.py
class TestSubagents:
    async def test_spawn_subagent(self): ...
    async def test_parallel_subagents(self): ...
    async def test_concurrency_limit(self): ...
```

### 14.2 Integration Tests

```python
# tests/integration/test_deep_agent.py
class TestDeepAgent:
    async def test_simple_task(self): ...
    async def test_planning_workflow(self): ...
    async def test_file_operations(self): ...
    async def test_skill_loading(self): ...
    async def test_subagent_delegation(self): ...
    async def test_interrupt_and_resume(self): ...
    async def test_full_research_workflow(self): ...
```

---

## 15. API Reference

### 15.1 Main Factory

```python
def create_deep_agent(
    model: Optional[dict] = None,
    tools: Optional[list[ToolSpec]] = None,
    skill_dirs: Optional[list[str]] = None,
    sandbox: bool = True,
    sandbox_working_dir: str = "./workspace",
    databases: Optional[dict[str, str]] = None,
    subagents: Optional[list[SubagentConfig]] = None,
    interrupt_on: Optional[dict[str, bool]] = None,
    persistence_path: Optional[str] = None,
    **kwargs,
) -> DeepAgent:
    """Create a deep agent with full capabilities."""
```

### 15.2 DeepAgent Methods

```python
class DeepAgent:
    async def run(
        self,
        message: str,
        session_id: Optional[str] = None,
    ) -> str:
        """Run agent to completion, return final response."""
    
    async def run_stream(
        self,
        message: str,
        session_id: Optional[str] = None,
        mode: StreamMode = StreamMode.EVENTS,
    ) -> AsyncIterator[Any]:
        """Run agent with streaming."""
    
    async def resume(
        self,
        session_id: str,
        modified_state: Optional[dict] = None,
    ) -> AsyncIterator[Any]:
        """Resume from interrupt."""
    
    async def reject(
        self,
        session_id: str,
        reason: str = "",
    ) -> AsyncIterator[Any]:
        """Reject interrupt and end execution."""
```

### 15.3 Tool Functions

```python
# Planning
def write_todos(current_task: str, next_steps: list[str], completed: list[str] = None) -> dict

# Filesystem
def ls(path: str = "/") -> dict
def read_file(path: str, offset: int = 0, limit: int = 100) -> dict
def write_file(path: str, content: str) -> dict
def edit_file(path: str, old_text: str, new_text: str) -> dict
def glob(pattern: str) -> dict
def grep(pattern: str, path: str = "/", include: str = None) -> dict

# Execution
def execute(command: str, timeout: int = 30) -> dict
def execute_python(code: str, timeout: int = 60) -> dict

# Database
async def execute_sql(query: str, database: str = "default") -> dict
async def get_schema(database: str = "default") -> dict
async def list_tables(database: str = "default") -> dict
async def describe_table(table: str, database: str = "default") -> dict

# Skills
def list_skills() -> list[dict]
def load_skill(skill_name: str) -> str

# Subagents
async def task(subagent: str, task: str, context: str = None) -> dict
async def parallel_tasks(tasks: list[dict]) -> dict
```

---

## Appendix A: Example Usage

```python
# examples/data_analysis.py

import asyncio
from vel import create_deep_agent

async def main():
    # Create agent with database access
    agent = create_deep_agent(
        model={"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
        databases={"analytics": "postgresql://user:pass@localhost/analytics"},
        sandbox=True,
    )
    
    # Run data analysis task
    async for event in agent.run_stream(
        "Analyze our user signups for the past 6 months. "
        "Break down by source, show month-over-month growth, "
        "and identify any notable trends. Create a report with charts."
    ):
        if event.type == "token":
            print(event.content, end="", flush=True)
        elif event.type == "tool_call":
            tool = event.metadata.get("tool_name", "unknown")
            print(f"\n🔧 Using {tool}...")
    
    print("\n\n✅ Analysis complete!")

asyncio.run(main())
```

```python
# examples/research_report.py

import asyncio
from vel import create_deep_agent, SubagentConfig

async def main():
    # Create agent with specialized subagents
    agent = create_deep_agent(
        subagents=[
            SubagentConfig(
                name="market-researcher",
                description="Specializes in market analysis and competitive intelligence",
                system_prompt="You are a market research specialist. Focus on market size, trends, and competitive landscape.",
            ),
            SubagentConfig(
                name="tech-researcher", 
                description="Specializes in technical analysis and architecture",
                system_prompt="You are a technical researcher. Focus on architecture, implementation details, and technical tradeoffs.",
            ),
        ],
    )
    
    # Run parallel research
    result = await agent.run(
        "Research the current state of AI agent frameworks. "
        "Cover both market landscape and technical approaches. "
        "Create a comprehensive report comparing top options."
    )
    
    print(result)

asyncio.run(main())
```

---

**END OF PRD**

*Hand this document to Claude Code for implementation.*