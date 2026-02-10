"""
Tokens Command

View token usage and context window statistics.
"""

from typing import Any, Dict

from valis_cli.commands.base import Command, CommandResult


def format_tokens(tokens: int) -> str:
    """Format token count for display."""
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.1f}M"
    elif tokens >= 1_000:
        return f"{tokens / 1_000:.1f}k"
    return str(tokens)


class TokensCommand(Command):
    """View token usage and context window statistics."""

    name = "tokens"
    description = "Show context window usage and compression history"
    usage = "/tokens"
    aliases = ["context", "ctx"]

    async def execute(
        self,
        args: list[str],
        context: Dict[str, Any],
    ) -> CommandResult:
        """
        Execute tokens command.

        /tokens - Show context usage breakdown
        """
        agent = context.get("agent")
        config = context.get("config")

        if agent is None:
            return CommandResult(
                success=False,
                message="Agent not initialized",
            )

        # Get VelHarness instance from AgentRunner
        harness = getattr(agent, "_agent", None)
        if harness is None:
            return CommandResult(
                success=False,
                message="Agent not initialized - run a query first",
            )

        # Get context middleware from underlying DeepAgent
        ctx_middleware = getattr(harness.deep_agent, "context", None)
        if ctx_middleware is None:
            return CommandResult(
                success=False,
                message="Context management not enabled",
            )

        # Get message history
        messages = agent.get_message_history()

        # Get API-reported usage (more accurate than estimation)
        api_usage = {}
        if hasattr(agent, "get_api_usage"):
            api_usage = agent.get_api_usage()

        # Get model name
        model = "claude-sonnet-4-5-20250929"  # default
        if config and hasattr(config, "model"):
            model = config.model.model

        # Get context stats (estimation-based)
        stats = ctx_middleware.get_context_stats(messages, model)

        # Calculate breakdown by role using middleware's estimate_tokens
        system_tokens = 0
        user_tokens = 0
        assistant_tokens = 0
        tool_call_tokens = 0
        tool_result_tokens = 0

        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                msg_tokens = ctx_middleware.estimate_tokens(content)
            else:
                msg_tokens = ctx_middleware.estimate_tokens(str(content))

            role = msg.get("role", "")
            if role == "system":
                system_tokens += msg_tokens
            elif role == "user":
                user_tokens += msg_tokens
            elif role == "assistant":
                assistant_tokens += msg_tokens
                # Count tool calls in assistant messages
                tool_calls = msg.get("tool_calls", [])
                if tool_calls:
                    tool_call_tokens += ctx_middleware.estimate_tokens(str(tool_calls))
            elif role == "tool":
                tool_result_tokens += msg_tokens

        # Prefer API-reported total if available
        current_display = stats['current_tokens']
        if api_usage.get("total_tokens", 0) > 0:
            current_display = api_usage["total_tokens"]
            usage_percent = (current_display / stats['max_tokens']) * 100
        else:
            usage_percent = stats['usage_percent']

        # Build output
        lines = [
            "Context Window Usage:",
            "",
            f"  Current:      {format_tokens(current_display)} / {format_tokens(stats['max_tokens'])} tokens",
            f"  Usage:        {usage_percent:.1f}%",
        ]

        # Show API vs estimated breakdown
        if api_usage.get("total_tokens", 0) > 0:
            lines.extend([
                "",
                "API-Reported (cumulative):",
                f"  Input:        {format_tokens(api_usage.get('prompt_tokens', 0))}",
                f"  Output:       {format_tokens(api_usage.get('completion_tokens', 0))}",
                f"  Total:        {format_tokens(api_usage.get('total_tokens', 0))}",
            ])

            # Show prompt caching stats if available
            cache_read = api_usage.get("cache_read_tokens", 0)
            cache_creation = api_usage.get("cache_creation_tokens", 0)
            if cache_read > 0 or cache_creation > 0:
                prompt_tokens = api_usage.get("prompt_tokens", 0)
                # Cache hit rate = cache_read / (cache_read + non-cached input)
                # Non-cached input = prompt_tokens - cache_read
                if prompt_tokens > 0:
                    cache_hit_rate = (cache_read / prompt_tokens) * 100
                else:
                    cache_hit_rate = 0

                lines.extend([
                    "",
                    "Prompt Caching:",
                    f"  Cache hits:   {format_tokens(cache_read)} ({cache_hit_rate:.1f}%)",
                    f"  Cache writes: {format_tokens(cache_creation)}",
                ])

                # Cost savings estimate (cache reads are 0.1x price)
                if cache_read > 0:
                    # Saved = cache_read * 0.9 (since it's 0.1x instead of 1x)
                    saved_tokens = int(cache_read * 0.9)
                    lines.append(f"  Est. savings: ~{format_tokens(saved_tokens)} tokens")
            else:
                lines.extend([
                    "",
                    "Prompt Caching:",
                    "  No cache hits yet (cache populates after first call)",
                ])

        lines.extend([
            "",
            f"Estimated by Role ({len(messages)} messages):",
            f"  System:       {format_tokens(system_tokens)}",
            f"  User:         {format_tokens(user_tokens)}",
            f"  Assistant:    {format_tokens(assistant_tokens)}",
            f"  Tool calls:   {format_tokens(tool_call_tokens)}",
            f"  Tool results: {format_tokens(tool_result_tokens)}",
            "",
            "Thresholds:",
            f"  Eviction:     {stats['eviction_threshold_percent']:.0f}%"
            + (" (will trigger)" if stats["will_evict"] else ""),
            f"  Summarize:    {stats['summarization_threshold_percent']:.0f}%"
            + (" (will trigger)" if stats["will_summarize"] else ""),
            "",
        ])

        # Compression stats
        ctxzip_enabled = stats.get("ctxzip_enabled", False)
        truncations = stats.get("truncations", 0)
        offloads = stats.get("offloads", 0)
        evictions = stats.get("evictions", 0)

        lines.append(f"Compression: {'ctx-zip enabled' if ctxzip_enabled else 'N-turn eviction'}")
        if stats['evictions_performed'] > 0:
            lines.append(f"  Truncations:  {truncations}")
            lines.append(f"  Evictions:    {evictions}")
            lines.append(f"  Offloads:     {offloads}")
        else:
            lines.append("  No compressions yet")

        # Show compression log if any
        compression_log = getattr(ctx_middleware, "_compression_log", [])
        if compression_log:
            lines.extend([
                "",
                "Recent compressions:",
            ])
            for entry in compression_log[-5:]:  # Last 5 entries
                comp_type = getattr(entry, "compression_type", "unknown")
                tool_name = getattr(entry, "tool_name", "unknown")
                original = getattr(entry, "original_tokens", 0)
                result = getattr(entry, "result_tokens", 0)
                lines.append(
                    f"  - {comp_type}: {tool_name} "
                    f"({format_tokens(original)} → {format_tokens(result)})"
                )

        return CommandResult(
            success=True,
            message="\n".join(lines),
            data=stats,
        )
