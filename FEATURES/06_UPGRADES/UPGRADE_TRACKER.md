# Vel-Harness Upgrade Tracker: Agent SDK Parity

> **Goal:** Bring vel-harness to production parity with Claude Agent SDK capabilities.
> **Target:** Python first, then transfer to TS mirror.
> **Plan:** See `/Users/richard.s/.claude/plans/compressed-launching-bunny.md` for full implementation details.

---

## Status Overview

| # | Workstream | Status | Files Changed | Tests | TS Transfer |
|---|-----------|--------|--------------|-------|-------------|
| 1 | Wire up existing middleware (caching + retry) | COMPLETE | config.py, factory.py, harness.py | test_caching_wiring.py (28 tests) | Ready |
| 2 | Hooks upgrade (control hooks) | COMPLETE | hooks.py (new), factory.py, harness.py, \_\_init\_\_.py | test_hooks.py (33 tests) | Ready |
| 3 | ReasoningConfig (native/reflection/prompted/none) | COMPLETE | reasoning.py (new), config.py, factory.py, harness.py, \_\_init\_\_.py | test_reasoning.py (60 tests) | Ready |
| 4 | Sandbox settings (expanded config) | COMPLETE | config.py, hooks.py, factory.py, harness.py | test_sandbox_settings.py (33 tests) | Ready |
| 5 | Subagent shape alignment (AgentDefinition) | COMPLETE | agents/config.py, agents/registry.py, agents/\_\_init\_\_.py, harness.py, \_\_init\_\_.py | test_agent_definition.py (33 tests) | Ready |
| 6 | Fallback model (automatic retry) | COMPLETE | fallback.py (new), config.py, harness.py, \_\_init\_\_.py | test_fallback.py (55 tests) | Ready |
| 7 | Dynamic mid-conversation controls (HarnessSession) | COMPLETE | session.py (new), harness.py, \_\_init\_\_.py | test_session.py (47 tests) | Ready |
| 8 | File checkpointing / rewind | COMPLETE | checkpoint.py (new), factory.py, session.py, harness.py, \_\_init\_\_.py | test_checkpoint.py (37 tests) | Ready |

---

## Workstream Details

### WS1: Wire Up Existing Middleware
- **Scope:** Connect already-built `ToolCachingMiddleware`, `AnthropicPromptCachingMiddleware`, `ToolRetryMiddleware`, `CircuitBreakerMiddleware` into factory pipeline
- **Key pattern:** Wrap (not add) — tools are wrapped with caching/retry after collection from middleware
- **Files to modify:**
  - `vel_harness/config.py` — Add `CachingConfig`, `RetryConfig`
  - `vel_harness/factory.py` — Wire middleware with wrap pattern
  - `vel_harness/harness.py` — Expose `caching` and `retry` params
- **Files to test:**
  - `tests/test_caching_wiring.py`
  - `tests/test_retry_wiring.py`
- **API surface for TS transfer:**
  - `CachingConfig` dataclass
  - `RetryConfig` dataclass
  - `VelHarness(caching=True, retry=True)` constructor params

### WS2: Hooks Upgrade
- **Scope:** Control hooks that can modify/block tool calls (not just observe)
- **Key pattern:** Tool wrapping with pre/post hook execution
- **New files:**
  - `vel_harness/hooks.py` — HookEngine, HookMatcher, HookResult, event types
- **Files to modify:**
  - `vel_harness/config.py` — (optional HooksConfig)
  - `vel_harness/factory.py` — Wire hooks via tool wrapping
  - `vel_harness/harness.py` — Expose `hooks` param
- **Files to test:**
  - `tests/test_hooks.py`
- **API surface for TS transfer:**
  - `HookResult` (allow/deny/modify)
  - `HookMatcher` (regex matcher, handler, timeout)
  - `HookEvent` types (PreToolUseEvent, PostToolUseEvent, etc.)
  - `HookEngine` class

### WS3: ReasoningConfig
- **Scope:** Unified reasoning: native (Anthropic thinking), reflection (multi-pass), prompted (CoT via prompting), none
- **Key pattern:** Stream wrapping with `PromptedReasoningParser` for prompted mode
- **New files:**
  - `vel_harness/reasoning.py` — ReasoningConfig, ReasoningDelimiters, PromptedReasoningParser
- **Files to modify:**
  - `vel_harness/config.py` — Add ReasoningConfig to DeepAgentConfig
  - `vel_harness/factory.py` — Wire reasoning modes
  - `vel_harness/harness.py` — Expose `reasoning` param
- **Files to test:**
  - `tests/test_reasoning.py`
- **API surface for TS transfer:**
  - `ReasoningConfig` (mode, budget_tokens, delimiters, etc.)
  - `ReasoningDelimiters` (xml/json/auto)
  - `PromptedReasoningParser` class
  - Stream events: `reasoning-start`, `reasoning-delta`, `reasoning-end`

### WS4: Sandbox Settings
- **Scope:** Expand SandboxConfig with excluded_commands, allowed_commands, network_allowed_hosts, etc.
- **Key pattern:** Enforcement via pre_tool_use hook (depends on WS2)
- **Files to modify:**
  - `vel_harness/config.py` — Expand SandboxConfig
- **Files to test:**
  - `tests/test_sandbox_settings.py`
- **API surface for TS transfer:**
  - Expanded `SandboxConfig` fields

### WS5: Subagent Shape Alignment
- **Scope:** Add AgentDefinition (Agent SDK-compatible) alongside existing AgentConfig
- **Key pattern:** Adapter pattern — AgentDefinition.to_agent_config()
- **Files to modify:**
  - `vel_harness/agents/config.py` — Add AgentDefinition
  - `vel_harness/agents/registry.py` — Accept both formats
  - `vel_harness/harness.py` — Accept Agent SDK-style agent dicts
- **Files to test:**
  - `tests/test_agent_definition.py`
- **API surface for TS transfer:**
  - `AgentDefinition` class
  - Model shorthand map (sonnet/opus/haiku/inherit)

### WS6: Fallback Model
- **Scope:** Automatic retry with different model on retryable errors (429, 529, 5xx)
- **New files:**
  - `vel_harness/fallback.py` — FallbackStreamWrapper
- **Files to modify:**
  - `vel_harness/config.py` — Add fallback_model, max_fallback_retries
  - `vel_harness/factory.py` — Wire fallback wrapper
- **Files to test:**
  - `tests/test_fallback.py`
- **API surface for TS transfer:**
  - `FallbackStreamWrapper` class
  - Config: `fallback_model`, `max_fallback_retries`

### WS7: Dynamic Mid-Conversation Controls
- **Scope:** HarnessSession class for interactive use with set_model, interrupt, set_reasoning
- **New files:**
  - `vel_harness/session.py` — HarnessSession
- **Files to modify:**
  - `vel_harness/harness.py` — Add create_session() factory
- **Files to test:**
  - `tests/test_session.py`
- **API surface for TS transfer:**
  - `HarnessSession` class (query, set_model, interrupt, set_reasoning)
  - `VelHarness.create_session()` factory

### WS8: File Checkpointing / Rewind
- **Scope:** Track filesystem changes, support revert to checkpoints
- **New files:**
  - `vel_harness/checkpoint.py` — FileCheckpointManager, FileChange, Checkpoint
- **Files to modify:**
  - `vel_harness/session.py` — Add rewind_files() method
  - `vel_harness/factory.py` — Wire checkpoint manager into filesystem tools
- **Files to test:**
  - `tests/test_checkpoint.py`
- **API surface for TS transfer:**
  - `FileCheckpointManager` class
  - `FileChange`, `Checkpoint` types
  - `HarnessSession.rewind_files()` method

---

## Breaking Changes

None planned. All changes are additive:
- New config fields have defaults (disabled by default)
- AgentDefinition is an addition alongside AgentConfig
- HarnessSession is a new class, VelHarness.run() unchanged
- Existing tests must continue passing

---

## Dependencies Between Workstreams

```
WS1 (middleware wiring) ← independent
WS2 (hooks) ← independent
WS3 (reasoning) ← can use hooks for lifecycle events
WS4 (sandbox) ← depends on WS2 (hooks for enforcement)
WS5 (subagents) ← independent
WS6 (fallback) ← independent
WS7 (session) ← uses WS5 (AgentDefinition._resolve_model)
WS8 (checkpoint) ← depends on WS7 (session.rewind_files)
```
