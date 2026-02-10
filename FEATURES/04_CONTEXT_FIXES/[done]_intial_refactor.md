# Token Efficiency Fixes for Vel Harness

## Problem Summary

Reading 833 lines + generating a summary cost **599.7k cumulative tokens**.  
Expected: ~50-80k.  
**We're at ~10x overhead.**

---

## Root Causes

| Issue | Current Behavior | Impact |
|-------|------------------|--------|
| Chunked reads | SKILL.md read 3x (100 lines per call) | 3 API calls instead of 1 |
| Sequential tool calls | 9 files = 9+ API round trips | Each carries full context |
| No prompt caching | 20k system prompt re-sent every call | 20k × 15 calls = 300k |
| No eviction | Tool results accumulate forever | Context bloats over conversation |

---

## Fix 1: Increase Read Chunk Size

**File**: `vel_harness/tools/filesystem.py` (or wherever `read_file` is defined)

**Current**: Default chunk size is ~100 lines

**Change**: Increase default to full file or ~500 lines

```python
def read_file(
    path: str,
    offset: int = 0,
    limit: int = 2000,  # Was 100, now 2000 lines
) -> str:
    ...
```

**Alternatively**, if the tool has a token/char limit:

```python
DEFAULT_READ_LIMIT = 50_000  # ~12k tokens, enough for most files
```

---

## Fix 2: Enable Prompt Caching

**File**: `vel_harness/agent.py` or wherever API calls are made

**Add cache_control to system prompt**:

```python
def build_messages(self):
    return [
        {
            "role": "system",
            "content": self.system_prompt,
            "cache_control": {"type": "ephemeral"}  # ADD THIS
        },
        *self.conversation_history
    ]
```

**Expected savings**: System prompt (20k) charged once per session, not per call. At 15 calls, saves ~280k tokens.

---

## Fix 3: Implement Tool Result Eviction

**File**: `vel_harness/middleware/context.py`

**After each assistant response**, compress old tool results:

```python
class ContextManagementMiddleware:
    def __init__(
        self,
        tool_result_max_age: int = 3,  # Keep last N turns of full results
        evicted_preview_lines: int = 10,
    ):
        self.tool_result_max_age = tool_result_max_age
        self.evicted_preview_lines = evicted_preview_lines
    
    def after_assistant_response(self, messages: list) -> list:
        """Evict old tool results to previews."""
        assistant_count = sum(1 for m in messages if m["role"] == "assistant")
        
        for i, msg in enumerate(messages):
            if msg["role"] != "tool":
                continue
            
            # Count assistant messages after this tool result
            assistants_after = sum(
                1 for m in messages[i:] if m["role"] == "assistant"
            )
            
            # If old enough, replace with preview
            if assistants_after >= self.tool_result_max_age:
                messages[i] = self._evict_to_preview(msg)
        
        return messages
    
    def _evict_to_preview(self, tool_msg: dict) -> dict:
        """Replace tool result with truncated preview."""
        content = tool_msg["content"]
        lines = content.split("\n")
        
        if len(lines) <= self.evicted_preview_lines * 2:
            return tool_msg  # Small enough to keep
        
        preview = "\n".join(
            lines[:self.evicted_preview_lines] +
            [f"\n[... {len(lines) - self.evicted_preview_lines * 2} lines evicted ...]\n"] +
            lines[-self.evicted_preview_lines:]
        )
        
        return {
            **tool_msg,
            "content": preview,
        }
```

---

## Fix 4: Batch File Reads (Parallel Tool Calls)

**File**: `vel_harness/prompts/tools/filesystem.py`

**Add guidance to batch reads**:

```python
FILESYSTEM_PROMPT_ADDITION = """
## Efficient File Reading

When you need to read multiple files:
- Use glob or ls first to identify files
- Read files in a single tool call batch when possible
- Prefer reading entire files over chunked reads unless file is very large (>1000 lines)

Bad (5 API round trips):
  read_file("a.py")
  read_file("b.py")
  read_file("c.py")
  read_file("d.py")
  read_file("e.py")

Good (1 API round trip with parallel tool use):
  [read_file("a.py"), read_file("b.py"), read_file("c.py"), read_file("d.py"), read_file("e.py")]
"""
```

**Also ensure Vel supports parallel tool calls** in the API request/response handling.

---

## Fix 5: Fix /tokens Display

**File**: `valis_cli/commands/tokens.py`

**Separate current context from cumulative**:

```python
def cmd_tokens(context):
    # Current context (overflow risk)
    current = {
        "system": count_tokens(context.system_prompt),
        "user": sum(count_tokens(m["content"]) for m in context.messages if m["role"] == "user"),
        "assistant": sum(count_tokens(m["content"]) for m in context.messages if m["role"] == "assistant"),
        "tool_calls": sum(count_tokens(str(m.get("tool_calls", ""))) for m in context.messages),
        "tool_results": sum(count_tokens(m["content"]) for m in context.messages if m["role"] == "tool"),
    }
    current_total = sum(current.values())
    
    # Cumulative (cost tracking)
    cumulative = context.api_token_totals  # Track this across all API calls
    
    print("Context Window (current turn):")
    print(f"  System:        {current['system']:,}")
    print(f"  User:          {current['user']:,}")
    print(f"  Assistant:     {current['assistant']:,}")
    print(f"  Tool calls:    {current['tool_calls']:,}")
    print(f"  Tool results:  {current['tool_results']:,}")
    print(f"  ─────────────────────")
    print(f"  Current:       {current_total:,} / {context.model_limit:,}")
    print(f"  Usage:         {current_total / context.model_limit * 100:.1f}%")
    print()
    print("Session Totals (cumulative):")
    print(f"  Input tokens:  {cumulative['input']:,}")
    print(f"  Output tokens: {cumulative['output']:,}")
    print(f"  API calls:     {cumulative['calls']}")
    
    # Warn if caching not working
    if cumulative['input'] > current['system'] * cumulative['calls'] * 0.5:
        print()
        print("⚠️  High cumulative input suggests prompt caching may not be active")
```

---

## Fix 6: Track and Report Caching Effectiveness

**File**: `vel_harness/agent.py`

**Track cache hits from API response**:

```python
def process_api_response(self, response):
    # Anthropic returns cache info in usage
    usage = response.get("usage", {})
    
    self.stats["input_tokens"] += usage.get("input_tokens", 0)
    self.stats["output_tokens"] += usage.get("output_tokens", 0)
    self.stats["cache_read_tokens"] += usage.get("cache_read_input_tokens", 0)
    self.stats["cache_create_tokens"] += usage.get("cache_creation_input_tokens", 0)
    self.stats["api_calls"] += 1
```

**Show in /tokens**:

```python
print("Prompt Caching:")
print(f"  Cache hits:    {stats['cache_read_tokens']:,} tokens")
print(f"  Cache misses:  {stats['cache_create_tokens']:,} tokens")
print(f"  Hit rate:      {cache_hit_rate:.1f}%")
```

---

## Implementation Order

| Priority | Fix | Effort | Impact |
|----------|-----|--------|--------|
| 1 | Fix 2: Prompt caching | Low | High — biggest immediate win |
| 2 | Fix 1: Read chunk size | Low | Medium — fewer API calls |
| 3 | Fix 5: /tokens display | Low | Visibility — see what's happening |
| 4 | Fix 6: Cache tracking | Low | Verify caching works |
| 5 | Fix 3: Tool result eviction | Medium | High — prevents context bloat |
| 6 | Fix 4: Parallel tool calls | Medium | Medium — may need API layer changes |

---

## Expected Results

| Metric | Before | After |
|--------|--------|-------|
| Cumulative tokens (same task) | 599.7k | ~60-80k |
| Cost (rough) | ~$1.80 | ~$0.20 |
| API calls for 9 files | 15+ | 5-7 |
| System prompt overhead | 300k+ | ~25k |

---

## Validation

After implementing, run the same task (read files + summarize) and compare:

```
# Before
Session Totals:
  Input tokens:  589,000
  API calls:     15+

# After (target)
Session Totals:
  Input tokens:  ~50,000
  API calls:     5-7
  Cache hit rate: 80%+
```

If cumulative tokens drops 5-10x, fixes are working.