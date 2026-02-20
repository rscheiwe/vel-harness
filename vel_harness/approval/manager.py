"""
Parallel Approval Manager

Handles multiple concurrent tool approval requests, enabling parallel
tool execution when the model requests multiple tools in the same step.
"""

import asyncio
import json
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
        self._stored_approvals_by_key: Dict[str, bool] = {}
        self._stored_approvals_by_tool: Dict[str, List[bool]] = {}
        self._id_counter = 0
        self._callbacks: List[Callable[[PendingApproval], None]] = []

    def _approval_key(self, tool_name: str, args: Dict[str, Any]) -> str:
        args_json = json.dumps(args, sort_keys=True, default=str)
        return f"{tool_name}:{args_json}"

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
        key = self._approval_key(tool_name, args)

        # Check if user already responded (exact call match)
        if key in self._stored_approvals_by_key:
            approved = self._stored_approvals_by_key.pop(key)
            return approved
        # Backward-compatible fallback by tool name queue.
        queue = self._stored_approvals_by_tool.get(tool_name)
        if queue:
            approved = queue.pop(0)
            if not queue:
                self._stored_approvals_by_tool.pop(tool_name, None)
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
        # Check if there's a pending approval for this tool. If more than one,
        # do not auto-resolve to avoid approving the wrong tool call.
        matches = [
            approval_id
            for approval_id, (approval, _) in self._pending.items()
            if approval.tool_name == tool_name
        ]
        if len(matches) == 1:
            return self.respond(matches[0], approved)
        if len(matches) > 1:
            return False

        # No pending approval - user responded before execute() was called
        self._stored_approvals_by_tool.setdefault(tool_name, []).append(approved)
        return True

    def respond_by_tool_args(
        self,
        tool_name: str,
        args: Dict[str, Any],
        approved: bool,
    ) -> bool:
        """Respond using exact tool name + args matching."""
        key = self._approval_key(tool_name, args)
        for approval_id, (approval, _) in list(self._pending.items()):
            if self._approval_key(approval.tool_name, approval.args) == key:
                return self.respond(approval_id, approved)
        self._stored_approvals_by_key[key] = approved
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
        self._stored_approvals_by_key.clear()
        self._stored_approvals_by_tool.clear()
