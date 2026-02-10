# Valis Harness PRD Addendum: Context Management

**Version:** 1.0  
**Date:** January 2025  
**Status:** Addendum to VALIS_HARNESS_PRD.md

---

## Overview

This addendum adds automatic context management to Valis Harness, preventing context window overflow through progressive compaction strategies. This mirrors Claude Code and DeepAgents behavior.

---

## Feature: Context Management Middleware

### 1. Problem Statement

Long-running agent sessions accumulate:
- Large tool outputs (file contents, query results, API responses)
- Redundant file contents (already persisted to filesystem)
- Historical tool calls no longer relevant

Without management, the context window fills up and performance degrades ("context rot"). Studies show LLM accuracy declines as context grows, even within technical limits.

### 2. Strategy: Progressive Compaction

Prefer reversible operations over lossy compression:

```
Priority 1: Raw (keep everything)
    ↓ when context > threshold
Priority 2: Offload large results (reversible)
    ↓ when still over threshold  
Priority 3: Compact tool calls (reversible)
    ↓ when still over threshold
Priority 4: Summarize (lossy, last resort)
```

### 3. Thresholds

| Trigger | Threshold | Action |
|---------|-----------|--------|
| Large tool result | > 20,000 tokens | Immediate offload to file |
| Tool call compaction | > 85% context window | Replace with file pointers |
| Summarization | > 95% context window | LLM summarization |

### 4. Implementation

#### 4.1 Context Manager Class

```python
# valis/middleware/context_management.py

from dataclasses import dataclass, field
from typing import Optional, Callable
from datetime import datetime
import tiktoken

@dataclass
class ContextConfig:
    """Configuration for context management"""
    
    # Thresholds (as percentage of max context)
    large_result_tokens: int = 20_000
    compaction_threshold: float = 0.85  # 85%
    summarization_threshold: float = 0.95  # 95%
    
    # Model context limits (token counts)
    model_context_limits: dict = field(default_factory=lambda: {
        "claude-sonnet-4-5-20250929": 200_000,
        "claude-opus-4-5-20251101": 200_000,
        "gpt-4o": 128_000,
        "gpt-4-turbo": 128_000,
        "gemini-1.5-pro": 1_000_000,
    })
    
    # Preview settings
    preview_lines: int = 10
    
    # Summarization model (can use cheaper model)
    summarization_model: Optional[dict] = None


@dataclass
class CompactionResult:
    """Result of a compaction operation"""
    original_tokens: int
    compacted_tokens: int
    tokens_saved: int
    strategy_used: str  # "offload", "compact", "summarize"
    files_created: list[str] = field(default_factory=list)


class ContextManagementMiddleware:
    """
    Middleware for automatic context window management.
    
    Implements progressive compaction:
    1. Offload large tool results to files
    2. Compact tool calls (replace content with file pointers)
    3. Summarize conversation (last resort)
    """
    
    def __init__(
        self,
        config: ContextConfig = None,
        filesystem_backend = None,
        tokenizer: str = "cl100k_base",
    ):
        self.config = config or ContextConfig()
        self.filesystem = filesystem_backend
        self.tokenizer = tiktoken.get_encoding(tokenizer)
        
        # Track compaction history
        self._compaction_history: list[CompactionResult] = []
        self._original_messages: list[dict] = []  # Canonical record
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        return len(self.tokenizer.encode(text))
    
    def count_message_tokens(self, messages: list[dict]) -> int:
        """Count total tokens in message list"""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.count_tokens(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        total += self.count_tokens(str(part.get("text", "")))
                        total += self.count_tokens(str(part.get("result", "")))
        return total
    
    def get_context_limit(self, model: str) -> int:
        """Get context limit for model"""
        return self.config.model_context_limits.get(model, 128_000)
    
    # =========================================================================
    # TIER 1: Large Result Offloading
    # =========================================================================
    
    def should_offload_result(self, result: str) -> bool:
        """Check if tool result should be offloaded"""
        return self.count_tokens(result) > self.config.large_result_tokens
    
    def offload_large_result(
        self,
        result: str,
        tool_name: str,
        tool_call_id: str,
    ) -> tuple[str, str]:
        """
        Offload large tool result to filesystem.
        
        Returns:
            (file_path, replacement_content)
        """
        # Generate file path
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        file_path = f"/tool_outputs/{tool_name}_{timestamp}_{tool_call_id[:8]}.txt"
        
        # Write full result to file
        self.filesystem.write_file(file_path, result)
        
        # Create preview
        lines = result.split("\n")
        preview = "\n".join(lines[:self.config.preview_lines])
        if len(lines) > self.config.preview_lines:
            preview += f"\n... ({len(lines) - self.config.preview_lines} more lines)"
        
        # Replacement content
        replacement = f"""[Large output saved to {file_path}]

Preview (first {self.config.preview_lines} lines):
{preview}

Use read_file("{file_path}") to view full content."""
        
        return file_path, replacement
    
    def process_tool_result(
        self,
        result: str,
        tool_name: str,
        tool_call_id: str,
    ) -> str:
        """
        Process tool result, offloading if necessary.
        
        Args:
            result: Raw tool result
            tool_name: Name of the tool
            tool_call_id: ID of the tool call
        
        Returns:
            Processed result (original or offloaded reference)
        """
        if self.should_offload_result(result):
            file_path, replacement = self.offload_large_result(
                result, tool_name, tool_call_id
            )
            
            self._compaction_history.append(CompactionResult(
                original_tokens=self.count_tokens(result),
                compacted_tokens=self.count_tokens(replacement),
                tokens_saved=self.count_tokens(result) - self.count_tokens(replacement),
                strategy_used="offload",
                files_created=[file_path],
            ))
            
            return replacement
        
        return result
    
    # =========================================================================
    # TIER 2: Tool Call Compaction
    # =========================================================================
    
    def compact_messages(
        self,
        messages: list[dict],
        model: str,
    ) -> list[dict]:
        """
        Compact messages by replacing file contents with pointers.
        
        Targets write_file and edit_file tool calls where content
        is already persisted to filesystem.
        """
        context_limit = self.get_context_limit(model)
        current_tokens = self.count_message_tokens(messages)
        threshold = int(context_limit * self.config.compaction_threshold)
        
        if current_tokens < threshold:
            return messages  # No compaction needed
        
        # Save original for canonical record
        self._original_messages = [dict(m) for m in messages]
        
        compacted = []
        tokens_saved = 0
        
        for msg in messages:
            if self._is_file_write_tool_call(msg):
                compacted_msg, saved = self._compact_file_write(msg)
                compacted.append(compacted_msg)
                tokens_saved += saved
            elif self._is_file_write_result(msg):
                compacted_msg, saved = self._compact_file_result(msg)
                compacted.append(compacted_msg)
                tokens_saved += saved
            else:
                compacted.append(msg)
        
        if tokens_saved > 0:
            self._compaction_history.append(CompactionResult(
                original_tokens=current_tokens,
                compacted_tokens=current_tokens - tokens_saved,
                tokens_saved=tokens_saved,
                strategy_used="compact",
            ))
        
        return compacted
    
    def _is_file_write_tool_call(self, msg: dict) -> bool:
        """Check if message is a file write tool call"""
        if msg.get("role") != "assistant":
            return False
        
        content = msg.get("content", [])
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "tool-call":
                    if part.get("toolName") in ("write_file", "edit_file"):
                        return True
        return False
    
    def _is_file_write_result(self, msg: dict) -> bool:
        """Check if message is a file write result"""
        if msg.get("role") != "tool":
            return False
        # Check metadata for tool name
        return msg.get("metadata", {}).get("tool_name") in ("write_file", "edit_file")
    
    def _compact_file_write(self, msg: dict) -> tuple[dict, int]:
        """Compact a file write tool call"""
        original_tokens = self.count_message_tokens([msg])
        
        compacted = dict(msg)
        content = compacted.get("content", [])
        
        if isinstance(content, list):
            new_content = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "tool-call":
                    tool_name = part.get("toolName")
                    args = part.get("args", {})
                    
                    if tool_name in ("write_file", "edit_file"):
                        # Replace content with pointer
                        file_path = args.get("path", "unknown")
                        new_args = dict(args)
                        
                        if "content" in new_args:
                            content_preview = new_args["content"][:100]
                            new_args["content"] = f"[Content written to {file_path}] Preview: {content_preview}..."
                        
                        if "new_text" in new_args:
                            new_args["new_text"] = f"[See {file_path} for content]"
                        
                        new_content.append({**part, "args": new_args})
                    else:
                        new_content.append(part)
                else:
                    new_content.append(part)
            
            compacted["content"] = new_content
        
        compacted_tokens = self.count_message_tokens([compacted])
        return compacted, original_tokens - compacted_tokens
    
    def _compact_file_result(self, msg: dict) -> tuple[dict, int]:
        """Compact a file write result"""
        original_tokens = self.count_message_tokens([msg])
        
        compacted = dict(msg)
        # Results from write_file are usually small ("ok"), so minimal savings
        # But edit_file might return diffs - compact those
        
        content = compacted.get("content", "")
        if isinstance(content, str) and len(content) > 500:
            compacted["content"] = "[File operation completed successfully. Use read_file() to view current content.]"
        
        compacted_tokens = self.count_message_tokens([compacted])
        return compacted, original_tokens - compacted_tokens
    
    # =========================================================================
    # TIER 3: Summarization (Last Resort)
    # =========================================================================
    
    async def summarize_conversation(
        self,
        messages: list[dict],
        model: str,
        summarization_agent = None,
    ) -> list[dict]:
        """
        Summarize conversation when compaction isn't enough.
        
        Creates structured summary and preserves original to filesystem.
        """
        context_limit = self.get_context_limit(model)
        current_tokens = self.count_message_tokens(messages)
        threshold = int(context_limit * self.config.summarization_threshold)
        
        if current_tokens < threshold:
            return messages  # No summarization needed
        
        # Save original messages to filesystem
        await self._save_conversation_to_file(messages)
        
        # Generate summary using LLM
        summary = await self._generate_summary(messages, summarization_agent)
        
        # Create summarized message list
        # Keep system message and recent messages
        summarized = []
        
        # Keep system message if present
        if messages and messages[0].get("role") == "system":
            summarized.append(messages[0])
        
        # Add summary as system context
        summarized.append({
            "role": "system",
            "content": f"""
[CONVERSATION SUMMARY]
The following is a summary of the conversation so far. The full conversation 
has been saved to /conversation_history/ and can be searched with grep().

{summary}

[END SUMMARY]
""",
        })
        
        # Keep recent messages (last ~20% of context)
        recent_token_budget = int(context_limit * 0.20)
        recent_messages = self._get_recent_messages(messages, recent_token_budget)
        summarized.extend(recent_messages)
        
        self._compaction_history.append(CompactionResult(
            original_tokens=current_tokens,
            compacted_tokens=self.count_message_tokens(summarized),
            tokens_saved=current_tokens - self.count_message_tokens(summarized),
            strategy_used="summarize",
            files_created=["/conversation_history/"],
        ))
        
        return summarized
    
    async def _save_conversation_to_file(self, messages: list[dict]) -> str:
        """Save full conversation to filesystem for recovery"""
        import json
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        file_path = f"/conversation_history/conversation_{timestamp}.json"
        
        self.filesystem.write_file(file_path, json.dumps(messages, indent=2))
        
        # Also save human-readable version
        readable_path = f"/conversation_history/conversation_{timestamp}.md"
        readable = self._messages_to_markdown(messages)
        self.filesystem.write_file(readable_path, readable)
        
        return file_path
    
    def _messages_to_markdown(self, messages: list[dict]) -> str:
        """Convert messages to human-readable markdown"""
        lines = ["# Conversation History\n"]
        
        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            
            if isinstance(content, list):
                content = "\n".join(
                    str(part.get("text", part)) for part in content
                )
            
            lines.append(f"## Message {i + 1} ({role})\n")
            lines.append(content[:2000])  # Truncate very long content
            if len(str(content)) > 2000:
                lines.append("\n[truncated...]")
            lines.append("\n")
        
        return "\n".join(lines)
    
    async def _generate_summary(
        self,
        messages: list[dict],
        summarization_agent = None,
    ) -> str:
        """Generate structured summary using LLM"""
        
        if summarization_agent is None:
            # Fallback to simple extraction
            return self._extract_summary_heuristic(messages)
        
        summary_prompt = """Summarize this conversation into a structured format:

## Session Intent
What is the user trying to accomplish?

## Progress So Far
What has been completed? What artifacts were created?

## Key Decisions
What important decisions were made?

## Current State
Where did we leave off?

## Next Steps
What remains to be done?

## Important Details
Any specific values, paths, or configurations that must be remembered.

Be concise but preserve critical information needed to continue the task."""
        
        # Convert messages to text for summarization
        conversation_text = self._messages_to_markdown(messages)
        
        response = await summarization_agent.run({
            'messages': [
                {'role': 'system', 'content': summary_prompt},
                {'role': 'user', 'content': conversation_text},
            ]
        }, stateless=True)
        
        return response
    
    def _extract_summary_heuristic(self, messages: list[dict]) -> str:
        """Fallback summary extraction without LLM"""
        
        # Extract user intents (first user message, recent user messages)
        user_messages = [m for m in messages if m.get("role") == "user"]
        intent = user_messages[0].get("content", "")[:500] if user_messages else "Unknown"
        
        # Extract tool calls made
        tools_used = set()
        files_created = set()
        
        for msg in messages:
            content = msg.get("content", [])
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "tool-call":
                            tools_used.add(part.get("toolName", "unknown"))
                            args = part.get("args", {})
                            if "path" in args:
                                files_created.add(args["path"])
        
        return f"""## Session Intent
{intent}

## Tools Used
{', '.join(tools_used) if tools_used else 'None'}

## Files Created/Modified
{chr(10).join(files_created) if files_created else 'None'}

## Note
This is an automatic summary. Full conversation saved to /conversation_history/
"""
    
    def _get_recent_messages(
        self,
        messages: list[dict],
        token_budget: int,
    ) -> list[dict]:
        """Get recent messages within token budget"""
        recent = []
        total_tokens = 0
        
        # Work backwards from end
        for msg in reversed(messages):
            msg_tokens = self.count_message_tokens([msg])
            if total_tokens + msg_tokens > token_budget:
                break
            recent.insert(0, msg)
            total_tokens += msg_tokens
        
        return recent
    
    # =========================================================================
    # Public Interface
    # =========================================================================
    
    async def manage_context(
        self,
        messages: list[dict],
        model: str,
        summarization_agent = None,
    ) -> list[dict]:
        """
        Main entry point: manage context with progressive compaction.
        
        Args:
            messages: Current message list
            model: Model name (for context limit lookup)
            summarization_agent: Optional agent for summarization
        
        Returns:
            Possibly compacted message list
        """
        context_limit = self.get_context_limit(model)
        current_tokens = self.count_message_tokens(messages)
        
        # Tier 1: Already handled at tool result time (process_tool_result)
        
        # Tier 2: Compaction
        compaction_threshold = int(context_limit * self.config.compaction_threshold)
        if current_tokens > compaction_threshold:
            messages = self.compact_messages(messages, model)
            current_tokens = self.count_message_tokens(messages)
        
        # Tier 3: Summarization
        summarization_threshold = int(context_limit * self.config.summarization_threshold)
        if current_tokens > summarization_threshold:
            messages = await self.summarize_conversation(
                messages, model, summarization_agent
            )
        
        return messages
    
    def get_compaction_stats(self) -> dict:
        """Get statistics on compaction operations"""
        total_saved = sum(r.tokens_saved for r in self._compaction_history)
        by_strategy = {}
        
        for r in self._compaction_history:
            if r.strategy_used not in by_strategy:
                by_strategy[r.strategy_used] = 0
            by_strategy[r.strategy_used] += r.tokens_saved
        
        return {
            "total_tokens_saved": total_saved,
            "compaction_events": len(self._compaction_history),
            "by_strategy": by_strategy,
        }
    
    def get_system_prompt_segment(self) -> str:
        """Return system prompt segment for context management"""
        return """
## Context Management

Your conversation history is automatically managed to stay within context limits:

1. **Large outputs** are saved to `/tool_outputs/` with a preview shown
2. **File contents** from write/edit operations are replaced with pointers
3. **If context gets very long**, a summary is created and full history saved to `/conversation_history/`

**To recover information:**
- Use `read_file("/tool_outputs/...")` to view full tool outputs
- Use `grep("keyword", "/conversation_history/")` to search past conversations
- Use `ls("/conversation_history/")` to see saved conversations

The original, uncompacted conversation is always preserved on the filesystem.
"""
```

#### 4.2 Integration with DeepAgent

```python
# valis/agent.py modifications

class DeepAgent:
    def __init__(self, config: DeepAgentConfig):
        # ... existing init ...
        
        # Context management
        self.context_manager = ContextManagementMiddleware(
            config=ContextConfig(
                large_result_tokens=config.large_result_tokens,
                compaction_threshold=config.compaction_threshold,
                summarization_threshold=config.summarization_threshold,
            ),
            filesystem_backend=self.filesystem_backend,
        )
    
    async def _execute_with_context_management(
        self,
        messages: list[dict],
        context: ExecutionContext,
    ):
        """Execute with automatic context management"""
        
        model = self.config.model.get("model", "")
        
        # Manage context before each LLM call
        messages = await self.context_manager.manage_context(
            messages,
            model,
            summarization_agent=self._get_summarization_agent(),
        )
        
        # Execute agent
        async for event in self.agent.run_stream(
            {'messages': messages},
            stateless=True,
        ):
            # Process tool results through context manager
            if event.get('type') == 'tool-result':
                result = event.get('result', '')
                tool_name = event.get('toolName', '')
                tool_call_id = event.get('toolCallId', '')
                
                processed = self.context_manager.process_tool_result(
                    str(result), tool_name, tool_call_id
                )
                event = {**event, 'result': processed}
            
            yield event
```

#### 4.3 Configuration in DeepAgentConfig

```python
@dataclass
class DeepAgentConfig:
    # ... existing fields ...
    
    # Context management
    large_result_tokens: int = 20_000
    compaction_threshold: float = 0.85
    summarization_threshold: float = 0.95
    summarization_model: Optional[dict] = None  # Cheaper model for summaries
```

### 5. Acceptance Criteria

- [ ] Large tool results (>20K tokens) automatically offloaded to files
- [ ] Preview shown with file path reference
- [ ] Tool call compaction triggers at 85% context
- [ ] File write/edit content replaced with pointers
- [ ] Summarization triggers at 95% context
- [ ] Summary includes: intent, progress, decisions, next steps
- [ ] Original messages saved to filesystem
- [ ] Recent messages preserved after summarization
- [ ] Compaction stats available
- [ ] System prompt explains recovery methods
- [ ] All operations are reversible via filesystem tools

### 6. Testing

```python
# tests/test_context_management.py

class TestContextManagement:
    def test_large_result_offload(self): ...
    def test_offload_creates_preview(self): ...
    def test_compaction_threshold(self): ...
    def test_file_write_compaction(self): ...
    def test_summarization_threshold(self): ...
    def test_summary_structure(self): ...
    def test_original_preserved(self): ...
    def test_recent_messages_kept(self): ...
    def test_recovery_via_grep(self): ...
    def test_stats_tracking(self): ...
```

---

## Files to Add/Modify

| File | Change |
|------|--------|
| `valis/middleware/context_management.py` | **NEW** - Full implementation |
| `valis/agent.py` | Add context management integration |
| `valis/config.py` | Add context config fields |
| `tests/test_context_management.py` | **NEW** - Tests |

---

**END OF ADDENDUM**
