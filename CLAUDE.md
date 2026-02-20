# CLAUDE.md

## Commands

```bash
# Install
pip install -e ".[dev]"          # dev dependencies
pip install -e ".[all]"          # all extras (database, accurate-tokens, ctxzip)

# Test
pytest                           # all tests (asyncio_mode=auto)
pytest tests/test_harness.py     # single file
pytest tests/test_harness.py::test_name  # single test

# Lint & Format
ruff check vel_harness tests     # lint (line-length=100, py311, E/F/I/W rules)
black vel_harness tests          # format
mypy                             # type check (disallow_untyped_defs=true)

# TypeScript (vel_harness-ts/)
npm run build                    # tsc
npm run test                     # vitest
npm run lint                     # eslint src
```

## Architecture

```
VelHarness (harness.py)  ← public API
  └── DeepAgent (factory.py)  ← internal, holds vel.Agent + middlewares
        └── vel.Agent(tools=all_tools)  ← flat tool list from all middlewares
```

`VelHarness` is the entry point. It wraps `DeepAgent`, which is created by `create_deep_agent()` factory. The factory:
1. Instantiates each middleware and collects their tools
2. Wraps all tools with cross-cutting layers: checkpoint → cache → retry → hooks (innermost to outermost)
3. Passes the flat tool list to `vel.Agent`

### Middleware Protocol

Middlewares are **not** a pipeline/chain. Each provides tools + system prompt segments + state:

```python
class Middleware(Protocol):
    def get_tools(self) -> List[Any]: ...
    def get_system_prompt_segment(self) -> str: ...
    def get_state(self) -> Dict[str, Any]: ...
    def load_state(self, state: Dict[str, Any]) -> None: ...
```

All middlewares extend `BaseMiddleware`. Key middlewares:

| Middleware | Tools |
|---|---|
| `FilesystemMiddleware` | read_file, write_file, edit_file, ls, glob, grep |
| `SandboxMiddleware` | execute, execute_python |
| `PlanningMiddleware` | write_todos |
| `SkillsMiddleware` | list_skills, activate_skill, deactivate_skill, get_skill, search_skills |
| `SubagentsMiddleware` | spawn_subagent, spawn_parallel, wait_subagent, etc. |
| `ContextManagementMiddleware` | (no tools — manages context window) |
| `MemoryMiddleware` | memory persistence tools |
| `ToolCachingMiddleware` | get_cache_stats, clear_tool_cache |
| `DatabaseMiddleware` | SQL query tools |

### Backends

Filesystem and execution use protocol-based backends (`@runtime_checkable`):
- `RealFilesystemBackend` — direct OS access (production)
- `StateFilesystemBackend` — in-memory (testing)
- `SandboxFilesystemBackend` — macOS Seatbelt / Linux bubblewrap
- `CompositeBackend` — routes paths to different backends by prefix

## Key Design Decisions

### System prompt is static
The system prompt never changes after construction. This preserves Anthropic prompt caching.

### Skills are injected as tool_result, not system prompt
`SkillInjectionMode.TOOL_RESULT` (default): when `activate_skill` is called, the skill content is returned wrapped in `<skill-loaded name="...">` XML. This avoids invalidating the prompt cache. The legacy `SYSTEM_PROMPT` mode exists but breaks caching.

### Append-only message history
Messages are never edited after being added. Each turn appends user → assistant → tool_result messages. Context is managed by `ContextManagementMiddleware` which truncates/offloads/evicts/summarizes at progressive thresholds (25k chars, 8k tokens, 85%, 95% of window).

### Tool wrapping pattern
Tools (`vel.ToolSpec`) are wrapped by creating a new ToolSpec with a modified handler that intercepts the original. The factory applies wrapping layers in order: checkpoint → cache → retry → hooks.

## Subagent Types

Defined in `agents/registry.py` as `DEFAULT_AGENTS`:

| Type | Tools | Max Turns | Purpose |
|---|---|---|---|
| `default` | execute, read/write/edit, ls, glob, grep, write_todos | 50 | General task execution |
| `explore` | read_file, ls, glob, grep, execute | 30 | Read-only codebase exploration |
| `plan` | read_file, ls, glob, grep, write_todos | 20 | Structured planning |

Model shorthand: `"sonnet"`, `"opus"`, `"haiku"`, `"inherit"`. Custom agents registered via `VelHarness(custom_agents={...})` or `harness.register_agent()`.

## CLIs

**`vel-harness`** — stub entry point (`vel_harness.cli.main:cli_entry`)

**`valis`** — full Textual TUI + Click CLI (`valis_cli.main:main`):
- `valis` — interactive TUI chat
- `valis ask "prompt"` — single-turn non-interactive
- `valis init` — initialize `.valis/` project dir
- `valis config` / `valis skills` / `valis models` / `valis version`
- Options: `--model/-m`, `--provider/-p`, `--project/-P`, `--no-sandbox`, `--compact`, `--show-thinking`
- Slash commands: `/help`, `/reset`, `/skills`, `/config`, `/permissions`, `/restart`, `/copy`, `/tokens`

## Project Structure

```
vel_harness/           # Main Python package
  harness.py           # VelHarness (public API)
  factory.py           # DeepAgent + create_deep_agent()
  config.py            # Dataclass config hierarchy (DeepAgentConfig, ModelConfig, etc.)
  session.py           # HarnessSession (async context manager, checkpoint/rewind)
  middleware/           # All middleware implementations
  backends/            # FilesystemBackend, ExecutionBackend implementations
  agents/              # AgentConfig, AgentRegistry, DEFAULT_AGENTS
  skills/              # SkillsRegistry, Skill loader (YAML frontmatter .md files)
  prompts/             # Modular prompt composition (adapted from Piebald)
  hooks.py             # HookEngine, HookMatcher, pre/post tool hooks
  reasoning.py         # ReasoningConfig: native, reflection, prompted, none
  fallback.py          # FallbackStreamWrapper (auto-retry on 429/5xx with fallback model)
  checkpoint.py        # FileCheckpointManager (track changes, rewind LIFO)
  approval/            # ApprovalManager (async tool approval with futures)
valis_cli/             # Textual TUI application
  app.py               # ValisCLI(App) — TUI
  agent.py             # AgentRunner (wraps VelHarness, streaming, approval)
  commands/            # Slash command handlers
vel_harness-ts/        # TypeScript port of vel-harness
valis_cli-ts/          # TypeScript port of valis CLI
skills/                # Bundled skill .md files (coding, data_analysis, research, reporting)
tests/                 # pytest suite (~31 test files)
  conftest.py          # Fixtures: state_backend, populated_backend, filesystem/planning middleware, todo_list, sample_skill_content
examples/              # Quickstart, streaming, etc.
```

## Testing

- **Framework:** pytest + pytest-asyncio (asyncio_mode = "auto" — all async tests auto-detected)
- **Key conftest fixtures:**
  - `state_backend` — fresh `StateFilesystemBackend` (in-memory)
  - `populated_backend` — `StateFilesystemBackend` with sample files (readme.md, sales.csv, users.csv, q1.md, main.py, utils.py)
  - `filesystem_middleware` / `populated_filesystem_middleware` — `FilesystemMiddleware` with above backends
  - `planning_middleware`, `todo_list`, `populated_todo_list`
  - `sample_skill_content` — YAML frontmatter + markdown body string
- **Pattern:** Tests use in-memory backends; no real filesystem or network calls needed. Tool handlers are called directly (not through the agent loop).

## Dependencies

- `vel-ai` (git: github.com/rscheiwe/vel.git) — agent runtime
- `agentmesh-py` (git: github.com/rscheiwe/mesh.git) — graph orchestration
- Python >= 3.11
