"""
Approval Dialog Widget

Dialog for approving or denying tool calls.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, Label, Static


class ToolApprovalWidget(Static):
    """Widget for displaying a tool call awaiting approval."""

    DEFAULT_CSS = """
    ToolApprovalWidget {
        background: $warning-darken-3;
        border: solid $warning;
        padding: 1;
        margin: 1;
    }

    ToolApprovalWidget .tool-header {
        color: $warning;
        text-style: bold;
    }

    ToolApprovalWidget .tool-name {
        color: $accent;
        text-style: bold;
    }

    ToolApprovalWidget .tool-args {
        padding: 1;
        background: $surface-darken-2;
        margin: 1 0;
    }

    ToolApprovalWidget Horizontal {
        height: 3;
        align: center middle;
    }

    ToolApprovalWidget Button {
        margin: 0 1;
    }
    """

    class Approved(Message):
        """Message sent when tool is approved."""

        def __init__(self, tool_id: str):
            self.tool_id = tool_id
            super().__init__()

    class Denied(Message):
        """Message sent when tool is denied."""

        def __init__(self, tool_id: str):
            self.tool_id = tool_id
            super().__init__()

    def __init__(
        self,
        tool_id: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        description: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.tool_id = tool_id
        self.tool_name = tool_name
        self.tool_args = tool_args
        self.description = description

    def compose(self) -> ComposeResult:
        """Compose the approval widget."""
        yield Static(
            Text("Tool Approval Required", style="bold yellow"),
            classes="tool-header",
        )
        yield Static(
            Text(f"Tool: {self.tool_name}", style="bold cyan"),
            classes="tool-name",
        )

        # Format arguments
        args_lines = []
        for key, value in self.tool_args.items():
            value_str = repr(value)
            if len(value_str) > 100:
                value_str = value_str[:100] + "..."
            args_lines.append(f"  {key}: {value_str}")

        yield Static(
            "\n".join(args_lines) or "  (no arguments)",
            classes="tool-args",
        )

        if self.description:
            yield Static(
                Text(self.description, style="dim"),
            )

        with Horizontal():
            yield Button("Approve", id="approve-btn", variant="success")
            yield Button("Deny", id="deny-btn", variant="error")
            yield Button("Always Allow", id="always-btn", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "approve-btn":
            self.post_message(self.Approved(self.tool_id))
        elif event.button.id == "deny-btn":
            self.post_message(self.Denied(self.tool_id))
        elif event.button.id == "always-btn":
            # TODO: Add to auto-approve list
            self.post_message(self.Approved(self.tool_id))


@dataclass
class ApprovalResult:
    """Result of approval dialog."""
    approved: bool
    always: bool = False  # If True, save to permissions


class ApprovalDialog(ModalScreen[ApprovalResult]):
    """Modal dialog for tool approval."""

    DEFAULT_CSS = """
    ApprovalDialog {
        align: center middle;
    }

    ApprovalDialog > Container {
        width: 80;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: thick $warning;
        padding: 1 2;
    }

    ApprovalDialog .dialog-title {
        text-style: bold;
        color: $warning;
        text-align: center;
        padding: 1;
    }

    ApprovalDialog .tool-info {
        padding: 1;
        background: $surface-darken-1;
        margin: 1 0;
    }

    ApprovalDialog .tool-name {
        color: $accent;
        text-style: bold;
    }

    ApprovalDialog .args-panel {
        padding: 1;
        background: $surface-darken-2;
        margin: 1 0;
        max-height: 20;
        overflow-y: auto;
    }

    ApprovalDialog Horizontal {
        height: 3;
        align: center middle;
        margin-top: 1;
    }

    ApprovalDialog Button {
        margin: 0 1;
    }

    ApprovalDialog .hint {
        color: $text-muted;
        text-align: center;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("y", "approve", "Approve", show=True, priority=True),
        Binding("a", "always_allow", "Always Allow", show=True, priority=True),
        Binding("n", "deny", "Deny", show=True, priority=True),
        Binding("escape", "deny", "Cancel", show=True, priority=True),
        Binding("enter", "approve", "Approve", show=False, priority=True),
    ]

    def __init__(
        self,
        tool_id: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        description: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.tool_id = tool_id
        self.tool_name = tool_name
        self.tool_args = tool_args
        self.description = description

    def compose(self) -> ComposeResult:
        """Compose the dialog."""
        with Container():
            yield Static(
                "Tool Approval Required",
                classes="dialog-title",
            )

            with Vertical(classes="tool-info"):
                yield Static(
                    Text(f"Tool: {self.tool_name}", style="bold cyan"),
                    classes="tool-name",
                )

                if self.description:
                    yield Static(Text(self.description, style="dim"))

            yield Static("Arguments:", classes="args-label")

            # Format arguments as syntax-highlighted JSON-ish
            import json
            args_str = json.dumps(self.tool_args, indent=2, default=str)
            yield Static(
                Syntax(args_str, "json", theme="monokai", line_numbers=False),
                classes="args-panel",
            )

            with Horizontal():
                yield Button("Approve [y]", id="approve", variant="success")
                yield Button("Always Allow [a]", id="always", variant="primary")
                yield Button("Deny [n]", id="deny", variant="error")

            yield Static(
                "Permission saved to .valis/settings.local.json",
                classes="hint",
            )

    def on_mount(self) -> None:
        """Focus the approve button when dialog mounts."""
        try:
            approve_btn = self.query_one("#approve", Button)
            approve_btn.focus()
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "approve":
            self.dismiss(ApprovalResult(approved=True, always=False))
        elif event.button.id == "always":
            self.dismiss(ApprovalResult(approved=True, always=True))
        elif event.button.id == "deny":
            self.dismiss(ApprovalResult(approved=False, always=False))

    def action_approve(self) -> None:
        """Approve the tool call once."""
        self.dismiss(ApprovalResult(approved=True, always=False))

    def action_always_allow(self) -> None:
        """Always allow this tool."""
        self.dismiss(ApprovalResult(approved=True, always=True))

    def action_deny(self) -> None:
        """Deny the tool call."""
        self.dismiss(ApprovalResult(approved=False, always=False))


class BatchApprovalWidget(Widget):
    """Widget for approving multiple tool calls at once."""

    DEFAULT_CSS = """
    BatchApprovalWidget {
        height: auto;
        background: $warning-darken-3;
        border: solid $warning;
        padding: 1;
    }

    BatchApprovalWidget .batch-header {
        text-style: bold;
        color: $warning;
    }

    BatchApprovalWidget .tool-list {
        padding: 1;
        background: $surface-darken-1;
    }

    BatchApprovalWidget Horizontal {
        height: 3;
        align: center middle;
    }
    """

    class BatchApproved(Message):
        """Message sent when batch is approved."""

        def __init__(self, tool_ids: List[str]):
            self.tool_ids = tool_ids
            super().__init__()

    class BatchDenied(Message):
        """Message sent when batch is denied."""

        def __init__(self, tool_ids: List[str]):
            self.tool_ids = tool_ids
            super().__init__()

    def __init__(
        self,
        tools: List[Dict[str, Any]],
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.tools = tools

    def compose(self) -> ComposeResult:
        """Compose the batch approval widget."""
        yield Static(
            Text(f"Approve {len(self.tools)} tool calls?", style="bold yellow"),
            classes="batch-header",
        )

        # List tools
        tool_lines = []
        for tool in self.tools:
            tool_lines.append(f"  - {tool.get('name', 'unknown')}")
        yield Static("\n".join(tool_lines), classes="tool-list")

        with Horizontal():
            yield Button("Approve All", id="approve-all", variant="success")
            yield Button("Deny All", id="deny-all", variant="error")
            yield Button("Review Each", id="review", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        tool_ids = [t.get("id", "") for t in self.tools]

        if event.button.id == "approve-all":
            self.post_message(self.BatchApproved(tool_ids))
        elif event.button.id == "deny-all":
            self.post_message(self.BatchDenied(tool_ids))
        # Review each is handled by parent
