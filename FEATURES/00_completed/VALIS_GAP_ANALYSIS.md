# Valis Harness vs DeepAgents: Gap Analysis

**Date:** January 2025

---

## Complete Feature Comparison

| Feature | DeepAgents | Valis PRD (Original) | Valis + Addendum | Status |
|---------|------------|---------------------|------------------|--------|
| **Core Middleware** |
| TodoListMiddleware (planning) | ✅ write_todos, read_todos | ✅ write_todos | ✅ | PARITY |
| FilesystemMiddleware | ✅ ls, read, write, edit, glob, grep, execute | ✅ ls, read, write, edit, glob, grep | ✅ | PARITY |
| SubAgentMiddleware | ✅ task tool with state isolation | ✅ task, parallel_tasks | ✅ | PARITY |
| SkillsMiddleware | ✅ Progressive disclosure, SKILL.md | ✅ SKILL.md format | ✅ | PARITY |
| SummarizationMiddleware | ✅ Auto-summarize at threshold | ❌ | ✅ Addendum | PARITY |
| HumanInTheLoopMiddleware | ✅ Configurable interrupts | ✅ HITLMiddleware | ✅ | PARITY |
| MemoryMiddleware | ✅ Loads AGENTS.md | ❌ | ✅ Addendum | PARITY |
| **Context Engineering** |
| Large result offloading | ✅ >20K tokens → file | ❌ | ✅ Addendum | PARITY |
| Tool call compaction | ✅ At 85% context | ❌ | ✅ Addendum | PARITY |
| Conversation summarization | ✅ At 95% context | ❌ | ✅ Addendum | PARITY |
| Original transcript preservation | ✅ Saved to filesystem | ❌ | ✅ Addendum | PARITY |
| **Long-term Memory** |
| CompositeBackend | ✅ Route paths to different backends | ❌ | ✅ Addendum | PARITY |
| StoreBackend (/memories/) | ✅ Persistent across sessions | ❌ | ✅ Addendum | PARITY |
| Memory-First Protocol | ✅ Check memory before responding | ❌ | ✅ Addendum | PARITY |
| AGENTS.md auto-load | ✅ Global + project-specific | ❌ | ✅ Addendum | PARITY |
| **Backends** |
| StateBackend (ephemeral) | ✅ In-memory state | ✅ StateFilesystemBackend | ✅ | PARITY |
| FilesystemBackend (local) | ✅ Real filesystem | ✅ SandboxFilesystemBackend | ✅ | PARITY |
| Local sandbox (bubblewrap/Seatbelt) | ✅ | ✅ | ✅ | PARITY |
| Remote sandbox (Modal) | ✅ | ❌ | ✅ Addendum | PARITY |
| Remote sandbox (Runloop) | ✅ | ❌ | ✅ Addendum | PARITY |
| Remote sandbox (Daytona) | ✅ | ❌ | ✅ Addendum | PARITY |
| Database backend | ⚠️ Not core | ✅ | ✅ | VALIS AHEAD |
| **Integrations** |
| Web search (Tavily) | ✅ Built-in | ❌ | ✅ Addendum | PARITY |
| MCP support | ✅ Via langchain-mcp-adapters | ❌ | ❌ | GAP |
| LangSmith tracing | ✅ Native | N/A (uses Mesh) | N/A | DIFFERENT APPROACH |
| **Optimizations** |
| AnthropicPromptCachingMiddleware | ✅ 5-min TTL | ❌ | ✅ Addendum | PARITY |
| LLMToolSelectorMiddleware | ✅ Filter tools by relevance | ❌ | ✅ Addendum | PARITY |
| ToolRetryMiddleware | ✅ Auto-retry failed tools | ❌ | ✅ Addendum | PARITY |
| **CLI** |
| Interactive TUI | ✅ Textual-based | ❌ | ❌ | OUT OF SCOPE |
| Conversation resume | ✅ | ❌ | ❌ | OUT OF SCOPE |
| Agent management | ✅ list, create, reset | ❌ | ❌ | OUT OF SCOPE |

---

## Gap Summary

### Gaps Closed by Addendum (P0-P1)

1. **Context Management Middleware** - Three-tier compression
2. **Long-term Memory** - CompositeBackend with /memories/ routing
3. **Remote Sandbox Support** - Modal, Runloop, Daytona
4. **Web Search Integration** - Tavily
5. **MemoryMiddleware** - AGENTS.md loading
6. **Prompt Caching** - Anthropic cache control
7. **Tool Retry** - Auto-retry with backoff
8. **Tool Selector** - LLM-based filtering for large tool sets

### Remaining Gaps (P2/Future)

| Gap | Notes |
|-----|-------|
| MCP Support | Could add via adapter pattern |
| CLI | Out of scope (use direct SDK) |
| LangSmith Integration | Different architecture (Mesh-based) |

### Areas Where Valis is Ahead

| Feature | Notes |
|---------|-------|
| Database Backend | Built-in SQL execution, schema introspection |
| Mesh Integration | Graph-based orchestration (DeepAgents uses LangGraph directly) |
| Parallel Subagents | explicit parallel_tasks() API |

---

## Files Produced

| File | Description |
|------|-------------|
| `VALIS_HARNESS_PRD.md` | Original PRD (7 features) |
| `VALIS_HARNESS_PRD_ADDENDUM.md` | Comprehensive addendum (5 features) |
| `VALIS_HARNESS_ADDENDUM_CONTEXT.md` | Detailed context management spec |
| `VEL_UPGRADE_PRD.md` | Vel API changes |
| `MESH_UPGRADE_PRD.md` | Mesh graph orchestration |

---

## Implementation Priority

### Phase 1: Core PRD (Weeks 1-5)
- Planning middleware
- Filesystem middleware  
- Local sandbox
- Skills system
- Database backend
- Subagents
- Factory function

### Phase 2: Parity Features (Weeks 6-7)
- Context management (P0)
- Long-term memory (P0)
- Remote sandboxes (P1)
- Web search (P1)

### Phase 3: Optimizations (Week 8)
- Prompt caching (P2)
- Tool retry (P2)
- Tool selector (P2)

### Future / Deferred
- MCP support
- CLI (if needed)

---

## Conclusion

With the original PRD plus addendum, Valis Harness achieves **feature parity with DeepAgents** for core agent capabilities. The main gaps are:

1. **MCP** - Easy to add later via adapter
2. **CLI** - Intentionally out of scope (Valis is SDK-first)

Valis has advantages in:
- Database integration (SQL execution)
- Mesh-based orchestration (more flexible than LangGraph for custom graphs)
- Parallel subagent execution

**Recommendation:** Proceed with implementation using PRD + Addendum.
