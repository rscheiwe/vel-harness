"""
Parallel Approval Manager

Handles multiple concurrent tool approval requests, enabling parallel
tool execution when the model requests multiple tools in the same step.
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime


@dataclass
class PendingApproval:
    """A pending tool approval request."""
    id: str
    tool_name: str
    args: Dict[str, Any]
    timestamp: datetime


class ApprovalManager:
    """
    Manages parallel tool approval requests.

    When the agent calls multiple tool execute() functions in parallel,
    each one may need approval. This manager:
    1. Tracks all pending approvals by unique ID
    2. Allows external code (UI) to respond to approvals
    3. Resolves the waiting futures when responses come in

    Handles race conditions where:
    - User may approve BEFORE execute() is called (pre-stored approvals)
    - User may approve AFTER execute() is waiting (pending approvals)
    """

    def __init__(self) -> None:
        self._pending: Dict[str, tuple[PendingApproval, asyncio.Future]] = {}
        self._stored_approvals: Dict[str, bool] = {}
        self._id_counter = 0
        self._callbacks: List[Callable[[PendingApproval], None]] = []

    def on_approval_needed(self, callback: Callable[[PendingApproval], None]) -> None:
        """Register a callback for when approval is needed."""
        self._callbacks.append(callback)

    async def request_approval(
        self,
        tool_name: str,
        args: Dict[str, Any],
    ) -> bool:
        """
        Request approval for a tool call.
        Returns when the user responds.

        Checks for pre-stored approvals first (for when user approved
        before execute() was called).
        """
        # Check if user already responded (via UI before execute() was called)
        if tool_name in self._stored_approvals:
            approved = self._stored_approvals.pop(tool_name)
            return approved

        self._id_counter += 1
        approval_id = f"approval-{self._id_counter}-{int(datetime.now().timestamp() * 1000)}"

        approval = PendingApproval(
            id=approval_id,
            tool_name=tool_name,
            args=args,
            timestamp=datetime.now(),
        )

        future: asyncio.Future[bool] = asyncio.get_event_loop().create_future()
        self._pending[approval_id] = (approval, future)

        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(approval)
            except Exception:
                pass  # Don't let callback errors break the flow

        return await future

    def respond(self, approval_id: str, approved: bool) -> bool:
        """
        Respond to a pending approval by ID.
        Returns True if the approval was found and resolved.
        """
        if approval_id not in self._pending:
            return False

        _, future = self._pending.pop(approval_id)
        if not future.done():
            future.set_result(approved)
        return True

    def respond_by_tool_name(self, tool_name: str, approved: bool) -> bool:
        """
        Respond to approval by tool name.
        If the approval is already pending, resolves it.
        If not yet pending (user responded early), stores for later.
        """
        # Check if there's a pending approval for this tool
        for approval_id, (approval, _) in list(self._pending.items()):
            if approval.tool_name == tool_name:
                return self.respond(approval_id, approved)

        # No pending approval - user responded before execute() was called
        # Store for later
        self._stored_approvals[tool_name] = approved
        return True

    def get_pending(self) -> List[PendingApproval]:
        """Get all pending approvals."""
        return [approval for approval, _ in self._pending.values()]

    def get_next(self) -> Optional[PendingApproval]:
        """Get the next pending approval (FIFO)."""
        if not self._pending:
            return None
        first_id = next(iter(self._pending))
        return self._pending[first_id][0]

    def has_pending(self) -> bool:
        """Check if there are any pending approvals."""
        return len(self._pending) > 0

    @property
    def pending_count(self) -> int:
        """Get count of pending approvals."""
        return len(self._pending)

    def clear(self) -> None:
        """Clear all pending approvals (deny all)."""
        for approval_id, (_, future) in list(self._pending.items()):
            if not future.done():
                future.set_result(False)
        self._pending.clear()
