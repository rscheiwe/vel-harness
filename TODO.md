# Valis CLI TODO

## Mesh Integration (Clarified Architecture)

### When Mesh is NOT Needed

**Sequential subagents (like Claude Code):**
```
Main Agent
    │
    ├── task("research X") ──► Subagent runs ──► returns result
    │                              (blocking)
    ├── task("research Y") ──► Subagent runs ──► returns result
    │                              (blocking)
    └── synthesize results
```
This is just nested while loops. No Mesh needed.

### When Mesh IS Needed

**Parallel subagents:**
```
Main Agent
    │
    ├──┬── task("research X") ──► Subagent 1 ─┬──► aggregate
    │  ├── task("research Y") ──► Subagent 2 ─┤
    │  └── task("research Z") ──► Subagent 3 ─┘
    │                (parallel)
    └── synthesize results
```
This requires orchestration. Mesh adds value here.

### Target Architecture

```
┌─────────────────────────────────────────────────┐
│                    CLI                          │
├─────────────────────────────────────────────────┤
│              Valis Harness                      │
│  ┌─────────────────────────────────────────┐   │
│  │  Middleware (context, memory, skills)   │   │
│  ├─────────────────────────────────────────┤   │
│  │  Vel (main agent loop)                  │   │
│  ├─────────────────────────────────────────┤   │
│  │  Mesh (ONLY for parallel subagents)     │   │
│  └─────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

### When Mesh Activates

| Scenario | Uses Mesh? |
|----------|------------|
| Simple task, no subagents | ❌ Just Vel loop |
| One subagent at a time | ❌ Nested Vel loops |
| `task` with `parallel=True` | ✅ Mesh fan-out |
| Multiple `task` calls in one turn | ✅ Mesh parallel |

### The `task` Tool Signature

```python
def task(
    instructions: str,
    context: list[str] = None,
    parallel: bool = False,  # ← This triggers Mesh
) -> str:
    if parallel:
        # Queue for Mesh parallel execution
        return mesh.spawn_parallel(instructions, context)
    else:
        # Blocking nested agent loop
        return run_subagent_sync(instructions, context)
```

### Why Mesh Still Matters

1. **Human-in-the-loop**: Mesh interrupts could solve the tool approval flow issue
2. **Checkpointing**: Proper state persistence/resume
3. **Parallel subagents**: Fan-out/fan-in for concurrent research tasks
4. **Graph-based orchestration**: More flexible workflows when needed

### Action Items
- [ ] Add mesh as optional dependency
- [ ] Implement `task` tool with `parallel` flag
- [ ] Use Mesh only when `parallel=True` is specified
- [ ] Add checkpoint/resume support via Mesh backends

### Completed
- [x] `SubagentSpawner.spawn_many()` now uses `asyncio.gather()` for parallel execution
- [x] `SubagentSpawner.wait_all()` now waits for all subagents in parallel

---

## Token Efficiency / Context Management

Current implementation burns tokens excessively. Example: "how much is Mesh used in vel_harness" used **489k tokens** when it should use ~10-20k max.

### Problems Observed
1. ~~**No tool result truncation**~~ - ✅ Added `head_limit` param to grep (default 50, max 200)
2. **Redundant tool calls** - agent runs 15+ similar searches instead of 2-3
3. ~~**No context window awareness**~~ - ✅ Added `/tokens` command and status bar tracking
4. **Using execute for grep** - inefficient, should use native grep tool

### What PRD Specified
`ContextManagementMiddleware` was supposed to handle:
- `tool_result_token_limit` - truncate large results ✅ Implemented
- `eviction_threshold` - summarize when context too large ✅ Implemented
- `preview_lines` - show truncated previews ✅ Implemented

### Two-Phase Context Management ✅
Clear separation of concerns:
- **Phase 1 (Immediate)**: Truncate results >25K tokens with head/tail preview
  - Content stays IN context (just shorter)
  - Agent sees results NOW without re-fetch
- **Phase 2 (Historical)**: ctx-zip offloads old results >8K tokens after assistant responds
  - Content moves OUT of context
  - Agent must use read tools to retrieve
- Optional dependency: `pip install vel-harness[ctxzip]`

### Token Counting
- [x] Added optional tiktoken for accurate counting (`pip install vel-harness[accurate-tokens]`)
- [x] Improved fallback heuristic (content-aware: JSON ~3 chars/token, prose ~3.8 chars/token)
- [x] API-reported usage now tracked and displayed in `/tokens` command

### Message Tracking Fix ✅
- Fixed `AgentRunner.get_message_history()` to include full conversation (tool calls, results, assistant responses)
- Added `get_api_usage()` for cumulative token usage from API

### Reference
- Anthropic's Advanced Tool Use guide: https://www.anthropic.com/engineering/advanced-tool-use

### Completed
- [x] Implement tool result truncation (like Claude Code's `head_limit`)
- [x] Add context window tracking to status bar
- [x] Integrate ctx-zip-py with two-pass compression
- [x] Add `/tokens` command for detailed usage breakdown
- [x] Track API-reported token usage
- [x] Fix message history tracking in AgentRunner
- [x] **Enable Anthropic prompt caching** - added cache_control to vel's anthropic.py, extended-cache-ttl header
- [x] **Wire up context middleware** - AgentRunner now calls process_tool_result() and after_assistant_response()
- [x] **Simple N-turn eviction** - fallback that works without ctx-zip, evicts tool results older than 3 turns
- [x] **Cache hit tracking** - /tokens now shows cache read/write stats and hit rate
- [x] **Modular prompt system** - vel_harness/prompts/ with compose_system_prompt()

### Remaining
- [ ] Implement smart search strategies (don't grep 5x for similar patterns)
- [ ] Add token budget awareness to agent
- [ ] **Test prompt updates** - run CLI and verify agent behavior with new composed prompts

---

## Tool Approval UX (like Claude Code)

Add back proper tool-use approval with blocking modal that actually works.

### Current Issue
The approval modal doesn't work due to async deadlock - vel's callback blocks while waiting for TUI approval, but TUI can't process input because the event loop is blocked.

### Claude Code Example

**Before approval (user sees prompt):**
```
USER: now what can we do about this list of tools, where one renders after another? it kind of
takes up a lot of the UI. claude code kinda does this thing where if there's a long list
of actions happening, it's like this vertical carousel with fading in/out UI. does that
make sense?
```

**After approval (compact result):**
```
⏺ Read(/var/folders/_f/gms6bl693zd82p4yxjd6hkh19syl4s/T/TemporaryItems/NSIRD_screencaptureui_
      i25U3T/Screenshot 2026-01-29 at 3.51.36 PM.png)
  ⎿  Read image (185.9KB)
```

### Requirements
1. Modal shows tool name + args, waits for user input (y/n/a)
2. Tool execution actually pauses until approval
3. After approval, show compact single-line result with icon
4. "Always Allow" saves to `.valis/settings.local.json`

### Potential Solutions
1. Run vel agent in separate thread/process so TUI event loop isn't blocked
2. Use Textual workers properly for the approval flow
3. Restructure vel to use a callback-based approval instead of blocking await

---

## Smoother Scrolling

Current scrolling UX issues:
- Jumpy auto-scroll during streaming
- Can scroll away during generation but jumps back erratically
- Should smoothly follow new content unless user explicitly scrolls up

### Action Items
- [x] Implement smooth auto-scroll that follows streaming content
- [x] Detect when user manually scrolls up and pause auto-scroll (`_user_scrolled_up` flag)
- [x] Resume auto-scroll when user scrolls back to bottom (`on_scroll_down` handler)
- [ ] Consider using Textual's animation support for smoother transitions

---

## UI Polish

### Message Spacing
- [x] Add spacing above/below user messages for better separation clarity
- [x] Visual distinction between conversation turns (margin-top/bottom on user messages)

### Pasted Text Rendering
- [ ] Fix multiline user messages not rendering with newlines
  - Long pastes (>10 lines) collapse to `[Pasted X lines]` placeholder (working)
  - On submit, placeholder expands to full content (working)
  - But rendered user message shows all text on single line (broken)
  - Issue: `MessageWidget` uses nested `Static` inside `Static`, may need different approach
  - Tried: `height: auto` CSS on both widgets - didn't fix
  - Tried: Switching to `render()` instead of `compose()` - broke all messages
  - May need to change how `Text()` handles multiline content or use different Rich renderable

### Focus Highlight in Cursor IDE
- [ ] Clicking chat area causes screen to "lighten" momentarily
  - Only happens in Cursor IDE, not in regular terminal
  - Claude Code doesn't have this issue
  - Tried: `can_focus = False` on ChatDisplay - didn't fix
  - Tried: CSS `:focus` rules with `tint: transparent` - partially works but affects input
  - May be Cursor-specific terminal behavior or need deeper Textual focus handling

### Text Selection
- [ ] Cannot select rendered text for copy/paste
  - Textual widgets don't support native text selection by default
  - May need to implement custom selection or use a different rendering approach
  - Claude Code allows text selection - investigate how they handle this
