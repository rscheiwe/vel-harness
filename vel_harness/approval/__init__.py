"""
Approval Management

Handles parallel tool approval requests for human-in-the-loop workflows.
"""

from vel_harness.approval.manager import ApprovalManager, PendingApproval

__all__ = ["ApprovalManager", "PendingApproval"]
