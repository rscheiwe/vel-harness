# Valis Harness PRD Addendum: DeepAgents Parity

**Version:** 1.0  
**Date:** January 2025  
**Author:** Product  
**Status:** Ready for Implementation

---

## Executive Summary

This addendum identifies gaps between the Valis Harness PRD and LangChain's DeepAgents, then specifies features to close those gaps. The most critical gap is **automatic context management**—DeepAgents implements sophisticated context compression that prevents context rot in long-running sessions.

### Gap Summary

| Feature | DeepAgents | Valis PRD | Priority |
|---------|------------|-----------|----------|
| Context Compaction | ✅ Full | ❌ Missing | **P0** |
| Long-term Memory | ✅ /memories/ path | ❌ Missing | **P0** |
| Remote Sandbox | ✅ Modal/Runloop/Daytona | ❌ Local only | P1 |
| Web Search | ✅ Tavily built-in | ❌ Not included | P1 |
| MCP Support | ✅ Via adapter | ❌ Not mentioned | P2 |
| Prompt Caching | ✅ Anthropic caching | ❌ Not mentioned | P2 |
| Tool Selector | ✅ LLM-based filtering | ❌ Not mentioned | P2 |
| Tool Retry | ✅ Configurable retry | ❌ Not mentioned | P2 |

---

## Table of Contents

1. [Feature 8: Context Management Middleware](#1-feature-8-context-management-middleware)
2. [Feature 9: Long-term Memory](#2-feature-9-long-term-memory)
3. [Feature 10: Remote Sandbox Support](#3-feature-10-remote-sandbox-support)
4. [Feature 11: Web Search Integration](#4-feature-11-web-search-integration)
5. [Feature 12: Additional Middleware](#5-feature-12-additional-middleware)
6. [Updated Implementation Order](#6-updated-implementation-order)
7. [Skills System Enhancements](#7-skills-system-enhancements)

---

## 1. Feature 8: Context Management Middleware

### 1.1 Overview

Context management prevents "context rot"—the degradation of LLM performance as context windows fill up. DeepAgents implements a three-tier compression strategy:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Context Management Tiers                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Tier 1: Large Result Offloading                                │
│  ─────────────────────────────                                  │
│  Trigger: Tool result > 20,000 tokens                           │
│  Action: Write to file, replace with path + 10-line preview     │
│  Reversibility: ✅ Full (agent can re-read file)                │
│                                                                  │
│  Tier 2: Tool Input Eviction                                    │
│  ────────────────────────────                                   │
│  Trigger: Context > 85% of model window                         │
│  Action: Replace file write/edit tool calls with file pointers  │
│  Reversibility: ✅ Full (content exists on disk)                │
│                                                                  │
│  Tier 3: Conversation Summarization                             │
│  ─────────────────────────────────                              │
│  Trigger: Tiers 1-2 insufficient                                │
│  Action: LLM summarizes history, saves original to transcript   │
│  Reversibility: ⚠️ Partial (can grep transcript)               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Implementation

```python
# valis/middleware/context.py

from dataclasses import dataclass, field
from typing import Optional, Callable
from datetime import datetime
import json


@dataclass
class ContextConfig:
    """Configuration for context management"""
    
    # Tier 1: Large result offloading
    tool_result_token_limit: int = 20_000
    preview_lines: int = 10
    
    # Tier 2: Tool input eviction
    eviction_threshold: float = 0.85  # 85% of context window
    
    # Tier 3: Summarization
    summarization_threshold: float = 0.95  # 95% of context window
    preserve_recent_messages: int = 20  # Keep last N messages verbatim
    
    # Model context windows (can be extended)
    model_context_windows: dict = field(default_factory=lambda: {
        "claude-sonnet-4-5-20250929": 200_000,
        "claude-opus-4-5-20250901": 200_000,
        "gpt-4o": 128_000,
        "gpt-4o-mini": 128_000,
        "gemini-1.5-pro": 2_000_000,
    })
    
    # Tools excluded from eviction (their outputs are not file-based)
    tools_excluded_from_eviction: set = field(default_factory=lambda: {
        "write_todos",
        "list_skills",
    })


@dataclass
class EvictedContent:
    """Represents content that was evicted to filesystem"""
    original_content: str
    file_path: str
    preview: str
    token_count: int
    eviction_reason: str  # "large_result" | "context_pressure"
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class ContextManagementMiddleware:
    """
    Middleware that manages context window to prevent context rot.
    
    Implements three-tier compression:
    1. Large tool result offloading (immediate)
    2. Tool input eviction (at 85% capacity)
    3. Conversation summarization (at 95% capacity)
    """
    
    def __init__(
        self,
        config: Optional[ContextConfig] = None,
        filesystem_backend = None,
        summarization_model: Optional[dict] = None,
    ):
        self.config = config or ContextConfig()
        self.filesystem = filesystem_backend
        self.summarization_model = summarization_model
        self._eviction_log: list[EvictedContent] = []
    
    def get_model_context_window(self, model: str) -> int:
        """Get context window size for model"""
        # Try exact match first
        if model in self.config.model_context_windows:
            return self.config.model_context_windows[model]
        
        # Try prefix match (e.g., "claude-sonnet" matches "claude-sonnet-4-...")
        for key, value in self.config.model_context_windows.items():
            if model.startswith(key.rsplit("-", 1)[0]):
                return value
        
        # Conservative default
        return 100_000
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count (rough: 4 chars per token)"""
        return len(text) // 4
    
    def estimate_message_tokens(self, messages: list[dict]) -> int:
        """Estimate total tokens in message history"""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.estimate_tokens(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        total += self.estimate_tokens(str(part))
        return total
    
    # =========================================================================
    # Tier 1: Large Result Offloading
    # =========================================================================
    
    def should_offload_result(self, content: str, tool_name: str) -> bool:
        """Check if tool result should be offloaded"""
        if tool_name in self.config.tools_excluded_from_eviction:
            return False
        return self.estimate_tokens(content) > self.config.tool_result_token_limit
    
    def offload_large_result(
        self,
        content: str,
        tool_name: str,
        tool_call_id: str,
    ) -> str:
        """
        Offload large tool result to filesystem.
        
        Returns replacement content with file path and preview.
        """
        # Generate file path
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        file_path = f"/context/tool_results/{tool_name}_{timestamp}_{tool_call_id[:8]}.txt"
        
        # Write to filesystem
        self.filesystem.write_file(file_path, content)
        
        # Generate preview (first N lines)
        lines = content.split("\n")
        preview_lines = lines[:self.config.preview_lines]
        preview = "\n".join(preview_lines)
        if len(lines) > self.config.preview_lines:
            preview += f"\n\n... [{len(lines) - self.config.preview_lines} more lines]"
        
        # Log eviction
        self._eviction_log.append(EvictedContent(
            original_content=content,
            file_path=file_path,
            preview=preview,
            token_count=self.estimate_tokens(content),
            eviction_reason="large_result",
        ))
        
        # Return replacement
        return f"""[Tool result saved to {file_path}]

Preview (first {self.config.preview_lines} lines):
{preview}

Use read_file("{file_path}") to see full content."""
    
    # =========================================================================
    # Tier 2: Tool Input Eviction
    # =========================================================================
    
    def should_evict_tool_inputs(
        self,
        messages: list[dict],
        model: str,
    ) -> bool:
        """Check if we should evict tool inputs due to context pressure"""
        current_tokens = self.estimate_message_tokens(messages)
        max_tokens = self.get_model_context_window(model)
        return current_tokens > (max_tokens * self.config.eviction_threshold)
    
    def evict_tool_inputs(self, messages: list[dict]) -> list[dict]:
        """
        Evict file content from tool calls, replacing with file paths.
        
        Only evicts write_file and edit_file tool calls where content
        is already persisted to filesystem.
        """
        evicted_messages = []
        
        for msg in messages:
            if msg.get("role") == "assistant":
                content = msg.get("content", [])
                if isinstance(content, list):
                    new_content = []
                    for part in content:
                        if (isinstance(part, dict) and 
                            part.get("type") == "tool-call" and
                            part.get("toolName") in ("write_file", "edit_file")):
                            
                            # Extract file path from args
                            args = part.get("args", {})
                            file_path = args.get("path", "unknown")
                            
                            # Replace with pointer
                            evicted_part = {
                                **part,
                                "args": {
                                    "path": file_path,
                                    "_evicted": True,
                                    "_note": f"Content written to {file_path}",
                                },
                            }
                            new_content.append(evicted_part)
                        else:
                            new_content.append(part)
                    
                    evicted_messages.append({**msg, "content": new_content})
                else:
                    evicted_messages.append(msg)
            else:
                evicted_messages.append(msg)
        
        return evicted_messages
    
    # =========================================================================
    # Tier 3: Conversation Summarization
    # =========================================================================
    
    def should_summarize(
        self,
        messages: list[dict],
        model: str,
    ) -> bool:
        """Check if we need to summarize conversation"""
        current_tokens = self.estimate_message_tokens(messages)
        max_tokens = self.get_model_context_window(model)
        return current_tokens > (max_tokens * self.config.summarization_threshold)
    
    async def summarize_conversation(
        self,
        messages: list[dict],
        session_id: str,
    ) -> list[dict]:
        """
        Summarize older messages, preserving recent ones.
        
        1. Save full transcript to filesystem
        2. Generate structured summary via LLM
        3. Return summary + recent messages
        """
        # Split messages
        preserve_count = self.config.preserve_recent_messages
        old_messages = messages[:-preserve_count] if len(messages) > preserve_count else []
        recent_messages = messages[-preserve_count:] if len(messages) > preserve_count else messages
        
        if not old_messages:
            return messages  # Nothing to summarize
        
        # Save full transcript
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        transcript_path = f"/context/transcripts/{session_id}_{timestamp}.json"
        self.filesystem.write_file(
            transcript_path,
            json.dumps(old_messages, indent=2),
        )
        
        # Generate summary
        summary = await self._generate_summary(old_messages, transcript_path)
        
        # Build new message list
        summary_message = {
            "role": "system",
            "content": f"""[Conversation Summary]

The earlier part of this conversation has been summarized to manage context.
Full transcript saved to: {transcript_path}

{summary}

[End of Summary - Recent messages follow]""",
        }
        
        return [summary_message] + recent_messages
    
    async def _generate_summary(
        self,
        messages: list[dict],
        transcript_path: str,
    ) -> str:
        """Generate structured summary of messages"""
        
        # Build summary prompt
        summary_prompt = """Summarize this conversation segment. Include:

## Session Intent
What is the user trying to accomplish?

## Progress Made
- Key actions taken
- Files created/modified
- Decisions made

## Current State
- Where we are in the workflow
- Any pending items

## Next Steps
- What remains to be done

## Key Details to Preserve
- Specific values, names, or configurations mentioned
- Any constraints or requirements stated

Be concise but preserve critical details needed to continue the work."""

        # If we have a summarization model, use it
        if self.summarization_model:
            from vel import Agent
            
            summarizer = Agent(
                id="context-summarizer",
                model=self.summarization_model,
                system_prompt=summary_prompt,
            )
            
            # Format messages for summarization
            content = "\n\n".join([
                f"[{m.get('role', 'unknown')}]: {m.get('content', '')}"
                for m in messages
            ])
            
            summary = await summarizer.run({
                "message": f"Summarize this conversation:\n\n{content}"
            }, stateless=True)
            
            return summary
        
        # Fallback: Simple extraction (no LLM)
        return self._extract_summary_heuristic(messages)
    
    def _extract_summary_heuristic(self, messages: list[dict]) -> str:
        """Simple heuristic summary when no LLM available"""
        # Extract tool calls
        tool_calls = []
        for msg in messages:
            content = msg.get("content", [])
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "tool-call":
                        tool_calls.append(f"- {part.get('toolName', 'unknown')}")
        
        # Extract user messages
        user_messages = [
            msg.get("content", "")[:200]
            for msg in messages
            if msg.get("role") == "user" and isinstance(msg.get("content"), str)
        ]
        
        return f"""## Tools Used
{chr(10).join(tool_calls[:20]) if tool_calls else "None recorded"}

## User Requests
{chr(10).join(f'- {m}...' for m in user_messages[:5]) if user_messages else "None recorded"}

Note: This is a heuristic summary. Use grep on {len(messages)} messages in transcript for details."""
    
    # =========================================================================
    # Main Processing
    # =========================================================================
    
    async def process_messages(
        self,
        messages: list[dict],
        model: str,
        session_id: str,
    ) -> list[dict]:
        """
        Process messages through context management tiers.
        
        Called before each LLM invocation.
        """
        processed = messages
        
        # Tier 2: Evict tool inputs if needed
        if self.should_evict_tool_inputs(processed, model):
            processed = self.evict_tool_inputs(processed)
        
        # Tier 3: Summarize if still too large
        if self.should_summarize(processed, model):
            processed = await self.summarize_conversation(processed, session_id)
        
        return processed
    
    def process_tool_result(
        self,
        content: str,
        tool_name: str,
        tool_call_id: str,
    ) -> str:
        """
        Process tool result through Tier 1 offloading.
        
        Called after each tool execution.
        """
        # Tier 1: Offload large results
        if self.should_offload_result(content, tool_name):
            return self.offload_large_result(content, tool_name, tool_call_id)
        
        return content
    
    def get_system_prompt_segment(self) -> str:
        """System prompt explaining context management"""
        return """
## Context Management

This session has automatic context management enabled:

1. **Large Results**: Tool outputs over ~20K tokens are saved to /context/tool_results/
   and replaced with a preview. Use read_file() to access full content.

2. **Context Pressure**: When context fills up, older file write/edit operations
   are compressed to file path references.

3. **Summarization**: If needed, older conversation is summarized and the full
   transcript saved to /context/transcripts/.

**Best Practices:**
- Write important findings to files proactively
- Use files as your working memory for large content
- Reference files by path rather than copying content into messages
"""


# Factory function
def create_context_middleware(
    filesystem_backend,
    summarization_model: Optional[dict] = None,
    config: Optional[ContextConfig] = None,
) -> ContextManagementMiddleware:
    """
    Create context management middleware.
    
    Args:
        filesystem_backend: Backend for file operations
        summarization_model: Model config for summarization (optional)
        config: Context management configuration
    
    Returns:
        Configured ContextManagementMiddleware
    """
    return ContextManagementMiddleware(
        config=config or ContextConfig(),
        filesystem_backend=filesystem_backend,
        summarization_model=summarization_model,
    )
```

### 1.3 Integration with DeepAgent

```python
# valis/agent.py modifications

class DeepAgent:
    def __init__(self, config: DeepAgentConfig):
        # ... existing init ...
        
        # Add context management
        self.context_manager = ContextManagementMiddleware(
            config=ContextConfig(
                tool_result_token_limit=config.tool_result_token_limit,
                eviction_threshold=config.eviction_threshold,
                summarization_threshold=config.summarization_threshold,
            ),
            filesystem_backend=self.filesystem_backend,
            summarization_model=config.summarization_model,
        )
    
    async def _execute_with_context_management(
        self,
        messages: list[dict],
        model: str,
        session_id: str,
    ):
        """Execute with context management applied"""
        
        # Process messages through context tiers
        processed_messages = await self.context_manager.process_messages(
            messages, model, session_id
        )
        
        # Execute agent
        async for event in self.agent.run_stream(
            {"messages": processed_messages},
            stateless=True,
        ):
            # Process tool results through Tier 1
            if event.get("type") == "tool-result":
                content = event.get("result", "")
                tool_name = event.get("toolName", "")
                tool_call_id = event.get("toolCallId", "")
                
                processed_content = self.context_manager.process_tool_result(
                    content, tool_name, tool_call_id
                )
                
                yield {**event, "result": processed_content}
            else:
                yield event
```

### 1.4 DeepAgentConfig Additions

```python
@dataclass
class DeepAgentConfig:
    # ... existing fields ...
    
    # Context management
    tool_result_token_limit: int = 20_000
    eviction_threshold: float = 0.85
    summarization_threshold: float = 0.95
    summarization_model: Optional[dict] = None  # Uses main model if None
```

### 1.5 Acceptance Criteria

- [ ] Tool results > 20K tokens offloaded to file with preview
- [ ] File write/edit tool calls evicted at 85% context
- [ ] Conversation summarized at 95% context
- [ ] Full transcript preserved to filesystem
- [ ] Summary includes session intent, progress, next steps
- [ ] Configurable thresholds
- [ ] Model context window detection

---

## 2. Feature 9: Long-term Memory

### 2.1 Overview

Long-term memory enables information to persist across sessions via a special `/memories/` path that routes to persistent storage.

### 2.2 Implementation

```python
# valis/backends/composite.py

from typing import Protocol, Optional
from dataclasses import dataclass


class StorageBackend(Protocol):
    """Protocol for storage backends"""
    def read(self, path: str) -> Optional[str]: ...
    def write(self, path: str, content: str) -> None: ...
    def delete(self, path: str) -> bool: ...
    def list(self, path: str) -> list[str]: ...
    def exists(self, path: str) -> bool: ...


@dataclass
class RouteConfig:
    """Configuration for a storage route"""
    prefix: str
    backend: StorageBackend
    description: str = ""


class CompositeBackend:
    """
    Routes file operations to different backends based on path prefix.
    
    Enables mixing ephemeral (in-memory/sandbox) storage with persistent
    storage for specific paths like /memories/.
    """
    
    def __init__(
        self,
        default: StorageBackend,
        routes: dict[str, StorageBackend] = None,
    ):
        """
        Args:
            default: Backend for paths not matching any route
            routes: Map of path prefix → backend
        """
        self.default = default
        self.routes = routes or {}
    
    def _get_backend(self, path: str) -> tuple[StorageBackend, str]:
        """Get backend and adjusted path for a given path"""
        for prefix, backend in sorted(
            self.routes.items(),
            key=lambda x: len(x[0]),
            reverse=True,  # Longest prefix first
        ):
            if path.startswith(prefix):
                return backend, path
        return self.default, path
    
    def read(self, path: str) -> Optional[str]:
        backend, adjusted_path = self._get_backend(path)
        return backend.read(adjusted_path)
    
    def write(self, path: str, content: str) -> None:
        backend, adjusted_path = self._get_backend(path)
        backend.write(adjusted_path, content)
    
    def delete(self, path: str) -> bool:
        backend, adjusted_path = self._get_backend(path)
        return backend.delete(adjusted_path)
    
    def list(self, path: str) -> list[str]:
        backend, adjusted_path = self._get_backend(path)
        return backend.list(adjusted_path)
    
    def exists(self, path: str) -> bool:
        backend, adjusted_path = self._get_backend(path)
        return backend.exists(adjusted_path)


class PersistentStoreBackend:
    """
    Backend that persists to disk or database.
    
    Used for /memories/ path to survive across sessions.
    """
    
    def __init__(
        self,
        base_path: str,  # e.g., ~/.valis/memories/
        agent_id: str = "default",
    ):
        import os
        self.base_path = os.path.expanduser(base_path)
        self.agent_id = agent_id
        self.root = os.path.join(self.base_path, agent_id)
        os.makedirs(self.root, exist_ok=True)
    
    def _resolve_path(self, path: str) -> str:
        """Resolve virtual path to filesystem path"""
        import os
        # Strip /memories/ prefix if present
        if path.startswith("/memories/"):
            path = path[len("/memories/"):]
        return os.path.join(self.root, path.lstrip("/"))
    
    def read(self, path: str) -> Optional[str]:
        import os
        fs_path = self._resolve_path(path)
        if os.path.exists(fs_path):
            with open(fs_path, "r") as f:
                return f.read()
        return None
    
    def write(self, path: str, content: str) -> None:
        import os
        fs_path = self._resolve_path(path)
        os.makedirs(os.path.dirname(fs_path), exist_ok=True)
        with open(fs_path, "w") as f:
            f.write(content)
    
    def delete(self, path: str) -> bool:
        import os
        fs_path = self._resolve_path(path)
        if os.path.exists(fs_path):
            os.remove(fs_path)
            return True
        return False
    
    def list(self, path: str) -> list[str]:
        import os
        fs_path = self._resolve_path(path)
        if os.path.isdir(fs_path):
            return os.listdir(fs_path)
        return []
    
    def exists(self, path: str) -> bool:
        import os
        return os.path.exists(self._resolve_path(path))
```

### 2.3 Memory-First Protocol

```python
# valis/middleware/memory.py

class MemoryMiddleware:
    """
    Middleware that implements memory-first protocol.
    
    - Loads AGENTS.md at startup
    - Instructs agent to check /memories/ before responding
    - Saves learnings to /memories/ automatically
    """
    
    def __init__(
        self,
        memories_path: str = "/memories/",
        agents_md_path: str = "/memories/AGENTS.md",
    ):
        self.memories_path = memories_path
        self.agents_md_path = agents_md_path
    
    def get_startup_context(self, filesystem_backend) -> str:
        """Load AGENTS.md if it exists"""
        content = filesystem_backend.read(self.agents_md_path)
        if content:
            return f"<agent_memory>\n{content}\n</agent_memory>"
        return ""
    
    def get_system_prompt_segment(self) -> str:
        return f"""
## Long-term Memory

You have persistent memory in `{self.memories_path}`:

**Memory-First Protocol:**
1. **Before research**: Check {self.memories_path} for relevant prior knowledge
2. **During work**: Reference memory files when uncertain
3. **After learning**: Save new information to {self.memories_path}

**Memory Organization:**
- `{self.agents_md_path}` - Your core knowledge (always loaded)
- `{self.memories_path}api-conventions.md` - API patterns
- `{self.memories_path}project-notes.md` - Project-specific info
- Organize by topic with descriptive filenames

**When to save to memory:**
- User teaches you something they want remembered
- You discover project-specific patterns
- Important decisions are made

Files in {self.memories_path} persist across sessions.
"""
```

### 2.4 Acceptance Criteria

- [ ] `/memories/` path routes to persistent storage
- [ ] Other paths use ephemeral storage
- [ ] AGENTS.md loaded at startup
- [ ] Memory-first protocol in system prompt
- [ ] Memories survive across sessions
- [ ] Agent-specific memory directories

---

## 3. Feature 10: Remote Sandbox Support

### 3.1 Overview

Support cloud-based sandboxes (Modal, Runloop, Daytona) in addition to local sandboxes for safety and scalability.

### 3.2 Implementation

```python
# valis/backends/sandbox_remote.py

from typing import Optional, Protocol
from dataclasses import dataclass
from abc import ABC, abstractmethod


class RemoteSandbox(ABC):
    """Abstract base for remote sandbox providers"""
    
    @abstractmethod
    async def execute(self, command: str, timeout: int = 30) -> dict: ...
    
    @abstractmethod
    async def read_file(self, path: str) -> str: ...
    
    @abstractmethod
    async def write_file(self, path: str, content: str) -> None: ...
    
    @abstractmethod
    async def cleanup(self) -> None: ...


@dataclass
class SandboxConfig:
    """Configuration for remote sandbox"""
    provider: str  # "modal" | "runloop" | "daytona"
    api_key: Optional[str] = None
    sandbox_id: Optional[str] = None  # Reuse existing sandbox
    setup_script: Optional[str] = None  # Path to setup.sh
    timeout: int = 300  # 5 min default


class ModalSandbox(RemoteSandbox):
    """Modal.com sandbox integration"""
    
    def __init__(self, config: SandboxConfig):
        self.config = config
        self._sandbox = None
    
    async def _ensure_sandbox(self):
        """Create or connect to sandbox"""
        if self._sandbox is None:
            import modal
            
            if self.config.sandbox_id:
                # Reuse existing
                self._sandbox = modal.Sandbox.from_id(self.config.sandbox_id)
            else:
                # Create new
                self._sandbox = modal.Sandbox.create(
                    image=modal.Image.debian_slim().pip_install("python3"),
                    timeout=self.config.timeout,
                )
                
                # Run setup script if provided
                if self.config.setup_script:
                    with open(self.config.setup_script) as f:
                        await self._sandbox.exec("bash", "-c", f.read())
    
    async def execute(self, command: str, timeout: int = 30) -> dict:
        await self._ensure_sandbox()
        result = await self._sandbox.exec("bash", "-c", command)
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "success": result.returncode == 0,
        }
    
    async def read_file(self, path: str) -> str:
        result = await self.execute(f"cat {path}")
        return result["stdout"]
    
    async def write_file(self, path: str, content: str) -> None:
        # Use heredoc to handle special characters
        await self.execute(f"cat << 'EOF' > {path}\n{content}\nEOF")
    
    async def cleanup(self) -> None:
        if self._sandbox:
            await self._sandbox.terminate()


class RunloopSandbox(RemoteSandbox):
    """Runloop sandbox integration"""
    
    def __init__(self, config: SandboxConfig):
        self.config = config
        self._client = None
        self._devbox = None
    
    async def _ensure_sandbox(self):
        if self._client is None:
            from runloop import Runloop
            self._client = Runloop(api_key=self.config.api_key)
            
            if self.config.sandbox_id:
                self._devbox = self._client.devboxes.get(self.config.sandbox_id)
            else:
                self._devbox = self._client.devboxes.create()
                
                if self.config.setup_script:
                    with open(self.config.setup_script) as f:
                        await self._devbox.run_command(f.read())
    
    async def execute(self, command: str, timeout: int = 30) -> dict:
        await self._ensure_sandbox()
        result = await self._devbox.run_command(command)
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "success": result.exit_code == 0,
        }
    
    # ... similar file operations ...
    
    async def cleanup(self) -> None:
        if self._devbox:
            await self._devbox.shutdown()


def create_sandbox(config: SandboxConfig) -> RemoteSandbox:
    """Factory for creating remote sandboxes"""
    if config.provider == "modal":
        return ModalSandbox(config)
    elif config.provider == "runloop":
        return RunloopSandbox(config)
    elif config.provider == "daytona":
        return DaytonaSandbox(config)
    else:
        raise ValueError(f"Unknown sandbox provider: {config.provider}")
```

### 3.3 Acceptance Criteria

- [ ] Modal sandbox integration
- [ ] Runloop sandbox integration
- [ ] Daytona sandbox integration
- [ ] Sandbox reuse via ID
- [ ] Setup script execution
- [ ] Automatic cleanup

---

## 4. Feature 11: Web Search Integration

### 4.1 Overview

Built-in web search tool using Tavily API.

### 4.2 Implementation

```python
# valis/tools/web_search.py

from vel import ToolSpec
from typing import Literal, Optional
import os


def create_web_search_tool(
    api_key: Optional[str] = None,
) -> ToolSpec:
    """Create web search tool using Tavily"""
    
    api_key = api_key or os.environ.get("TAVILY_API_KEY")
    
    if not api_key:
        raise ValueError(
            "Tavily API key required. Set TAVILY_API_KEY env var or pass api_key."
        )
    
    from tavily import TavilyClient
    client = TavilyClient(api_key=api_key)
    
    def web_search(
        query: str,
        max_results: int = 5,
        topic: Literal["general", "news", "finance"] = "general",
        include_raw_content: bool = False,
    ) -> dict:
        """
        Search the web for current information.
        
        Args:
            query: Search query
            max_results: Maximum number of results (1-10)
            topic: Search topic category
            include_raw_content: Include full page content
        
        Returns:
            Search results with titles, URLs, and snippets
        """
        results = client.search(
            query,
            max_results=min(max_results, 10),
            topic=topic,
            include_raw_content=include_raw_content,
        )
        
        return {
            "query": query,
            "results": [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", ""),
                    "raw_content": r.get("raw_content") if include_raw_content else None,
                }
                for r in results.get("results", [])
            ],
        }
    
    return ToolSpec.from_function(
        web_search,
        name="web_search",
        description="""
        Search the web for current information.
        
        Use for:
        - Finding recent news and events
        - Looking up current facts
        - Researching topics
        - Verifying information
        """,
        category="research",
        tags=["web", "search", "research"],
    )
```

### 4.3 Acceptance Criteria

- [ ] Tavily integration works
- [ ] Configurable max results
- [ ] Topic filtering (general/news/finance)
- [ ] Raw content option
- [ ] API key from env or explicit

---

## 5. Feature 12: Additional Middleware

### 5.1 Anthropic Prompt Caching

```python
# valis/middleware/caching.py

class AnthropicPromptCachingMiddleware:
    """
    Cache system prompts for Anthropic models.
    
    Reduces latency and cost for repeated prompts.
    """
    
    def __init__(self, ttl_seconds: int = 300):  # 5 min default
        self.ttl = ttl_seconds
    
    def wrap_system_prompt(self, prompt: str, model: str) -> dict:
        """Wrap prompt with cache control for Anthropic"""
        if "claude" not in model.lower():
            return {"content": prompt}
        
        return {
            "content": prompt,
            "cache_control": {"type": "ephemeral"},
        }
```

### 5.2 LLM Tool Selector

```python
# valis/middleware/tool_selector.py

class LLMToolSelectorMiddleware:
    """
    Use LLM to select relevant tools before main call.
    
    Reduces token usage when many tools available.
    """
    
    def __init__(
        self,
        model: dict,
        max_tools: int = 10,
        always_include: list[str] = None,
    ):
        self.model = model
        self.max_tools = max_tools
        self.always_include = always_include or []
    
    async def select_tools(
        self,
        query: str,
        available_tools: list[ToolSpec],
    ) -> list[ToolSpec]:
        """Select most relevant tools for query"""
        # Always include specified tools
        selected = [
            t for t in available_tools
            if t.name in self.always_include
        ]
        
        # LLM selects from remaining
        remaining = [
            t for t in available_tools
            if t.name not in self.always_include
        ]
        
        if len(remaining) <= self.max_tools - len(selected):
            return available_tools
        
        # ... LLM selection logic ...
        
        return selected + llm_selected[:self.max_tools - len(selected)]
```

### 5.3 Tool Retry

```python
# valis/middleware/retry.py

class ToolRetryMiddleware:
    """
    Automatically retry failed tool calls.
    """
    
    def __init__(
        self,
        max_retries: int = 2,
        retry_on: tuple = (Exception,),
        backoff: float = 1.0,
    ):
        self.max_retries = max_retries
        self.retry_on = retry_on
        self.backoff = backoff
    
    async def execute_with_retry(
        self,
        tool: ToolSpec,
        args: dict,
    ) -> dict:
        """Execute tool with retry logic"""
        last_error = None
        
        for attempt in range(self.max_retries + 1):
            try:
                return await tool.handler(**args)
            except self.retry_on as e:
                last_error = e
                if attempt < self.max_retries:
                    await asyncio.sleep(self.backoff * (attempt + 1))
        
        raise last_error
```

---

## 6. Updated Implementation Order

### Original PRD (Weeks 1-5)

| Week | Feature |
|------|---------|
| 1 | Filesystem + Planning middleware |
| 2 | Sandbox + Database backends |
| 3 | Skills system + Subagents |
| 4 | Deep agent factory + Integration |
| 5 | CLI + Polish |

### Addendum Features (Weeks 6-7)

| Week | Feature | Priority |
|------|---------|----------|
| 6 | Context Management Middleware | P0 |
| 6 | Long-term Memory (/memories/) | P0 |
| 7 | Remote Sandbox Support | P1 |
| 7 | Web Search Integration | P1 |
| 7 | Additional Middleware (caching, retry) | P2 |

### Dependency Graph

```
Week 1-2: Filesystem ────────────────────────┐
                                             │
Week 6: Context Management ◄─────────────────┤
                                             │
Week 6: Long-term Memory ◄───────────────────┤ (needs filesystem)
                                             │
Week 2: Local Sandbox ───────────────────────┤
                                             │
Week 7: Remote Sandbox ◄─────────────────────┘ (extends sandbox)

Week 7: Web Search (independent)

Week 7: Additional Middleware (independent)
```

---

## 7. Skills System Enhancements

### 7.1 Progressive Disclosure

The original PRD has skills but should add:

```python
# Enhancement to SkillsMiddleware

class SkillsMiddleware:
    def __init__(self, ...):
        # ... existing ...
        
        # Progressive disclosure: load only frontmatter at startup
        self.skill_metadata: dict[str, dict] = {}  # name → {description, tags}
        self.skill_content: dict[str, str] = {}    # name → full content (loaded on demand)
    
    def _scan_skills(self):
        """Scan directories and load only metadata"""
        for skill_path in self._find_skill_files():
            metadata = self._parse_frontmatter(skill_path)
            self.skill_metadata[metadata["name"]] = {
                "description": metadata.get("description", ""),
                "tags": metadata.get("tags", []),
                "path": skill_path,
            }
            # Don't load full content yet
    
    def load_skill(self, name: str) -> str:
        """Load full skill content on demand"""
        if name not in self.skill_content:
            path = self.skill_metadata[name]["path"]
            self.skill_content[name] = self._read_skill_file(path)
        return self.skill_content[name]
    
    def get_system_prompt_segment(self) -> str:
        """Include only skill names/descriptions, not full content"""
        skill_list = "\n".join([
            f"- **{name}**: {meta['description']}"
            for name, meta in self.skill_metadata.items()
        ])
        return f"""
## Available Skills

{skill_list}

Use `load_skill(name)` to load detailed instructions when needed.
"""
```

### 7.2 Project-Specific Skills

```python
# Skill directory hierarchy
SKILL_SEARCH_PATHS = [
    "~/.valis/{agent_name}/skills/",      # Global agent skills
    ".valis/skills/",                       # Project-specific skills
]
```

---

## Summary: Full Feature List

### Core PRD (Original)
1. ✅ Planning Middleware (write_todos)
2. ✅ Filesystem Middleware (ls, read, write, edit, glob, grep)
3. ✅ Local Sandbox Backend (bubblewrap/Seatbelt)
4. ✅ Skills System
5. ✅ Database Backend
6. ✅ Subagent System
7. ✅ Deep Agent Factory

### Addendum (This Document)
8. ⬜ Context Management Middleware (P0)
9. ⬜ Long-term Memory (P0)
10. ⬜ Remote Sandbox Support (P1)
11. ⬜ Web Search Integration (P1)
12. ⬜ Additional Middleware (P2)

### DeepAgents Parity Status

| Feature | DeepAgents | Valis (with addendum) |
|---------|------------|----------------------|
| Planning | ✅ | ✅ |
| Filesystem | ✅ | ✅ |
| Local Sandbox | ✅ | ✅ |
| Remote Sandbox | ✅ | ✅ (addendum) |
| Subagents | ✅ | ✅ |
| Skills | ✅ | ✅ |
| Context Management | ✅ | ✅ (addendum) |
| Long-term Memory | ✅ | ✅ (addendum) |
| Web Search | ✅ | ✅ (addendum) |
| HITL | ✅ | ✅ |
| MCP Support | ✅ | ⬜ (future) |
| CLI | ✅ | ⬜ (out of scope) |

---

**END OF ADDENDUM**

*Implement addendum features after core PRD is complete.*
