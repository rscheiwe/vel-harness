"""
Valis CLI Application

Main Textual TUI application.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.events import Paste
from textual.message import Message as TextualMessage
from textual.reactive import reactive
from textual.widgets import Footer, Header, Static
from textual.worker import Worker, WorkerState

from valis_cli.agent import AgentRunner, AgentEvent, EventType, create_cli_agent
from valis_cli.commands import CommandResult, get_registry
from valis_cli.config import Config, get_config
from valis_cli.widgets.approval import ApprovalDialog, ApprovalResult
from valis_cli.widgets.chat import ChatDisplay, Message, MessageRole
from valis_cli.widgets.input import ChatInput


class AgentEventMessage(TextualMessage):
    """Message to pass agent events to the UI."""

    def __init__(self, event: AgentEvent) -> None:
        self.event = event
        super().__init__()


class AgentDoneMessage(TextualMessage):
    """Message indicating agent has finished."""

    def __init__(self, error: Optional[str] = None) -> None:
        self.error = error
        super().__init__()


def format_duration(seconds: float) -> str:
    """Format duration as human-readable string."""
    if seconds < 60:
        return f"{int(seconds)}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}m {secs}s"


def format_tokens(count: int) -> str:
    """Format token count with K suffix for thousands."""
    if count >= 1000:
        return f"{count / 1000:.1f}k"
    return str(count)


class StatusBar(Static):
    """Status bar showing current state with animated spinner, elapsed time, and token usage."""

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 1;
        background: $surface-darken-2;
        color: $text-muted;
        padding: 0 2;
    }

    StatusBar .processing {
        color: $warning;
    }

    StatusBar .hint {
        color: $text-muted;
    }

    StatusBar .tokens {
        color: $accent;
    }

    StatusBar .context-normal {
        color: $success;
    }

    StatusBar .context-warning {
        color: $warning;
    }

    StatusBar .context-critical {
        color: $error;
    }
    """

    status = reactive("Ready", init=False)
    model = reactive("", init=False)
    is_processing = reactive(False, init=False)
    elapsed_seconds = reactive(0.0, init=False)
    total_tokens = reactive(0, init=False)
    # Context window tracking
    context_tokens = reactive(0, init=False)
    context_max = reactive(200_000, init=False)
    context_percent = reactive(0.0, init=False)

    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._spinner_frame = 0
        self._timer = None
        self._start_time: Optional[float] = None

    def on_mount(self) -> None:
        """Update display on mount."""
        self._update_display()

    def start_processing(self) -> None:
        """Start processing mode with timer and spinner."""
        self._start_time = time.time()
        self.elapsed_seconds = 0.0
        self.is_processing = True
        self._spinner_frame = 0
        # Start timer for updates
        self._timer = self.set_interval(0.1, self._tick)
        self._update_display()

    def stop_processing(self) -> None:
        """Stop processing mode."""
        if self._timer:
            self._timer.stop()
            self._timer = None
        self.is_processing = False
        self._start_time = None
        self._update_display()

    def add_tokens(self, count: int) -> None:
        """Add to token count."""
        self.total_tokens += count

    def reset_tokens(self) -> None:
        """Reset token count."""
        self.total_tokens = 0

    def update_context_stats(self, current: int, max_tokens: int) -> None:
        """Update context window stats."""
        self.context_tokens = current
        self.context_max = max_tokens
        self.context_percent = (current / max_tokens * 100) if max_tokens > 0 else 0
        if self.is_mounted:
            self._update_display()

    def _get_context_style(self) -> str:
        """Get the style for context display based on usage."""
        if self.context_percent >= 95:
            return "bold red"  # Critical - summarization imminent
        elif self.context_percent >= 85:
            return "yellow"  # Warning - eviction threshold
        elif self.context_percent >= 70:
            return "cyan"  # Approaching limits
        return "green"  # Normal

    def _tick(self) -> None:
        """Timer tick - update spinner and elapsed time."""
        self._spinner_frame = (self._spinner_frame + 1) % len(self.SPINNER_FRAMES)
        if self._start_time:
            self.elapsed_seconds = time.time() - self._start_time
        self._update_display()

    def _update_display(self) -> None:
        """Update the status bar display."""
        # Build context display string
        ctx_display = ""
        if self.context_tokens > 0 or self.context_max > 0:
            ctx_style = self._get_context_style()
            ctx_display = f"[{ctx_style}]{format_tokens(self.context_tokens)}/{format_tokens(self.context_max)} ({self.context_percent:.0f}%)[/]"

        if self.is_processing:
            # Processing mode: spinner + status + (esc hint) + elapsed + context
            spinner = self.SPINNER_FRAMES[self._spinner_frame]
            elapsed = format_duration(self.elapsed_seconds)

            parts = [f"{spinner} {self.status}"]
            hint_parts = [f"esc to interrupt", elapsed]

            if ctx_display:
                hint_parts.append(ctx_display)
            elif self.total_tokens > 0:
                hint_parts.append(f"↑ {format_tokens(self.total_tokens)}")

            parts.append(f"({' · '.join(hint_parts)})")
            self.update("  ".join(parts))
        else:
            # Ready mode: model + context + help
            parts = []
            if self.model:
                parts.append(f"⚡ {self.model}")

            # Show context usage if available
            if ctx_display:
                parts.append(ctx_display)
            elif self.total_tokens > 0:
                parts.append(f"↑ {format_tokens(self.total_tokens)} tokens")

            parts.append("ctrl+c: quit | /help: commands")
            self.update("  ".join(parts))

    def watch_status(self, status: str) -> None:
        if self.is_mounted:
            self._update_display()

    def watch_model(self, model: str) -> None:
        if self.is_mounted:
            self._update_display()

    def watch_is_processing(self, processing: bool) -> None:
        if self.is_mounted:
            self._update_display()

    def watch_total_tokens(self, tokens: int) -> None:
        if self.is_mounted and self.is_processing:
            self._update_display()


class TurnEnvelope(Static):
    """Turn progress indicator showing agent is working."""

    DEFAULT_CSS = """
    TurnEnvelope {
        height: 0;
        padding: 0 2;
        background: $surface-darken-1;
    }

    TurnEnvelope.active {
        height: 1;
    }
    """

    # Shimmer colors (base → bright → base)
    BASE_COLOR = (64, 180, 180)      # Muted teal
    SHIMMER_COLOR = (100, 255, 255)  # Bright cyan
    SHIMMER_SPREAD = 0.2             # Width of bright region

    def __init__(self, verb: str = "Harnessing", **kwargs):
        super().__init__(**kwargs)
        self.verb = verb
        self._start_time: Optional[float] = None
        self._tokens_in = 0
        self._tokens_out = 0
        self._shimmer_position = 0.0  # 0.0 to 1.0
        self._timer = None
        self._active = False

    def start(self) -> None:
        """Start the turn envelope."""
        self._start_time = time.time()
        self._tokens_in = 0
        self._tokens_out = 0
        self._shimmer_frame = 0
        self._active = True
        self.add_class("active")
        self.styles.height = 1  # Force height via styles too
        self._update_display()
        self._timer = self.set_interval(0.05, self._tick)  # ~20fps for smooth shimmer

    def stop(self) -> None:
        """Stop the turn envelope."""
        if self._timer:
            self._timer.stop()
            self._timer = None
        self._start_time = None
        self._active = False
        self.remove_class("active")
        self.styles.height = 0  # Force height via styles too
        self.update("")

    def update_tokens(self, input_tokens: int, output_tokens: int) -> None:
        """Update token counts."""
        self._tokens_in += input_tokens
        self._tokens_out += output_tokens
        if self._active:
            self._update_display()

    def set_tokens(self, input_tokens: int, output_tokens: int) -> None:
        """Set token counts directly."""
        self._tokens_in = input_tokens
        self._tokens_out = output_tokens
        if self._active:
            self._update_display()

    def _tick(self) -> None:
        """Timer tick for shimmer animation."""
        # Move shimmer position
        self._shimmer_position = (self._shimmer_position + 0.03) % 1.0
        if self._active:
            self._update_display()

    def _shimmer_text(self, text: str) -> str:
        """Apply shimmer effect to text, returning Rich markup."""
        import math
        result = []
        length = len(text)

        for i, char in enumerate(text):
            # Normalize character position to 0-1
            char_pos = i / max(length - 1, 1)

            # Distance from shimmer center
            shimmer_center = self._shimmer_position * (1 + self.SHIMMER_SPREAD * 2) - self.SHIMMER_SPREAD
            distance = abs(char_pos - shimmer_center)

            # Calculate intensity (1.0 at center, 0.0 outside spread)
            if distance < self.SHIMMER_SPREAD:
                intensity = (1 + math.cos(math.pi * distance / self.SHIMMER_SPREAD)) / 2
            else:
                intensity = 0.0

            # Blend colors
            r = int(self.BASE_COLOR[0] + (self.SHIMMER_COLOR[0] - self.BASE_COLOR[0]) * intensity)
            g = int(self.BASE_COLOR[1] + (self.SHIMMER_COLOR[1] - self.BASE_COLOR[1]) * intensity)
            b = int(self.BASE_COLOR[2] + (self.SHIMMER_COLOR[2] - self.BASE_COLOR[2]) * intensity)

            result.append(f"[rgb({r},{g},{b}) bold]{char}[/]")

        return "".join(result)

    def _update_display(self) -> None:
        """Update the display."""
        if self._start_time is None or not self._active:
            return

        elapsed = int(time.time() - self._start_time)

        # Format tokens
        total_tokens = self._tokens_in + self._tokens_out
        if total_tokens >= 1000:
            tokens_str = f"{total_tokens / 1000:.1f}k"
        else:
            tokens_str = str(total_tokens)

        # Apply shimmer to verb
        shimmered_verb = self._shimmer_text(f"{self.verb}…")

        self.update(
            f"{shimmered_verb} "
            f"[dim](esc to interrupt · {elapsed}s · ↓ {tokens_str} tokens)[/]"
        )


class WelcomeBanner(Static):
    """Welcome banner shown at startup."""

    DEFAULT_CSS = """
    WelcomeBanner {
        padding: 1 2;
        margin: 1;
        text-align: center;
        border: round $primary-darken-2;
    }

    WelcomeBanner .ascii-art {
        color: $primary;
        text-align: center;
    }

    WelcomeBanner .info {
        color: $text-muted;
        text-align: center;
        margin-top: 1;
    }
    """

    # ASCII art for VALIS
    ASCII_VALIS = """
[bold]██╗   ██╗ █████╗ ██╗     ██╗███████╗[/]
[bold]██║   ██║██╔══██╗██║     ██║██╔════╝[/]
[bold]██║   ██║███████║██║     ██║███████╗[/]
[bold]╚██╗ ██╔╝██╔══██║██║     ██║╚════██║[/]
[bold] ╚████╔╝ ██║  ██║███████╗██║███████║[/]
[bold]  ╚═══╝  ╚═╝  ╚═╝╚══════╝╚═╝╚══════╝[/]
"""

    def __init__(self, model: str = "", tier: str = "", cwd: str = "", **kwargs):
        super().__init__(**kwargs)
        self.model = model
        self.tier = tier
        self.cwd = cwd

    def compose(self) -> ComposeResult:
        yield Static(self.ASCII_VALIS, classes="ascii-art")
        info_lines = []
        if self.model:
            info_lines.append(f"[bold]{self.model}[/]")
        if self.tier:
            info_lines.append(self.tier)
        if self.cwd:
            info_lines.append(f"[dim]{self.cwd}[/]")
        if info_lines:
            yield Static("\n".join(info_lines), classes="info")


class ValisCLI(App):
    """Main Valis CLI application."""

    TITLE = "Valis CLI"

    CSS = """
    Screen {
        layout: vertical;
    }

    /* Disable focus highlight on chat display (prevents lightening on click) */
    #chat-display:focus {
        tint: transparent;
    }

    #main-container {
        height: 1fr;
        min-height: 10;
    }

    ChatDisplay {
        height: 1fr;
        min-height: 5;
    }

    #input-area {
        dock: bottom;
        height: auto;
    }

    ChatInput {
        margin-bottom: 1;
    }

    StatusBar {
        dock: bottom;
        height: 1;
        background: $surface-darken-1;
        color: $text-muted;
        padding: 0 2;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+l", "clear", "Clear"),
        Binding("ctrl+r", "reset", "Reset"),
        Binding("ctrl+shift+c", "copy_last", "Copy last response", show=False),
        Binding("ctrl+s", "toggle_select_mode", "Toggle select mode", show=False),
        Binding("escape", "interrupt", "Interrupt", show=False),
    ]

    ENABLE_COMMAND_PALETTE = False

    def __init__(
        self,
        config: Optional[Config] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.config = config or get_config()
        self.agent: Optional[AgentRunner] = None
        self._processing = False
        self._cancel_requested = False
        self._select_mode = False  # Track current mode
        self._current_task: Optional[asyncio.Task] = None
        self._streaming_widget = None
        self._pending_user_input: str = ""

    def compose(self) -> ComposeResult:
        """Compose the application."""
        yield Header(show_clock=False)
        with Container(id="main-container"):
            yield ChatDisplay(
                compact=self.config.compact_mode,
                show_tool_calls=self.config.show_tool_calls,
                id="chat-display",
            )
        # Input area with envelope above it
        with Vertical(id="input-area"):
            yield TurnEnvelope(verb="Harnessing", id="turn-envelope")
            yield ChatInput(id="chat-input")
        yield StatusBar(id="status-bar")

    async def on_mount(self) -> None:
        """Handle mount event."""
        # Initialize agent
        self.agent = create_cli_agent(config=self.config)

        # Update status bar
        status_bar = self.query_one("#status-bar", StatusBar)
        model_str = f"{self.config.model.provider}/{self.config.model.model}"
        status_bar.model = model_str

        # Build welcome banner (centered)
        import os
        cwd = os.getcwd()
        home = os.path.expanduser("~")
        if cwd.startswith(home):
            cwd = "~" + cwd[len(home):]

        # ASCII art lines - will be centered
        ascii_lines = [
            "[#40E0D0 bold]██╗   ██╗ █████╗ ██╗     ██╗███████╗[/]",
            "[#40E0D0 bold]██║   ██║██╔══██╗██║     ██║██╔════╝[/]",
            "[#40E0D0 bold]██║   ██║███████║██║     ██║███████╗[/]",
            "[#40E0D0 bold]╚██╗ ██╔╝██╔══██║██║     ██║╚════██║[/]",
            "[#40E0D0 bold] ╚████╔╝ ██║  ██║███████╗██║███████║[/]",
            "[#40E0D0 bold]  ╚═══╝  ╚═╝  ╚═╝╚══════╝╚═╝╚══════╝[/]",
        ]

        # Get terminal width for centering (approximate)
        try:
            import shutil
            term_width = shutil.get_terminal_size().columns - 10  # Account for margins
        except Exception:
            term_width = 80

        # Center each line
        def center_line(line: str, width: int) -> str:
            # Strip markup to get visible length
            import re
            visible = re.sub(r'\[.*?\]', '', line)
            padding = max(0, (width - len(visible)) // 2)
            return " " * padding + line

        centered_ascii = "\n".join(center_line(line, term_width) for line in ascii_lines)
        centered_model = center_line(f"[bold]{model_str}[/]", term_width)
        centered_cwd = center_line(f"[dim]{cwd}[/]", term_width)
        centered_help = center_line("[dim]Type a message to chat, or /help for commands[/]", term_width)

        welcome_content = f"""{centered_ascii}

{centered_model}
{centered_cwd}

{centered_help}"""

        # Show welcome banner
        chat = self.query_one("#chat-display", ChatDisplay)
        chat.add_message(Message(
            role=MessageRole.SYSTEM,
            content=welcome_content,
        ))

        # Focus input
        self.query_one("#chat-input", ChatInput).focus_input()

    def on_paste(self, event: Paste) -> None:
        """Debug: Log paste events at app level."""
        with open("/tmp/valis_paste_debug.log", "a") as f:
            f.write(f"[APP PASTE] text={event.text[:100]}...\n")

    async def on_chat_input_submitted(self, event: ChatInput.Submitted) -> None:
        """Handle user message submission."""
        if self._processing:
            return

        user_input = event.value.strip()
        images = event.images

        # Allow submission with just images (no text required)
        if not user_input and not images:
            return

        await self._process_message(user_input, images=images)

    async def on_chat_input_slash_command(
        self,
        event: ChatInput.SlashCommand,
    ) -> None:
        """Handle slash command."""
        await self._execute_command(event.command, event.args)

    async def _process_message(
        self,
        user_input: str,
        images: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Process a user message with optional images."""
        if self.agent is None:
            return

        self._processing = True
        self._cancel_requested = False
        self._streaming_widget = None
        chat = self.query_one("#chat-display", ChatDisplay)
        input_widget = self.query_one("#chat-input", ChatInput)
        status_bar = self.query_one("#status-bar", StatusBar)

        # Disable input while processing
        input_widget.disable()

        # Start turn envelope
        turn_envelope = self.query_one("#turn-envelope", TurnEnvelope)
        turn_envelope.start()

        # Add user message to display (with image indicator if present)
        display_text = user_input
        if images:
            image_count = len(images)
            prefix = f"[{image_count} image{'s' if image_count > 1 else ''}] "
            display_text = prefix + (user_input or "(no text)")
        chat.add_user_message(display_text)

        # Show loading indicator
        chat.show_loading()

        # Run agent in a threaded worker so UI stays responsive
        self._pending_user_input = user_input
        self._pending_images = images
        self.run_worker(
            self._run_agent_worker,
            name="agent_worker",
            exclusive=True,
            thread=True,
        )

    def _run_agent_worker(self) -> None:
        """Worker function that runs the agent in a thread and posts events."""
        import asyncio

        user_input = self._pending_user_input
        images = getattr(self, '_pending_images', None)

        async def run_agent():
            try:
                async for event in self.agent.run(user_input, images=images):
                    if self._cancel_requested:
                        self.call_from_thread(self.post_message, AgentDoneMessage(error="Interrupted by user"))
                        return
                    self.call_from_thread(self.post_message, AgentEventMessage(event))
                self.call_from_thread(self.post_message, AgentDoneMessage())
            except Exception as e:
                self.call_from_thread(self.post_message, AgentDoneMessage(error=str(e)))

        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_agent())
        finally:
            loop.close()

    def on_agent_event_message(self, message: AgentEventMessage) -> None:
        """Handle agent event from worker."""
        event = message.event
        chat = self.query_one("#chat-display", ChatDisplay)
        status_bar = self.query_one("#status-bar", StatusBar)

        if event.type == EventType.TEXT_DELTA:
            delta = event.data.get("delta", "")
            # Create streaming widget on first text (or after tool call)
            if self._streaming_widget is None:
                self._streaming_widget = chat.start_streaming()
            self._streaming_widget.append(delta)

        elif event.type == EventType.TOOL_CALL:
            # End any active streaming BEFORE showing tool call
            if self._streaming_widget is not None:
                chat.end_streaming()
                self._streaming_widget = None

            # Hide loading when tool call arrives
            chat.hide_loading()
            tool_id = event.data.get("id", "")
            tool_name = event.data.get("name", "unknown")
            tool_args = event.data.get("args", {})

            if event.data.get("denied"):
                chat.add_message(Message(
                    role=MessageRole.ERROR,
                    content=f"Tool {tool_name} denied by permissions",
                ))
            else:
                # Add tool call as pending (running) with shimmer animation
                chat.add_tool_call(
                    name=tool_name,
                    args=tool_args,
                    tool_call_id=tool_id,
                    pending=True,
                )

        elif event.type == EventType.TOOL_RESULT:
            # Mark the tool call as completed with result
            tool_id = event.data.get("id", "")
            result = event.data.get("result")
            if tool_id:
                chat.mark_tool_completed(tool_id, result)

        elif event.type == EventType.APPROVAL_REQUIRED:
            if self._streaming_widget is not None:
                chat.end_streaming()
                self._streaming_widget = None

            chat.hide_loading()
            tool_id = event.data.get("id", "")
            tool_name = event.data.get("name", "unknown")
            tool_args = event.data.get("args", {})

            # Add tool call as pending (running) with shimmer animation
            chat.add_tool_call(
                name=tool_name,
                args=tool_args,
                tool_call_id=tool_id,
                pending=True,
            )

        elif event.type == EventType.RESPONSE_METADATA:
            usage = event.data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total = usage.get("total_tokens", 0)
            if total > 0:
                status_bar.add_tokens(total)
                # Update turn envelope with cumulative tokens
                turn_envelope = self.query_one("#turn-envelope", TurnEnvelope)
                turn_envelope.update_tokens(prompt_tokens, completion_tokens)

        elif event.type == EventType.ERROR:
            error = event.data.get("error", "Unknown error")
            chat.add_error(error)

    def on_agent_done_message(self, message: AgentDoneMessage) -> None:
        """Handle agent completion from worker."""
        chat = self.query_one("#chat-display", ChatDisplay)
        status_bar = self.query_one("#status-bar", StatusBar)
        input_widget = self.query_one("#chat-input", ChatInput)

        if message.error:
            if message.error == "Interrupted by user":
                chat.add_message(Message(
                    role=MessageRole.SYSTEM,
                    content="Interrupted by user",
                ))
            else:
                chat.add_error(message.error)

        # Hide loading if still showing
        chat.hide_loading()

        # End streaming if active
        if self._streaming_widget is not None:
            chat.end_streaming()
            self._streaming_widget = None

        # Update context display
        self._update_context_display()

        # Stop turn envelope
        turn_envelope = self.query_one("#turn-envelope", TurnEnvelope)
        turn_envelope.stop()

        # Re-enable input
        input_widget.enable()
        input_widget.focus_input()
        self._processing = False
        self._cancel_requested = False

    def _update_context_display(self) -> None:
        """Update status bar with current context usage."""
        if self.agent is None:
            return

        # Get VelHarness instance from AgentRunner
        harness = getattr(self.agent, "_agent", None)
        if harness is None:
            return

        # Get context middleware from underlying DeepAgent
        ctx_middleware = getattr(harness.deep_agent, "context", None)
        if ctx_middleware is None:
            return

        # Get message history
        messages = self.agent.get_message_history()

        # Get model name
        model = self.config.model.model if self.config else "claude-sonnet-4-5-20250929"

        # Get context stats
        try:
            stats = ctx_middleware.get_context_stats(messages, model)

            # Prefer API-reported usage if available
            current_tokens = stats["current_tokens"]
            if hasattr(self.agent, "get_api_usage"):
                api_usage = self.agent.get_api_usage()
                if api_usage.get("total_tokens", 0) > 0:
                    current_tokens = api_usage["total_tokens"]

            status_bar = self.query_one("#status-bar", StatusBar)
            status_bar.update_context_stats(
                current_tokens,
                stats["max_tokens"],
            )
        except Exception:
            pass  # Silently fail if stats unavailable

    async def _show_approval_dialog(
        self,
        tool_id: str,
        tool_name: str,
        tool_args: Dict[str, Any],
    ) -> Optional[ApprovalResult]:
        """Show tool approval dialog."""
        dialog = ApprovalDialog(
            tool_id=tool_id,
            tool_name=tool_name,
            tool_args=tool_args,
        )
        result = await self.push_screen_wait(dialog)
        return result

    async def _execute_command(
        self,
        command: str,
        args: list[str],
    ) -> None:
        """Execute a slash command."""
        registry = get_registry()
        cmd = registry.get(command)
        chat = self.query_one("#chat-display", ChatDisplay)

        if cmd is None:
            chat.add_message(Message(
                role=MessageRole.ERROR,
                content=f"Unknown command: /{command}",
            ))
            return

        # Build context
        context = {
            "agent": self.agent,
            "config": self.config,
            "app": self,
        }

        try:
            result = await cmd.execute(args, context)

            if result.message:
                chat.add_message(Message(
                    role=MessageRole.SYSTEM,
                    content=result.message,
                ))

            # Handle special actions
            if result.data.get("action") == "clear":
                chat.clear()

            if result.should_exit:
                self.exit()

        except Exception as e:
            chat.add_error(f"Command error: {e}")

    def action_quit(self) -> None:
        """Quit the application."""
        self.exit()

    def action_clear(self) -> None:
        """Clear the chat display."""
        chat = self.query_one("#chat-display", ChatDisplay)
        chat.clear()

    def action_reset(self) -> None:
        """Reset the session."""
        if self.agent:
            self.agent.reset_session()
        chat = self.query_one("#chat-display", ChatDisplay)
        chat.clear()
        chat.add_message(Message(
            role=MessageRole.SYSTEM,
            content="Session reset. Starting fresh conversation.",
        ))

    async def action_help(self) -> None:
        """Show help."""
        await self._execute_command("help", [])

    def action_interrupt(self) -> None:
        """Interrupt the current processing."""
        if self._processing:
            self._cancel_requested = True
        else:
            # If not processing, focus input
            self.query_one("#chat-input", ChatInput).focus_input()

    def action_focus_input(self) -> None:
        """Focus the input field."""
        self.query_one("#chat-input", ChatInput).focus_input()

    def action_copy_last(self) -> None:
        """Copy the last assistant response to clipboard."""
        chat = self.query_one("#chat-display", ChatDisplay)
        content = chat.get_last_assistant_message()
        if content:
            # Try Textual's built-in clipboard (OSC 52 - works on most terminals)
            self.copy_to_clipboard(content)
            self.notify("Copied to clipboard", severity="information")
        else:
            self.notify("No assistant message to copy", severity="warning")

    def action_toggle_select_mode(self) -> None:
        """Toggle between mouse mode and text selection mode."""
        import sys

        self._select_mode = not self._select_mode

        if self._select_mode:
            # Disable mouse reporting - allows terminal text selection
            sys.stdout.write("\x1b[?1000l")  # Disable basic mouse
            sys.stdout.write("\x1b[?1002l")  # Disable button-event tracking
            sys.stdout.write("\x1b[?1003l")  # Disable all-motion tracking
            sys.stdout.write("\x1b[?1006l")  # Disable SGR extended mouse
            sys.stdout.flush()
            self.notify("Select mode ON - use mouse to select text", severity="information")
        else:
            # Re-enable mouse reporting
            sys.stdout.write("\x1b[?1000h")  # Enable basic mouse
            sys.stdout.write("\x1b[?1002h")  # Enable button-event tracking
            sys.stdout.write("\x1b[?1006h")  # Enable SGR extended mouse
            sys.stdout.flush()
            self.notify("Select mode OFF - mouse interactions enabled", severity="information")


def run_app(config: Optional[Config] = None, mouse: bool = True) -> None:
    """Run the Valis CLI application.

    Args:
        config: Application configuration
        mouse: Enable mouse support. Set False for text selection mode.
    """
    app = ValisCLI(config=config)
    app.run(mouse=mouse)


if __name__ == "__main__":
    run_app()
