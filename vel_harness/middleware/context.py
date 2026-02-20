"""
Context Management Middleware

Prevents context rot in long-running sessions via two-phase approach:

Phase 1 (Immediate): Truncate massive tool results as they arrive (>25K tokens)
    - Content stays in context, just shorter (head + tail preview)
    - Agent can see results NOW without re-fetch

Phase 2 (Historical): Offload old tool results after assistant processes them (>8K tokens)
    - Uses ctx-zip to move content OUT of context
    - Agent must use read tools to retrieve if needed

Additional tiers:
- Tier 2: Tool input eviction (at 85% context capacity)
- Tier 3: Conversation summarization (at 95% context capacity)
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, TYPE_CHECKING

logger = logging.getLogger(__name__)

# Optional ctx-zip-py integration
_ctxzip_available: Optional[bool] = None

if TYPE_CHECKING:
    from ctxzippy import FileStorageAdapter, CompactOptions


def _check_ctxzip_available() -> bool:
    """Check if ctxzippy is available."""
    global _ctxzip_available
    if _ctxzip_available is None:
        try:
            import ctxzippy
            _ctxzip_available = True
            logger.debug("ctxzippy available - historical offload enabled")
        except ImportError:
            _ctxzip_available = False
            logger.debug(
                "ctxzippy not installed - historical offload disabled. "
                "Install with: pip install ctxzippy"
            )
    return _ctxzip_available


# Lazy import for tiktoken (optional dependency)
_tiktoken_available: Optional[bool] = None
_tiktoken_encoder = None


def _get_tiktoken():
    """Lazily import tiktoken and cache availability."""
    global _tiktoken_available, _tiktoken_encoder
    if _tiktoken_available is None:
        try:
            import tiktoken
            _tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
            _tiktoken_available = True
            logger.debug("tiktoken available - using accurate token counting")
        except ImportError:
            _tiktoken_available = False
            logger.debug(
                "tiktoken not installed - using heuristic token counting. "
                "Install with: pip install tiktoken"
            )
        except Exception as e:
            _tiktoken_available = False
            logger.debug(
                "tiktoken unavailable (%s) - using heuristic token counting",
                e,
            )
    return _tiktoken_encoder if _tiktoken_available else None


class FilesystemBackend(Protocol):
    """Protocol for filesystem backends."""

    def write_file(self, path: str, content: str) -> Dict[str, Any]: ...
    def read_file(self, path: str, offset: int = 0, limit: int = 100) -> Dict[str, Any]: ...
    def exists(self, path: str) -> bool: ...


@dataclass
class ContextConfig:
    """Configuration for context management."""

    # Phase 1: Truncation (immediate) - content stays in context
    truncate_threshold: int = 25_000  # Truncate results > 25K tokens
    truncate_head_lines: int = 50  # Lines to show at start
    truncate_tail_lines: int = 20  # Lines to show at end

    # Phase 2: Historical offload (after assistant response) - content moves out
    history_threshold: int = 8_000  # Offload historical results > 8K tokens
    storage_path: str = "~/.vel_harness/ctx_storage"

    # Tier 2: Tool input eviction
    eviction_threshold: float = 0.85  # 85% of context window

    # Tier 3: Summarization
    summarization_threshold: float = 0.95  # 95% of context window
    preserve_recent_messages: int = 20  # Keep last N messages verbatim

    # Model context windows (can be extended)
    model_context_windows: Dict[str, int] = field(
        default_factory=lambda: {
            "claude-sonnet-4-5-20250929": 200_000,
            "claude-opus-4-5-20250901": 200_000,
            "claude-3-5-sonnet": 200_000,
            "claude-3-opus": 200_000,
            "gpt-4o": 128_000,
            "gpt-4o-mini": 128_000,
            "gpt-4-turbo": 128_000,
            "gemini-1.5-pro": 2_000_000,
            "gemini-1.5-flash": 1_000_000,
        }
    )

    # Tools excluded from compression
    tools_excluded_from_compression: set = field(
        default_factory=lambda: {
            "write_todos",
            "list_skills",
            "get_skill",
            "activate_skill",
        }
    )


@dataclass
class CompressionEvent:
    """Represents a compression event."""

    tool_name: str
    original_tokens: int
    result_tokens: int
    compression_type: str  # "truncate" | "offload"
    file_path: Optional[str] = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ContextManagementMiddleware:
    """
    Middleware that manages context window to prevent context rot.

    Two-phase approach:
    - Phase 1: Truncate current results (immediate, keeps content in context)
    - Phase 2: Offload historical results (after response, moves content out)

    Plus additional tiers for context pressure management.
    """

    def __init__(
        self,
        config: Optional[ContextConfig] = None,
        filesystem_backend: Optional[FilesystemBackend] = None,
        summarization_model: Optional[Dict[str, str]] = None,
    ):
        self.config = config or ContextConfig()
        self.filesystem = filesystem_backend
        self.summarization_model = summarization_model
        self._compression_log: List[CompressionEvent] = []
        self._session_id: str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._ctxzip_storage = None

    @property
    def compression_log(self) -> List[CompressionEvent]:
        """Get the compression log."""
        return self._compression_log.copy()

    def _get_ctxzip_storage(self):
        """Get or create ctx-zip storage adapter."""
        if self._ctxzip_storage is not None:
            return self._ctxzip_storage

        if not _check_ctxzip_available():
            return None

        try:
            from ctxzippy import FileStorageAdapter
            base_path = Path(os.path.expanduser(self.config.storage_path)).resolve()
            base_path.mkdir(parents=True, exist_ok=True)
            self._ctxzip_storage = FileStorageAdapter(base_path)
            logger.debug(f"ctx-zip storage initialized at {base_path}")
            return self._ctxzip_storage
        except Exception as e:
            logger.warning(f"Failed to initialize ctx-zip storage: {e}")
            return None

    def get_model_context_window(self, model: str) -> int:
        """Get context window size for model."""
        if model in self.config.model_context_windows:
            return self.config.model_context_windows[model]

        for key, value in self.config.model_context_windows.items():
            if model.startswith(key.rsplit("-", 1)[0]):
                return value
            if key.startswith(model.rsplit("-", 1)[0]):
                return value

        return 100_000  # Conservative default

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count using tiktoken if available, else heuristic."""
        if not text:
            return 0

        encoder = _get_tiktoken()
        if encoder is not None:
            try:
                return len(encoder.encode(text))
            except Exception:
                pass

        return self._fallback_estimate(text)

    def _fallback_estimate(self, text: str) -> int:
        """Conservative fallback when tiktoken unavailable."""
        if not text:
            return 0

        sample = text[:500]
        code_indicators = (
            sample.count('{') + sample.count('}') +
            sample.count('(') + sample.count(')') +
            sample.count(';') + sample.count(':')
        )
        is_code_heavy = code_indicators > len(sample) / 50

        if text.lstrip().startswith('{') or text.lstrip().startswith('['):
            return len(text) // 3  # JSON
        elif is_code_heavy:
            return int(len(text) / 3.5)  # Code
        else:
            return int(len(text) / 3.8)  # Prose

    def estimate_message_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Estimate total tokens in message history."""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.estimate_tokens(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        total += self.estimate_tokens(str(part))
                    elif isinstance(part, str):
                        total += self.estimate_tokens(part)

            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                total += self.estimate_tokens(str(tool_calls))

        return total

    # =========================================================================
    # Phase 1: Truncate Current Results (Immediate)
    # =========================================================================

    def process_tool_result(
        self,
        content: str,
        tool_name: str,
        tool_call_id: str,
    ) -> str:
        """
        Phase 1: Truncate massive tool results immediately.

        Content stays IN context (just truncated) - no re-fetch needed.
        Agent can see results NOW.
        """
        if tool_name in self.config.tools_excluded_from_compression:
            return content

        tokens = self.estimate_tokens(content)

        if tokens > self.config.truncate_threshold:
            return self._truncate_with_preview(content, tool_name, tokens)

        return content

    def _truncate_with_preview(
        self,
        content: str,
        tool_name: str,
        original_tokens: int,
    ) -> str:
        """Truncate content with head + tail preview."""
        lines = content.split("\n")
        total_lines = len(lines)

        head_lines = self.config.truncate_head_lines
        tail_lines = self.config.truncate_tail_lines

        if total_lines <= head_lines + tail_lines:
            return content  # Not enough to truncate

        head = lines[:head_lines]
        tail = lines[-tail_lines:]
        omitted = total_lines - head_lines - tail_lines

        truncated = "\n".join(head)
        truncated += f"\n\n[... {omitted} lines truncated ({original_tokens:,} tokens total) ...]\n\n"
        truncated += "\n".join(tail)

        result_tokens = self.estimate_tokens(truncated)

        self._compression_log.append(CompressionEvent(
            tool_name=tool_name,
            original_tokens=original_tokens,
            result_tokens=result_tokens,
            compression_type="truncate",
        ))

        logger.debug(
            f"Truncated {tool_name} result: {original_tokens:,} → {result_tokens:,} tokens"
        )

        return truncated

    # =========================================================================
    # Phase 2: Evict Historical Results (After Assistant Response)
    # =========================================================================

    async def after_assistant_response(
        self,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Phase 2: Evict old tool results after assistant processes them.

        Simple N-turn eviction: Replace tool results older than N assistant
        turns with truncated previews.
        """
        # First try simple N-turn eviction (always available)
        evicted = self._evict_old_tool_results(messages)

        # Then try ctx-zip for additional compression if available
        if _check_ctxzip_available():
            storage = self._get_ctxzip_storage()
            if storage is not None:
                try:
                    from ctxzippy import compact_messages, CompactOptions

                    options = CompactOptions(
                        storage=storage,
                        boundary="since-last-assistant-or-user-text",
                    )

                    compacted = await compact_messages(evicted, options)

                    # Log if additional compression happened
                    original_tokens = self.estimate_message_tokens(evicted)
                    result_tokens = self.estimate_message_tokens(compacted)

                    if result_tokens < original_tokens:
                        self._compression_log.append(CompressionEvent(
                            tool_name="[ctx-zip]",
                            original_tokens=original_tokens,
                            result_tokens=result_tokens,
                            compression_type="offload",
                        ))
                        logger.debug(
                            f"ctx-zip offload: {original_tokens:,} → {result_tokens:,} tokens"
                        )

                    return compacted

                except Exception as e:
                    logger.warning(f"ctx-zip historical offload failed: {e}")

        return evicted

    def _evict_old_tool_results(
        self,
        messages: List[Dict[str, Any]],
        max_age_turns: int = 3,
        preview_lines: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Simple N-turn eviction: Replace old tool results with previews.

        Args:
            messages: Message list
            max_age_turns: Keep full results for last N assistant turns
            preview_lines: Number of lines to keep in preview (head + tail)

        Returns:
            Message list with old tool results evicted to previews.
        """
        # Count assistant messages to determine "age" of each tool result
        assistant_indices = [
            i for i, msg in enumerate(messages)
            if msg.get("role") == "assistant"
        ]

        if len(assistant_indices) <= max_age_turns:
            # Not enough turns to evict anything
            return messages

        # Find the cutoff index: tool results before this are old
        cutoff_index = assistant_indices[-max_age_turns]

        evicted_messages = []
        eviction_count = 0

        for i, msg in enumerate(messages):
            if msg.get("role") == "tool" and i < cutoff_index:
                # This is an old tool result - evict to preview
                content = msg.get("content", "")
                original_tokens = self.estimate_tokens(content)

                # Only evict if it's large enough to matter
                if original_tokens > 500:  # ~2KB threshold
                    evicted_content = self._create_preview(
                        content,
                        preview_lines,
                        original_tokens,
                    )
                    evicted_messages.append({
                        **msg,
                        "content": evicted_content,
                    })
                    eviction_count += 1

                    result_tokens = self.estimate_tokens(evicted_content)
                    self._compression_log.append(CompressionEvent(
                        tool_name=msg.get("tool_call_id", "unknown")[:20],
                        original_tokens=original_tokens,
                        result_tokens=result_tokens,
                        compression_type="evict",
                    ))
                else:
                    evicted_messages.append(msg)
            else:
                evicted_messages.append(msg)

        if eviction_count > 0:
            logger.debug(f"Evicted {eviction_count} old tool results")

        return evicted_messages

    def _create_preview(
        self,
        content: str,
        preview_lines: int,
        original_tokens: int,
    ) -> str:
        """Create a head+tail preview of content."""
        lines = content.split("\n")
        total_lines = len(lines)

        if total_lines <= preview_lines * 2:
            return content  # Small enough to keep

        head_count = preview_lines
        tail_count = preview_lines
        omitted = total_lines - head_count - tail_count

        preview = "\n".join(lines[:head_count])
        preview += f"\n\n[... {omitted} lines evicted ({original_tokens:,} tokens) ...]\n\n"
        preview += "\n".join(lines[-tail_count:])

        return preview

    # =========================================================================
    # Tier 2: Tool Input Eviction
    # =========================================================================

    def should_evict_tool_inputs(
        self,
        messages: List[Dict[str, Any]],
        model: str,
    ) -> bool:
        """Check if we should evict tool inputs due to context pressure."""
        current_tokens = self.estimate_message_tokens(messages)
        max_tokens = self.get_model_context_window(model)
        return current_tokens > (max_tokens * self.config.eviction_threshold)

    def evict_tool_inputs(
        self, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Evict file content from tool calls, replacing with file paths."""
        evicted_messages = []

        for msg in messages:
            if msg.get("role") == "assistant":
                content = msg.get("content", [])
                if isinstance(content, list):
                    new_content = []
                    for part in content:
                        if (
                            isinstance(part, dict)
                            and part.get("type") == "tool-call"
                            and part.get("toolName") in ("write_file", "edit_file")
                        ):
                            args = part.get("args", {})
                            file_path = args.get("path", "unknown")
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
        messages: List[Dict[str, Any]],
        model: str,
    ) -> bool:
        """Check if we need to summarize conversation."""
        current_tokens = self.estimate_message_tokens(messages)
        max_tokens = self.get_model_context_window(model)
        return current_tokens > (max_tokens * self.config.summarization_threshold)

    async def summarize_conversation(
        self,
        messages: List[Dict[str, Any]],
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Summarize older messages, preserving recent ones."""
        session_id = session_id or self._session_id

        preserve_count = self.config.preserve_recent_messages
        if len(messages) > preserve_count:
            old_messages = messages[:-preserve_count]
            recent_messages = messages[-preserve_count:]
        else:
            return messages

        if not old_messages:
            return messages

        if self.filesystem:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            transcript_path = f"/context/transcripts/{session_id}_{timestamp}.json"
            self.filesystem.write_file(
                transcript_path,
                json.dumps(old_messages, indent=2, default=str),
            )
        else:
            transcript_path = "[filesystem not available]"

        summary = await self._generate_summary(old_messages, transcript_path)

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
        messages: List[Dict[str, Any]],
        transcript_path: str,
    ) -> str:
        """Generate structured summary of messages."""
        if self.summarization_model:
            try:
                from vel import Agent

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

                summarizer = Agent(
                    id="context-summarizer",
                    model=self.summarization_model,
                    system_prompt=summary_prompt,
                )

                content = "\n\n".join(
                    [
                        f"[{m.get('role', 'unknown')}]: {m.get('content', '')}"
                        for m in messages
                    ]
                )

                result = await summarizer.run(
                    {"message": f"Summarize this conversation:\n\n{content}"},
                    stateless=True,
                )

                if isinstance(result, dict) and "output" in result:
                    return result["output"]
                elif isinstance(result, str):
                    return result
            except Exception:
                pass

        return self._extract_summary_heuristic(messages)

    def _extract_summary_heuristic(self, messages: List[Dict[str, Any]]) -> str:
        """Simple heuristic summary when no LLM available."""
        tool_calls = []
        for msg in messages:
            content = msg.get("content", [])
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "tool-call":
                        tool_calls.append(f"- {part.get('toolName', 'unknown')}")

        user_messages = [
            msg.get("content", "")[:200]
            for msg in messages
            if msg.get("role") == "user" and isinstance(msg.get("content"), str)
        ]

        nl = "\n"
        return f"""## Tools Used
{nl.join(tool_calls[:20]) if tool_calls else "None recorded"}

## User Requests
{nl.join(f'- {m}...' for m in user_messages[:5]) if user_messages else "None recorded"}

Note: This is a heuristic summary. Full transcript contains {len(messages)} messages."""

    # =========================================================================
    # Main Processing
    # =========================================================================

    async def process_messages(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Process messages through context management tiers."""
        processed = messages

        if self.should_evict_tool_inputs(processed, model):
            processed = self.evict_tool_inputs(processed)

        if self.should_summarize(processed, model):
            processed = await self.summarize_conversation(processed, session_id)

        return processed

    def get_system_prompt_segment(self) -> str:
        """System prompt explaining context management."""
        ctxzip_note = ""
        if _check_ctxzip_available():
            ctxzip_note = f"""
- **Historical Offload**: After you process tool results, old outputs >{self.config.history_threshold // 1000}K tokens
  are moved to storage. Use read/search tools to retrieve if needed.
"""

        return f"""
## Context Management

This session has automatic context management:

- **Truncation**: Tool outputs >{self.config.truncate_threshold // 1000}K tokens are truncated with head/tail preview.
  You can see the result immediately without re-fetching.
{ctxzip_note}
- **Context Pressure**: When context fills up, older operations are compressed.

**Best Practices:**
- Write important findings to files proactively
- Use files as working memory for large content
- Reference files by path rather than copying content
"""

    def get_context_stats(self, messages: List[Dict[str, Any]], model: str) -> Dict[str, Any]:
        """Get current context usage statistics."""
        current_tokens = self.estimate_message_tokens(messages)
        max_tokens = self.get_model_context_window(model)
        usage_percent = (current_tokens / max_tokens) * 100 if max_tokens > 0 else 0

        truncations = sum(1 for e in self._compression_log if e.compression_type == "truncate")
        offloads = sum(1 for e in self._compression_log if e.compression_type == "offload")
        evictions = sum(1 for e in self._compression_log if e.compression_type == "evict")

        return {
            "current_tokens": current_tokens,
            "max_tokens": max_tokens,
            "usage_percent": round(usage_percent, 2),
            "eviction_threshold_percent": self.config.eviction_threshold * 100,
            "summarization_threshold_percent": self.config.summarization_threshold * 100,
            "will_evict": usage_percent > (self.config.eviction_threshold * 100),
            "will_summarize": usage_percent > (self.config.summarization_threshold * 100),
            "evictions_performed": len(self._compression_log),
            "ctxzip_enabled": _ctxzip_available is True,
            "truncations": truncations,
            "offloads": offloads,
            "evictions": evictions,
        }

    def get_tools(self) -> List:
        """Context management doesn't provide user-facing tools."""
        return []

    def get_state(self) -> Dict[str, Any]:
        """Get serializable state for persistence."""
        return {
            "session_id": self._session_id,
            "compression_count": len(self._compression_log),
            "compression_log": [
                {
                    "tool_name": e.tool_name,
                    "original_tokens": e.original_tokens,
                    "result_tokens": e.result_tokens,
                    "compression_type": e.compression_type,
                    "timestamp": e.timestamp,
                }
                for e in self._compression_log
            ],
        }

    def load_state(self, state: Dict[str, Any]) -> None:
        """Load state from persistence."""
        if "session_id" in state:
            self._session_id = state["session_id"]


def create_context_middleware(
    filesystem_backend: Optional[FilesystemBackend] = None,
    summarization_model: Optional[Dict[str, str]] = None,
    config: Optional[ContextConfig] = None,
) -> ContextManagementMiddleware:
    """Create context management middleware."""
    return ContextManagementMiddleware(
        config=config or ContextConfig(),
        filesystem_backend=filesystem_backend,
        summarization_model=summarization_model,
    )
