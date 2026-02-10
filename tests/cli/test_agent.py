"""
Tests for valis_cli.agent
"""

import pytest

from valis_cli.agent import (
    AgentEvent,
    ApprovalHandler,
    EventType,
    ToolCall,
)


class TestEventType:
    """Tests for EventType enum."""

    def test_event_types_exist(self):
        """Test expected event types exist."""
        assert EventType.TEXT_START.value == "text-start"
        assert EventType.TEXT_DELTA.value == "text-delta"
        assert EventType.TEXT_END.value == "text-end"
        assert EventType.TOOL_CALL.value == "tool-call"
        assert EventType.TOOL_RESULT.value == "tool-result"
        assert EventType.APPROVAL_REQUIRED.value == "approval-required"
        assert EventType.ERROR.value == "error"


class TestAgentEvent:
    """Tests for AgentEvent."""

    def test_create_event(self):
        """Test creating an event."""
        event = AgentEvent(
            type=EventType.TEXT_DELTA,
            data={"delta": "Hello"},
        )
        assert event.type == EventType.TEXT_DELTA
        assert event.data["delta"] == "Hello"
        assert event.timestamp is not None

    def test_to_dict(self):
        """Test converting event to dict."""
        event = AgentEvent(
            type=EventType.TOOL_CALL,
            data={"name": "read_file", "args": {"path": "/test"}},
        )
        d = event.to_dict()
        assert d["type"] == "tool-call"
        assert d["data"]["name"] == "read_file"
        assert "timestamp" in d


class TestToolCall:
    """Tests for ToolCall."""

    def test_create_tool_call(self):
        """Test creating a tool call."""
        tc = ToolCall(
            id="tc_123",
            name="write_file",
            args={"path": "/test.txt", "content": "Hello"},
            description="Write a file",
        )
        assert tc.id == "tc_123"
        assert tc.name == "write_file"
        assert tc.args["path"] == "/test.txt"
        assert tc.description == "Write a file"

    def test_format_for_display(self):
        """Test formatting for display."""
        tc = ToolCall(
            id="tc_123",
            name="read_file",
            args={"path": "/test.txt"},
        )
        display = tc.format_for_display()
        assert "read_file" in display
        assert "/test.txt" in display

    def test_format_truncates_long_args(self):
        """Test that long args are truncated in display."""
        tc = ToolCall(
            id="tc_123",
            name="write_file",
            args={"content": "x" * 100},
        )
        display = tc.format_for_display()
        assert len(display) < 200  # Should be truncated


class TestApprovalHandler:
    """Tests for ApprovalHandler."""

    def test_auto_approve(self):
        """Test auto-approve list."""
        handler = ApprovalHandler(auto_approve=["read_file", "ls"])
        assert handler.should_auto_approve("read_file")
        assert handler.should_auto_approve("ls")
        assert not handler.should_auto_approve("write_file")

    def test_always_deny(self):
        """Test always-deny list."""
        handler = ApprovalHandler(always_deny=["dangerous_tool"])
        assert handler.should_deny("dangerous_tool")
        assert not handler.should_deny("read_file")

    def test_pending_approvals(self):
        """Test pending approval management."""
        handler = ApprovalHandler()

        tc = ToolCall(
            id="tc_123",
            name="write_file",
            args={"path": "/test"},
        )

        handler.add_pending(tc)
        assert handler.get_pending("tc_123") == tc
        assert handler.get_pending("tc_456") is None

    def test_resolve_approval(self):
        """Test resolving approvals."""
        handler = ApprovalHandler()

        tc = ToolCall(
            id="tc_123",
            name="write_file",
            args={},
        )

        handler.add_pending(tc)
        result = handler.resolve("tc_123", True)
        assert result is True
        assert handler.get_pending("tc_123") is None

    def test_resolve_nonexistent(self):
        """Test resolving non-existent approval."""
        handler = ApprovalHandler()
        result = handler.resolve("nonexistent", True)
        assert result is False

    def test_clear_pending(self):
        """Test clearing all pending approvals."""
        handler = ApprovalHandler()

        for i in range(3):
            tc = ToolCall(id=f"tc_{i}", name="tool", args={})
            handler.add_pending(tc)

        handler.clear_pending()
        for i in range(3):
            assert handler.get_pending(f"tc_{i}") is None
