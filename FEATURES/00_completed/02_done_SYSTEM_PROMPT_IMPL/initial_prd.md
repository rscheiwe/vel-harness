# Vel Harness: Comprehensive Prompt System Implementation Guide

## Overview

Implement a modular prompt system in `vel_harness/` that brings Claude Code-quality prompts to the harness. Source prompts from the Piebald repo, adapt for our architecture, and integrate with existing middleware.

**Goal**: Robust, production-quality agent behavior matching Claude Code's capabilities.

---

## Directory Structure

Add to existing `vel_harness/`:

```
vel_harness/
├── prompts/                         # NEW - All prompt content
│   ├── __init__.py                  # Exports all prompts
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── base.py                  # BASE_SYSTEM_PROMPT (identity, principles)
│   │   ├── tone.py                  # TONE_PROMPT (communication style)
│   │   └── tasks.py                 # DOING_TASKS_PROMPT (task execution guidance)
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── bash.py                  # BASH_TOOL_PROMPT
│   │   ├── bash_sandbox.py          # BASH_SANDBOX_PROMPT
│   │   ├── bash_git.py              # BASH_GIT_PROMPT (commit/PR instructions)
│   │   ├── filesystem.py            # READ/WRITE/EDIT/LS/GLOB/GREP prompts
│   │   ├── todo.py                  # TODO_WRITE_PROMPT
│   │   └── task.py                  # TASK_TOOL_PROMPT (subagent delegation)
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── explore.py               # EXPLORE_AGENT_PROMPT
│   │   ├── plan.py                  # PLAN_AGENT_PROMPT
│   │   └── task_notes.py            # TASK_AGENT_NOTES_PROMPT
│   │
│   ├── utilities/
│   │   ├── __init__.py
│   │   └── compaction.py            # COMPACTION_PROMPT
│   │
│   └── reminders/
│       ├── __init__.py              # Conditional reminder injection
│       ├── plan_mode.py             # PLAN_MODE_REMINDER
│       ├── long_conversation.py     # LONG_CONVERSATION_REMINDER
│       └── error_recovery.py        # ERROR_RECOVERY_REMINDER
│
├── middleware/                      # EXISTING - Update to use prompts
│   ├── filesystem.py
│   ├── planning.py
│   └── ...
│
└── factory.py                       # EXISTING - Update to compose prompts
```

---

## Phase 1: Fetch Prompts from Piebald

### Source Repository

```
https://github.com/Piebald-AI/claude-code-system-prompts/tree/main/system-prompts
```

### P0 Prompts (Critical - Fetch First)

| Piebald File | Target File | Est. Tokens |
|--------------|-------------|-------------|
| `system-prompt-main-system-prompt.md` | `prompts/core/base.py` | 2,852 |
| `tool-description-bash.md` | `prompts/tools/bash.py` | 1,067 |
| `tool-description-read.md` | `prompts/tools/filesystem.py` | ~300 |
| `tool-description-write.md` | `prompts/tools/filesystem.py` | ~400 |
| `tool-description-edit.md` | `prompts/tools/filesystem.py` | ~500 |
| `tool-description-ls.md` | `prompts/tools/filesystem.py` | ~200 |
| `tool-description-glob.md` | `prompts/tools/filesystem.py` | ~250 |
| `tool-description-grep.md` | `prompts/tools/filesystem.py` | ~300 |
| `tool-description-todowrite.md` | `prompts/tools/todo.py` | 2,167 |
| `agent-prompt-explore.md` | `prompts/agents/explore.py` | 516 |
| `agent-prompt-plan-mode-enhanced.md` | `prompts/agents/plan.py` | 633 |

### P1 Prompts (Important - Fetch Second)

| Piebald File | Target File | Est. Tokens |
|--------------|-------------|-------------|
| `tool-description-bash-sandbox-note.md` | `prompts/tools/bash_sandbox.py` | 454 |
| `tool-description-bash-git-commit-and-pr.md` | `prompts/tools/bash_git.py` | ~800 |
| `tool-description-task.md` | `prompts/tools/task.py` | 294 |
| `agent-prompt-task-tool-extra-notes.md` | `prompts/agents/task_notes.py` | 127 |
| `utility-prompt-compaction.md` | `prompts/utilities/compaction.py` | ~500 |

---

## Phase 2: Prompt File Format

Each prompt file should follow this pattern:

```python
# vel_harness/prompts/tools/bash.py
"""
Bash tool prompt - execution guidance for shell commands.
Source: Piebald claude-code-system-prompts (adapted)
"""

BASH_TOOL_PROMPT = """
Executes a shell command in the user's environment.

## Usage Guidelines

- Use for running CLI commands, scripts, and system operations
- Working directory persists between commands; shell state does not
- The shell environment is initialized from the user's profile (bash or zsh)
- For long-running processes, consider using background execution

## Output Handling

- stdout and stderr are captured and returned
- Exit codes are included in the response
- Large outputs may be truncated; use file redirection for full output

## Security Considerations

- Avoid commands that modify system configuration without user approval
- Never execute commands that could expose sensitive credentials
- Prefer explicit file paths over glob patterns for destructive operations

## Examples

Good:
- `ls -la src/` - List directory contents
- `grep -r "TODO" --include="*.py"` - Search codebase
- `python -m pytest tests/` - Run tests
- `git status` - Check repository state

Avoid without approval:
- `rm -rf` - Destructive operations
- `chmod 777` - Overly permissive permissions
- Commands involving ~/.ssh, ~/.aws, or other credential paths
"""

# Token count: ~1,067 (will vary after adaptation)
TOKEN_ESTIMATE = 1067
```

---

## Phase 3: Variable Interpolation

Piebald prompts contain `${VARIABLE}` placeholders. Handle these:

### Strategy 1: Static Replacement (Preferred)

```python
# Before (Piebald raw):
# "Use ${BASH_TOOL_NAME} for shell commands"

# After (adapted):
BASH_TOOL_PROMPT = """
Use the `execute` tool for shell commands.
"""
```

### Strategy 2: Runtime Interpolation (When Needed)

```python
# prompts/core/base.py

from string import Template

_BASE_TEMPLATE = Template("""
You are $AGENT_NAME, an AI assistant created by $COMPANY.
Working directory: $WORKING_DIR
""")

def get_base_prompt(
    agent_name: str = "Vel",
    company: str = "the user",
    working_dir: str = None,
) -> str:
    import os
    return _BASE_TEMPLATE.substitute(
        AGENT_NAME=agent_name,
        COMPANY=company,
        WORKING_DIR=working_dir or os.getcwd(),
    )
```

### Variable Mapping Reference

| Piebald Variable | Vel Harness Value |
|------------------|-------------------|
| `${BASH_TOOL_NAME}` | `execute` |
| `${READ_TOOL_NAME}` | `read_file` |
| `${WRITE_TOOL_NAME}` | `write_file` |
| `${EDIT_TOOL_NAME}` | `edit_file` |
| `${GLOB_TOOL_NAME}` | `glob` |
| `${GREP_TOOL_NAME}` | `grep` |
| `${LS_TOOL_NAME}` | `ls` |
| `${TASK_TOOL_NAME}` | `task` |
| `${TODO_TOOL_NAME}` | `write_todos` / `read_todos` |

---

## Phase 4: Prompt Composition

### prompts/__init__.py

```python
"""
Vel Harness Prompt System

Modular prompts for robust agent behavior.
"""

from .core.base import BASE_SYSTEM_PROMPT, get_base_prompt
from .core.tone import TONE_PROMPT
from .core.tasks import DOING_TASKS_PROMPT

from .tools.bash import BASH_TOOL_PROMPT
from .tools.bash_sandbox import BASH_SANDBOX_PROMPT
from .tools.bash_git import BASH_GIT_PROMPT
from .tools.filesystem import (
    READ_TOOL_PROMPT,
    WRITE_TOOL_PROMPT,
    EDIT_TOOL_PROMPT,
    LS_TOOL_PROMPT,
    GLOB_TOOL_PROMPT,
    GREP_TOOL_PROMPT,
)
from .tools.todo import TODO_WRITE_PROMPT
from .tools.task import TASK_TOOL_PROMPT

from .agents.explore import EXPLORE_AGENT_PROMPT
from .agents.plan import PLAN_AGENT_PROMPT
from .agents.task_notes import TASK_AGENT_NOTES_PROMPT

from .utilities.compaction import COMPACTION_PROMPT

from .reminders import get_active_reminders


def compose_system_prompt(
    include_tools: list[str] = None,
    include_sandbox: bool = True,
    include_git: bool = True,
    custom_sections: list[str] = None,
) -> str:
    """
    Compose a complete system prompt from modular pieces.
    
    Args:
        include_tools: List of tool names to include prompts for.
                      None = include all.
        include_sandbox: Include bash sandbox instructions.
        include_git: Include git commit/PR instructions.
        custom_sections: Additional prompt sections to append.
    
    Returns:
        Complete system prompt string.
    """
    sections = [
        BASE_SYSTEM_PROMPT,
        TONE_PROMPT,
        DOING_TASKS_PROMPT,
    ]
    
    # Tool prompts
    tool_prompts = {
        "execute": BASH_TOOL_PROMPT,
        "read_file": READ_TOOL_PROMPT,
        "write_file": WRITE_TOOL_PROMPT,
        "edit_file": EDIT_TOOL_PROMPT,
        "ls": LS_TOOL_PROMPT,
        "glob": GLOB_TOOL_PROMPT,
        "grep": GREP_TOOL_PROMPT,
        "write_todos": TODO_WRITE_PROMPT,
        "task": TASK_TOOL_PROMPT,
    }
    
    if include_tools is None:
        include_tools = list(tool_prompts.keys())
    
    for tool_name in include_tools:
        if tool_name in tool_prompts:
            sections.append(tool_prompts[tool_name])
    
    # Conditional sections
    if include_sandbox and "execute" in include_tools:
        sections.append(BASH_SANDBOX_PROMPT)
    
    if include_git and "execute" in include_tools:
        sections.append(BASH_GIT_PROMPT)
    
    # Custom sections
    if custom_sections:
        sections.extend(custom_sections)
    
    return "\n\n".join(sections)


def compose_agent_prompt(agent_type: str) -> str:
    """
    Get the system prompt for a specific agent type.
    
    Args:
        agent_type: One of "explore", "plan", "task"
    
    Returns:
        Agent-specific system prompt.
    """
    agent_prompts = {
        "explore": EXPLORE_AGENT_PROMPT,
        "plan": PLAN_AGENT_PROMPT,
        "task": TASK_AGENT_NOTES_PROMPT,
    }
    
    base = compose_system_prompt()
    agent_specific = agent_prompts.get(agent_type, "")
    
    return f"{base}\n\n{agent_specific}"


# Convenience exports
__all__ = [
    # Composition functions
    "compose_system_prompt",
    "compose_agent_prompt",
    "get_active_reminders",
    
    # Core prompts
    "BASE_SYSTEM_PROMPT",
    "TONE_PROMPT", 
    "DOING_TASKS_PROMPT",
    
    # Tool prompts
    "BASH_TOOL_PROMPT",
    "BASH_SANDBOX_PROMPT",
    "BASH_GIT_PROMPT",
    "READ_TOOL_PROMPT",
    "WRITE_TOOL_PROMPT",
    "EDIT_TOOL_PROMPT",
    "LS_TOOL_PROMPT",
    "GLOB_TOOL_PROMPT",
    "GREP_TOOL_PROMPT",
    "TODO_WRITE_PROMPT",
    "TASK_TOOL_PROMPT",
    
    # Agent prompts
    "EXPLORE_AGENT_PROMPT",
    "PLAN_AGENT_PROMPT",
    "TASK_AGENT_NOTES_PROMPT",
    
    # Utility prompts
    "COMPACTION_PROMPT",
]
```

---

## Phase 5: Middleware Integration

### Update Existing Middleware Pattern

```python
# vel_harness/middleware/filesystem.py

from ..prompts import READ_TOOL_PROMPT, WRITE_TOOL_PROMPT  # NEW import

class FilesystemMiddleware:
    """Middleware for filesystem operations."""
    
    # NEW: Reference prompt from prompts module
    system_prompt_section = READ_TOOL_PROMPT + "\n\n" + WRITE_TOOL_PROMPT
    
    def __init__(self, ...):
        # existing init
        pass
    
    def wrap_request(self, request):
        # Inject prompt section if not already present
        if self.system_prompt_section not in request.system_prompt:
            request.system_prompt += "\n\n" + self.system_prompt_section
        
        # existing tool injection logic
        request.tools += self.tools
        return request
```

### Middleware Base Class Update

```python
# vel_harness/middleware/base.py

from abc import ABC, abstractmethod
from typing import Optional

class BaseMiddleware(ABC):
    """Base class for all middleware with prompt support."""
    
    # Override in subclasses to inject prompt sections
    system_prompt_section: Optional[str] = None
    
    @abstractmethod
    def wrap_request(self, request):
        """Wrap an outgoing request."""
        pass
    
    @abstractmethod
    def process_response(self, response):
        """Process an incoming response."""
        pass
    
    def get_prompt_section(self) -> str:
        """Get the prompt section this middleware contributes."""
        return self.system_prompt_section or ""
```

---

## Phase 6: Factory Update

### Update create_deep_agent()

```python
# vel_harness/factory.py

from .prompts import compose_system_prompt, compose_agent_prompt

def create_deep_agent(
    model: dict = None,
    tools: list = None,
    system_prompt: str = None,
    middleware: list = None,
    backend = None,
    interrupt_on: list = None,
    # NEW prompt configuration
    prompt_config: dict = None,
):
    """
    Create a configured deep agent instance.
    
    Args:
        model: Model configuration dict.
        tools: List of tools to enable.
        system_prompt: Custom system prompt (overrides composed prompt).
        middleware: List of middleware instances.
        backend: Filesystem backend.
        interrupt_on: Tools requiring human approval.
        prompt_config: Prompt composition options:
            - include_tools: List of tool names
            - include_sandbox: bool
            - include_git: bool
            - custom_sections: List of additional prompt strings
    
    Returns:
        Configured Agent instance.
    """
    # Default model
    if model is None:
        model = {
            'provider': 'anthropic',
            'model': 'claude-sonnet-4-5-20250929'
        }
    
    # Compose system prompt
    if system_prompt is None:
        prompt_config = prompt_config or {}
        system_prompt = compose_system_prompt(**prompt_config)
    
    # Default middleware stack
    default_middleware = [
        TodoMiddleware(),
        FilesystemMiddleware(backend=backend),
        SubagentMiddleware(),
    ]
    
    all_middleware = default_middleware + (middleware or [])
    
    # Collect prompt sections from middleware
    for mw in all_middleware:
        section = getattr(mw, 'system_prompt_section', None)
        if section and section not in system_prompt:
            system_prompt += "\n\n" + section
    
    # Create agent
    agent = Agent(
        model=model,
        system_prompt=system_prompt,
        tools=tools or [],
        middleware=all_middleware,
        interrupt_on=interrupt_on,
    )
    
    return agent


def create_explore_agent(**kwargs):
    """Create an explore subagent (read-only)."""
    kwargs['system_prompt'] = compose_agent_prompt('explore')
    kwargs['prompt_config'] = {
        'include_tools': ['read_file', 'ls', 'glob', 'grep', 'execute'],
        'include_sandbox': True,
        'include_git': False,
    }
    return create_deep_agent(**kwargs)


def create_plan_agent(**kwargs):
    """Create a planning subagent."""
    kwargs['system_prompt'] = compose_agent_prompt('plan')
    kwargs['prompt_config'] = {
        'include_tools': ['read_file', 'ls', 'glob', 'grep', 'write_todos'],
        'include_sandbox': False,
        'include_git': False,
    }
    return create_deep_agent(**kwargs)
```

---

## Phase 7: Reminders System

### Conditional Reminder Injection

```python
# vel_harness/prompts/reminders/__init__.py

from typing import List
from .plan_mode import PLAN_MODE_REMINDER
from .long_conversation import LONG_CONVERSATION_REMINDER
from .error_recovery import ERROR_RECOVERY_REMINDER

def get_active_reminders(
    context: dict,
) -> List[str]:
    """
    Get reminders that should be active given current context.
    
    Args:
        context: Dict with keys like:
            - plan_mode_active: bool
            - token_usage_percent: float
            - last_tool_failed: bool
            - consecutive_errors: int
    
    Returns:
        List of reminder strings to inject.
    """
    reminders = []
    
    # Plan mode reminder
    if context.get('plan_mode_active', False):
        reminders.append(PLAN_MODE_REMINDER)
    
    # Long conversation reminder (approaching context limit)
    usage = context.get('token_usage_percent', 0)
    if usage > 70:
        reminders.append(LONG_CONVERSATION_REMINDER)
    
    # Error recovery reminder
    if context.get('last_tool_failed', False):
        reminders.append(ERROR_RECOVERY_REMINDER)
    
    return reminders


def inject_reminders(system_prompt: str, context: dict) -> str:
    """Inject active reminders into system prompt."""
    reminders = get_active_reminders(context)
    if reminders:
        reminder_section = "\n\n## Active Reminders\n\n" + "\n\n".join(reminders)
        return system_prompt + reminder_section
    return system_prompt
```

---

## Implementation Checklist

### P0 - Core (Do First)

- [ ] Create `vel_harness/prompts/` directory structure
- [ ] Fetch `system-prompt-main-system-prompt.md` → `prompts/core/base.py`
- [ ] Extract tone section → `prompts/core/tone.py`
- [ ] Extract tasks section → `prompts/core/tasks.py`
- [ ] Fetch `tool-description-bash.md` → `prompts/tools/bash.py`
- [ ] Fetch filesystem tool descriptions → `prompts/tools/filesystem.py`
- [ ] Fetch `tool-description-todowrite.md` → `prompts/tools/todo.py`
- [ ] Fetch `agent-prompt-explore.md` → `prompts/agents/explore.py`
- [ ] Fetch `agent-prompt-plan-mode-enhanced.md` → `prompts/agents/plan.py`
- [ ] Create `prompts/__init__.py` with composition functions
- [ ] Update `factory.py` to use `compose_system_prompt()`
- [ ] Test: Basic agent creation with new prompts

### P1 - Safety & Delegation (Do Second)

- [ ] Fetch `tool-description-bash-sandbox-note.md` → `prompts/tools/bash_sandbox.py`
- [ ] Fetch `tool-description-bash-git-commit-and-pr.md` → `prompts/tools/bash_git.py`
- [ ] Fetch `tool-description-task.md` → `prompts/tools/task.py`
- [ ] Fetch `agent-prompt-task-tool-extra-notes.md` → `prompts/agents/task_notes.py`
- [ ] Fetch compaction prompt → `prompts/utilities/compaction.py`
- [ ] Update middleware to reference prompt modules
- [ ] Test: Sandbox behavior, git operations, subagent delegation

### P2 - Reminders & Polish (Do Third)

- [ ] Create `prompts/reminders/` with conditional injection
- [ ] Add plan mode reminder
- [ ] Add long conversation reminder
- [ ] Add error recovery reminder
- [ ] Integrate reminders with context middleware
- [ ] Test: Reminders inject at appropriate times

---

## Testing

### Prompt Composition Test

```python
# tests/test_prompts.py

from vel_harness.prompts import compose_system_prompt, compose_agent_prompt

def test_compose_system_prompt_default():
    prompt = compose_system_prompt()
    assert "execute" in prompt.lower() or "bash" in prompt.lower()
    assert len(prompt) > 5000  # Should be substantial

def test_compose_system_prompt_subset():
    prompt = compose_system_prompt(include_tools=["read_file", "ls"])
    assert "read" in prompt.lower()
    assert "write_file" not in prompt.lower()  # Not included

def test_compose_agent_prompt_explore():
    prompt = compose_agent_prompt("explore")
    assert "read-only" in prompt.lower()
    assert "strictly prohibited" in prompt.lower()

def test_token_budget():
    """Ensure prompts don't exceed reasonable size."""
    prompt = compose_system_prompt()
    # Rough estimate: 4 chars per token
    estimated_tokens = len(prompt) / 4
    assert estimated_tokens < 25000  # Stay under 25K tokens
```

### Integration Test

```python
# tests/test_factory_with_prompts.py

from vel_harness import create_deep_agent

def test_agent_creation_with_prompts():
    agent = create_deep_agent()
    assert agent.system_prompt is not None
    assert len(agent.system_prompt) > 5000

def test_explore_agent_is_readonly():
    from vel_harness.factory import create_explore_agent
    agent = create_explore_agent()
    assert "read-only" in agent.system_prompt.lower()
```

---

## Token Budget Summary

| Component | Tokens | Cumulative |
|-----------|--------|------------|
| Base system prompt | ~2,852 | 2,852 |
| Tone | ~300 | 3,152 |
| Tasks | ~400 | 3,552 |
| Bash tool | ~1,067 | 4,619 |
| Bash sandbox | ~454 | 5,073 |
| Bash git | ~800 | 5,873 |
| Filesystem tools (6) | ~1,950 | 7,823 |
| Todo tool | ~2,167 | 9,990 |
| Task tool | ~294 | 10,284 |
| Explore agent | ~516 | 10,800 |
| Plan agent | ~633 | 11,433 |
| Task notes | ~127 | 11,560 |
| Compaction | ~500 | 12,060 |
| Reminders (conditional) | ~500 | 12,560 |
| **Total (full suite)** | **~12,560** | |

~6% of 200K context window. Acceptable overhead for robust behavior.

---

## Notes

1. **Strip ${VARIABLES}** - Replace all Piebald interpolation variables with static values or make configurable.

2. **Tool names matter** - Ensure prompt references match actual tool names in `vel_harness/tools/`.

3. **Don't duplicate** - If middleware already has tool descriptions inline, either:
   - Move them to prompts/ and reference, OR
   - Keep them inline and skip the prompts/tools/ file for that tool

4. **Test incrementally** - After each prompt file, verify the agent still works.

5. **Version tracking** - Note which Piebald version prompts were extracted from in comments.