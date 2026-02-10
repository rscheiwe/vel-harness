"""
Reminder prompts - conditional injection based on context.
P2 implementation - stubs for now.
"""

from typing import List, Dict, Any


# Placeholder prompts for P2 implementation
PLAN_MODE_REMINDER = ""
LONG_CONVERSATION_REMINDER = ""
ERROR_RECOVERY_REMINDER = ""


def get_active_reminders(context: Dict[str, Any]) -> List[str]:
    """
    Get reminders that should be active given current context.

    Args:
        context: Dict with keys like:
            - plan_mode_active: bool
            - token_usage_percent: float
            - last_tool_failed: bool
            - consecutive_errors: int

    Returns:
        List of reminder strings to inject.
    """
    # P2 implementation - return empty list for now
    return []


def inject_reminders(system_prompt: str, context: Dict[str, Any]) -> str:
    """Inject active reminders into system prompt."""
    reminders = get_active_reminders(context)
    if reminders:
        reminder_section = "\n\n## Active Reminders\n\n" + "\n\n".join(reminders)
        return system_prompt + reminder_section
    return system_prompt


__all__ = [
    "PLAN_MODE_REMINDER",
    "LONG_CONVERSATION_REMINDER",
    "ERROR_RECOVERY_REMINDER",
    "get_active_reminders",
    "inject_reminders",
]
