"""
Chat Display Widget

Displays the conversation history with messages and tool calls.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from rich.console import RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


class MessageRole(str, Enum):
    """Message role types."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"
    ERROR = "error"


@dataclass
class Message:
    """A chat message."""

    role: MessageRole
    content: str
    timestamp: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.metadata is None:
            self.metadata = {}


class MessageWidget(Static):
    """Widget for displaying a single message."""

    DEFAULT_CSS = """
    MessageWidget {
        margin: 0 1;
        padding: 0 1;
        height: auto;
    }

    MessageWidget .message-content {
        height: auto;
    }

    MessageWidget.user {
        background: $primary-darken-2;
        border-left: thick $primary;
        margin-top: 1;
        margin-bottom: 1;
        height: auto;
    }

    MessageWidget.assistant {
        background: $surface;
        border-left: thick $secondary;
        margin-bottom: 1;
    }

    MessageWidget.system {
        background: $surface-darken-1;
        border-left: thick $warning;
        color: $text-muted;
        margin-top: 1;
        margin-bottom: 1;
    }

    MessageWidget.tool {
        background: $surface-darken-2;
        border-left: thick $accent;
        color: $text-muted;
    }

    MessageWidget.error {
        background: $error-darken-3;
        border-left: thick $error;
        color: $error;
    }
    """

    def __init__(
        self,
        message: Message,
        compact: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.message = message
        self.compact = compact
        self.add_class(message.role.value)

    def compose(self) -> ComposeResult:
        """Compose the message widget."""
        yield Static(self._render_content(), classes="message-content")

    def _render_content(self) -> RenderableType:
        """Render the message content."""
        if self.message.role == MessageRole.USER:
            prefix = "You" if not self.compact else ">"
            return Text(f"{prefix}: {self.message.content}")

        elif self.message.role == MessageRole.ASSISTANT:
            if self.compact:
                return Text(self.message.content)
            # Render as markdown for assistant messages
            return Markdown(self.message.content)

        elif self.message.role == MessageRole.TOOL:
            tool_name = self.message.metadata.get("name", "tool")
            if self.compact:
                return Text(f"[{tool_name}] {self.message.content[:100]}...")
            return Text(f"Tool: {tool_name}\n{self.message.content}")

        elif self.message.role == MessageRole.ERROR:
            return Text(f"Error: {self.message.content}", style="bold red")

        elif self.message.role == MessageRole.SYSTEM:
            # System messages support Rich markup
            return Text.from_markup(self.message.content)

        else:
            return Text(self.message.content, style="dim")


class ToolCallWidget(Static):
    """Widget for displaying a tool call with tree format and shimmer when running."""

    DEFAULT_CSS = """
    ToolCallWidget {
        margin: 0 1;
        padding: 0 1;
        height: auto;
        background: $surface-darken-1;
    }

    ToolCallWidget.pending {
        color: #40E0D0;
    }

    ToolCallWidget.completed {
        color: $text-muted;
    }

    ToolCallWidget.first-in-group {
        margin-top: 1;
    }

    ToolCallWidget.last-in-group {
        margin-bottom: 1;
    }

    /* Subtle indentation for consecutive tool calls */
    ToolCallWidget.continuation {
        padding-left: 2;
    }
    """

    SHIMMER_CHARS = ["·", "∴", "·", "∵", "·", "⁖", "·", "∷"]

    def __init__(
        self,
        name: str,
        args: Dict[str, Any],
        result: Optional[Any] = None,
        pending: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.tool_name = name
        self.tool_args = args
        self.tool_result = result
        self._result_summary: Optional[str] = None
        self.pending = pending
        self._shimmer_frame = 0
        self._timer = None
        self.add_class("pending" if pending else "completed")

    def on_mount(self) -> None:
        """Start animation if pending, otherwise render static."""
        if self.pending:
            self._timer = self.set_interval(0.15, self._tick)
        self._update_display()

    def _tick(self) -> None:
        """Timer tick for shimmer animation."""
        self._shimmer_frame = (self._shimmer_frame + 1) % len(self.SHIMMER_CHARS)
        self._update_display()

    def mark_completed(self, result: Optional[Any] = None) -> None:
        """Mark this tool call as completed with optional result."""
        self.pending = False
        self.tool_result = result
        self._result_summary = self._generate_result_summary(result)
        if self._timer:
            self._timer.stop()
            self._timer = None
        self.remove_class("pending")
        self.add_class("completed")
        self._update_display()

    def _generate_result_summary(self, result: Any) -> str:
        """Generate a brief summary of the tool result."""
        if result is None:
            return "Done"

        # Handle dict results (most tools return dicts)
        if isinstance(result, dict):
            # Check for error
            if "error" in result:
                err = str(result["error"])[:40]
                return f"Error: {err}"

            # Tool-specific dict handling
            if self.tool_name in ("ls", "glob"):
                entries = result.get("entries", result.get("matches", []))
                count = result.get("count", len(entries) if isinstance(entries, list) else 0)
                return f"Found {count} items"
            elif self.tool_name in ("read_file", "read"):
                lines = result.get("lines_returned", result.get("total_lines", 0))
                total = result.get("total_lines", lines)
                if result.get("has_more"):
                    return f"Read {lines}/{total} lines"
                return f"Read {lines} lines"
            elif self.tool_name in ("write_file", "write"):
                lines = result.get("lines", 0)
                return f"Wrote {lines} lines"
            elif self.tool_name in ("edit_file", "edit"):
                return "File updated"
            elif self.tool_name in ("grep", "search"):
                matches = result.get("matches", [])
                total = result.get("total_matches", len(matches))
                return f"Found {total} matches"
            elif self.tool_name == "execute":
                if result.get("success", True):
                    return "Executed successfully"
                return "Completed with errors"
            else:
                # Generic dict - check for status
                status = result.get("status", "")
                if status:
                    return str(status)
                return "Done"

        # Handle string results
        result_str = str(result)

        if self.tool_name == "execute":
            if "error" in result_str.lower() or "traceback" in result_str.lower():
                return "Completed with errors"
            return "Executed successfully"

        # Generic: show truncated result or line count
        if len(result_str) > 50:
            lines = result_str.count("\n") + 1
            if lines > 1:
                return f"{lines} lines"
            return result_str[:40] + "..."
        return result_str[:50] if result_str else "Done"

    def _format_args(self) -> str:
        """Format tool arguments - show full paths, truncate only content."""
        args_parts = []
        for k, v in self.tool_args.items():
            v_str = str(v)
            # Only truncate content-like args, not paths
            if k in ("content", "old_text", "new_text", "code") and len(v_str) > 50:
                v_str = v_str[:47] + "..."
            args_parts.append(f"{k}={v_str}")
        return ", ".join(args_parts)

    def _update_display(self) -> None:
        """Update the display."""
        if self.pending:
            # Running state: shimmer + "Running tool_name..."
            shimmer = self.SHIMMER_CHARS[self._shimmer_frame]
            self.update(Text(f"{shimmer} Running {self.tool_name}...", style="#40E0D0"))
        else:
            # Completed state: tree format
            # ● tool_name(args)
            #   └ Result summary
            args_str = self._format_args()
            summary = self._result_summary or "Done"

            text = Text()
            text.append("● ", style="green")
            text.append(f"{self.tool_name}({args_str})\n", style="dim cyan")
            text.append("  └ ", style="dim")
            text.append(summary, style="dim")
            self.update(text)


class BrailleSpinner:
    """Animated braille spinner."""

    FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def __init__(self) -> None:
        self._position = 0

    def next_frame(self) -> str:
        frame = self.FRAMES[self._position]
        self._position = (self._position + 1) % len(self.FRAMES)
        return frame

    def current_frame(self) -> str:
        return self.FRAMES[self._position]


class LoadingIndicator(Widget):
    """Animated loading indicator - based on deepagents-cli."""

    DEFAULT_CSS = """
    LoadingIndicator {
        height: auto;
        padding: 0 1;
    }

    LoadingIndicator Horizontal {
        height: auto;
        width: 100%;
    }

    LoadingIndicator .spinner {
        width: auto;
        color: $success;
    }

    LoadingIndicator .status {
        width: auto;
        color: $success;
    }
    """

    def __init__(self, status: str = "Agent is thinking", **kwargs):
        super().__init__(**kwargs)
        self._status = status
        self._spinner = BrailleSpinner()
        self._spinner_widget: Optional[Static] = None
        self._status_widget: Optional[Static] = None

    def compose(self) -> ComposeResult:
        """Compose the loading widget layout."""
        with Horizontal():
            self._spinner_widget = Static(self._spinner.current_frame(), classes="spinner")
            yield self._spinner_widget
            self._status_widget = Static(f" {self._status}...", classes="status")
            yield self._status_widget

    def on_mount(self) -> None:
        """Start animation on mount."""
        self.set_interval(0.1, self._update_animation)

    def _update_animation(self) -> None:
        """Update spinner frame."""
        if self._spinner_widget:
            frame = self._spinner.next_frame()
            self._spinner_widget.update(f"[#00FF00]{frame}[/]")


class StreamingTextWidget(Static):
    """Widget for displaying streaming text."""

    DEFAULT_CSS = """
    StreamingTextWidget {
        padding: 0 1;
        margin-bottom: 1;
    }
    """

    text = reactive("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._buffer = ""

    def append(self, text: str) -> None:
        """Append text to the stream."""
        self._buffer += text
        self.text = self._buffer

    def watch_text(self, text: str) -> None:
        """Update display when text changes."""
        self.update(Markdown(text) if text else "")
        # Auto-scroll after updating
        self.call_after_refresh(self._scroll_to_end)

    def _scroll_to_end(self) -> None:
        """Scroll to end after refresh."""
        try:
            # Find ChatDisplay ancestor and scroll (respecting user scroll position)
            for ancestor in self.ancestors:
                if isinstance(ancestor, ChatDisplay):
                    ancestor.smart_scroll_end(animate=False)
                    break
        except Exception:
            pass

    def clear(self) -> None:
        """Clear the stream."""
        self._buffer = ""
        self.text = ""

    def get_content(self) -> str:
        """Get the current content."""
        return self._buffer


class ChatDisplay(ScrollableContainer):
    """Container for displaying the chat conversation."""

    DEFAULT_CSS = """
    ChatDisplay {
        height: 1fr;
        padding: 1;
        scrollbar-gutter: stable;
    }

    ChatDisplay > Vertical {
        height: auto;
    }
    """

    can_focus = False  # Prevent focus highlight when clicking chat area

    def __init__(
        self,
        compact: bool = False,
        show_tool_calls: bool = True,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.compact = compact
        self.show_tool_calls = show_tool_calls
        self._messages: List[Message] = []
        self._streaming: Optional[StreamingTextWidget] = None
        self._loading: Optional[LoadingIndicator] = None
        self._user_scrolled_up = False

    def compose(self) -> ComposeResult:
        """Compose the chat display."""
        yield Vertical(id="chat-messages")

    def on_scroll_up(self) -> None:
        """User scrolled up - disable auto-scroll."""
        self._user_scrolled_up = True

    def on_scroll_down(self) -> None:
        """User scrolled down - check if at bottom to re-enable auto-scroll."""
        # Re-enable auto-scroll if user scrolled back to bottom
        if self.scroll_y >= self.max_scroll_y - 2:
            self._user_scrolled_up = False

    def smart_scroll_end(self, animate: bool = True) -> None:
        """Scroll to end only if user hasn't scrolled up."""
        if not self._user_scrolled_up:
            self.scroll_end(animate=animate)

    def add_message(self, message: Message) -> None:
        """Add a message to the display."""
        self._messages.append(message)
        # Mark last tool call for spacing before message
        self._mark_last_tool_call()
        container = self.query_one("#chat-messages", Vertical)
        container.mount(MessageWidget(message, compact=self.compact))
        self.smart_scroll_end(animate=False)

    def add_user_message(self, content: str) -> None:
        """Add a user message."""
        self.add_message(Message(role=MessageRole.USER, content=content))

    def add_assistant_message(self, content: str) -> None:
        """Add an assistant message."""
        self.add_message(Message(role=MessageRole.ASSISTANT, content=content))

    def add_tool_call(
        self,
        name: str,
        args: Dict[str, Any],
        tool_call_id: Optional[str] = None,
        result: Optional[Any] = None,
        pending: bool = False,
    ) -> None:
        """Add a tool call display."""
        if not self.show_tool_calls:
            return

        container = self.query_one("#chat-messages", Vertical)

        # Check if this is first tool call after text (for spacing)
        is_first_in_group = True
        children = list(container.children)
        if children:
            last_child = children[-1]
            if isinstance(last_child, ToolCallWidget):
                is_first_in_group = False

        widget = ToolCallWidget(
            name=name,
            args=args,
            result=result,
            pending=pending,
            id=f"tool-{tool_call_id}" if tool_call_id else None,
        )
        if is_first_in_group:
            widget.add_class("first-in-group")
        else:
            # Subtle indent for consecutive tool calls
            widget.add_class("continuation")

        container.mount(widget)
        self.smart_scroll_end(animate=False)

    def mark_tool_completed(self, tool_call_id: str, result: Optional[Any] = None) -> None:
        """Mark a tool call as completed by its ID."""
        try:
            widget = self.query_one(f"#tool-{tool_call_id}", ToolCallWidget)
            widget.mark_completed(result)
        except Exception:
            pass  # Widget not found, ignore

    def _mark_last_tool_call(self) -> None:
        """Mark the last tool call in a group for spacing."""
        container = self.query_one("#chat-messages", Vertical)
        children = list(container.children)
        if children:
            last_child = children[-1]
            if isinstance(last_child, ToolCallWidget):
                last_child.add_class("last-in-group")

    def show_loading(self) -> None:
        """Show loading indicator."""
        if self._loading is not None:
            return
        self._loading = LoadingIndicator()
        container = self.query_one("#chat-messages", Vertical)
        container.mount(self._loading)
        self.smart_scroll_end(animate=False)

    def hide_loading(self) -> None:
        """Hide loading indicator."""
        if self._loading is not None:
            self._loading.remove()
            self._loading = None

    def start_streaming(self) -> StreamingTextWidget:
        """Start streaming text."""
        # Hide loading indicator when streaming starts
        self.hide_loading()
        # Mark last tool call for spacing before text
        self._mark_last_tool_call()
        self._streaming = StreamingTextWidget()
        container = self.query_one("#chat-messages", Vertical)
        container.mount(self._streaming)
        self.smart_scroll_end(animate=False)
        return self._streaming

    def end_streaming(self) -> str:
        """End streaming and return content."""
        if self._streaming is None:
            return ""

        content = self._streaming.get_content()

        # Convert to regular message
        self._streaming.remove()
        self._streaming = None

        if content:
            self.add_message(Message(
                role=MessageRole.ASSISTANT,
                content=content,
            ))

        return content

    def add_error(self, error: str) -> None:
        """Add an error message."""
        self.add_message(Message(role=MessageRole.ERROR, content=error))

    def clear(self) -> None:
        """Clear all messages."""
        self._messages.clear()
        container = self.query_one("#chat-messages", Vertical)
        container.remove_children()

    def get_messages(self) -> List[Message]:
        """Get all messages."""
        return self._messages.copy()

    def get_last_assistant_message(self) -> Optional[str]:
        """Get the content of the last assistant message."""
        for msg in reversed(self._messages):
            if msg.role == MessageRole.ASSISTANT:
                return msg.content
        return None

    def get_last_message(self) -> Optional[str]:
        """Get the content of the last message (any role)."""
        if self._messages:
            return self._messages[-1].content
        return None
