# Valis CLI Fork Strategy

**Source:** `langchain-ai/deepagents` (MIT License)  
**Target:** `valis-cli`  
**Approach:** Fork deepagents-cli, swap agent backend

---

## 1. What to Keep (Unchanged)

These components are framework-agnostic and work as-is:

```
libs/deepagents-cli/
├── deepagents_cli/
│   ├── main.py              # Entry point, arg parsing ✅
│   ├── config.py            # Settings, paths, project detection ✅
│   ├── app.py               # Textual TUI application ✅
│   ├── welcome.py           # Welcome banner ✅
│   ├── skills.py            # Skill discovery ✅
│   ├── commands/            # list, reset, skills commands ✅
│   │   ├── list_agents.py
│   │   ├── reset.py
│   │   └── skills.py
│   └── widgets/             # TUI components ✅
│       ├── chat.py
│       ├── input.py
│       └── approval.py
```

## 2. What to Replace

Only the agent creation/invocation layer:

```python
# BEFORE (deepagents-cli/agent.py)
from deepagents import create_deep_agent
from langchain.chat_models import init_chat_model

agent = create_deep_agent(
    model=init_chat_model("anthropic:claude-sonnet-4-5"),
    tools=[...],
    system_prompt=system_prompt,
    interrupt_on={...},
    backend=backend,
)
result = agent.invoke({"messages": [...]})

# AFTER (valis-cli/agent.py)
from valis import create_deep_agent

agent = create_deep_agent(
    model={'provider': 'anthropic', 'model': 'claude-sonnet-4-5-20250929'},
    tools=[...],
    system_prompt=system_prompt,
    interrupt_on={...},
    backend=backend,
)
result = await agent.run({"messages": [...]})
```

## 3. Files to Modify

| File | Changes |
|------|---------|
| `agent.py` | Replace `deepagents` import with `valis` |
| `app.py` | Update streaming event names if different |
| `pyproject.toml` | Replace `deepagents` dep with `valis-harness` |

### 3.1 agent.py Diff

```python
# Remove
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langchain.chat_models import init_chat_model

# Add
from valis import create_deep_agent
from valis.backends import CompositeBackend, StateBackend, PersistentStoreBackend
```

### 3.2 Event Name Mapping

| DeepAgents Event | Valis Event |
|------------------|-------------|
| `on_chat_model_stream` | `text-delta` |
| `on_tool_start` | `tool-call` |
| `on_tool_end` | `tool-result` |

If Valis events differ, create adapter in `app.py`:

```python
async def normalize_events(valis_stream):
    """Adapt Valis events to CLI expected format"""
    async for event in valis_stream:
        if event['type'] == 'text-delta':
            yield {'type': 'on_chat_model_stream', 'content': event['delta']}
        # ...
```

## 4. pyproject.toml Changes

```toml
# BEFORE
[project]
name = "deepagents-cli"
dependencies = [
    "deepagents>=0.3.0",
    "textual>=0.50.0",
    "rich>=13.0.0",
    "click>=8.0.0",
    "python-dotenv>=1.0.0",
]

# AFTER
[project]
name = "valis-cli"
dependencies = [
    "valis-harness>=0.1.0",
    "textual>=0.50.0",
    "rich>=13.0.0",
    "click>=8.0.0",
    "python-dotenv>=1.0.0",
]
```

## 5. Path Changes

| DeepAgents | Valis |
|------------|-------|
| `~/.deepagents/` | `~/.valis/` |
| `.deepagents/` | `.valis/` |
| `AGENTS.md` | `AGENTS.md` (keep) |
| `/memories/` | `/memories/` (keep) |

Single sed replacement in `config.py`:

```bash
sed -i 's/deepagents/valis/g' config.py
```

## 6. Implementation Steps

### Week 1: Fork & Rename

```bash
# Clone
git clone https://github.com/langchain-ai/deepagents
cd deepagents/libs/deepagents-cli

# Create new repo
mkdir valis-cli
cp -r deepagents_cli valis_cli
cp pyproject.toml README.md valis-cli/

# Rename package
mv valis_cli/deepagents_cli valis_cli/valis_cli
find valis_cli -name "*.py" -exec sed -i 's/deepagents_cli/valis_cli/g' {} \;
find valis_cli -name "*.py" -exec sed -i 's/deepagents/valis/g' {} \;
```

### Week 2: Swap Agent Backend

1. Update `agent.py` imports
2. Match `create_deep_agent` signature
3. Update event streaming in `app.py`
4. Test basic conversation flow

### Week 3: Verify Feature Parity

- [ ] Interactive mode works
- [ ] Slash commands work
- [ ] Skills loading works
- [ ] Memory persistence works
- [ ] Approval flow works
- [ ] Sandbox integration works

## 7. API Compatibility Layer

If Valis Harness API differs from DeepAgents, create a thin adapter:

```python
# valis_cli/compat.py

from valis import create_deep_agent as _create_deep_agent

def create_deep_agent(
    model=None,
    tools=None,
    system_prompt=None,
    interrupt_on=None,
    backend=None,
    **kwargs
):
    """Adapter matching DeepAgents signature"""
    
    # Convert model format
    if isinstance(model, str):
        provider, model_name = model.split(':')
        model = {'provider': provider, 'model': model_name}
    
    # Map interrupt_on to Valis format
    # ...
    
    return _create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        interrupt_on=interrupt_on,
        backend=backend,
        **kwargs
    )
```

## 8. Testing Strategy

```bash
# Run DeepAgents CLI
uvx deepagents-cli
> Create a hello.py file

# Run Valis CLI (same task)
uvx valis-cli
> Create a hello.py file

# Compare:
# - Output format
# - Approval flow
# - File creation
# - Memory saving
```

## 9. What NOT to Fork

Skip these (not needed or will diverge):

- `deepagents_harbor/` - evaluation harness (build separately if needed)
- LangSmith tracing (replace with own observability)
- LangGraph-specific checkpointing (use Mesh checkpoints)

## 10. Estimated Effort

| Task | Time |
|------|------|
| Fork + rename | 2 hours |
| Swap agent.py | 4 hours |
| Update app.py streaming | 4 hours |
| Config path changes | 1 hour |
| Testing | 8 hours |
| **Total** | ~2.5 days |

Much faster than building from scratch (~6 weeks in original PRD).

---

## Summary

**Do:**
- Fork the CLI (MIT license allows this)
- Keep TUI, config, skills, approval unchanged
- Replace only `agent.py` with Valis imports

**Don't:**
- Rewrite TUI from scratch
- Reinvent config discovery
- Rebuild approval formatters

The deepagents-cli is ~90% framework-agnostic. Only the thin agent creation layer (~10%) needs replacement.