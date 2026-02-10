"""
Core prompts - identity, tone, and task execution guidance.
"""

from .base import BASE_SYSTEM_PROMPT, get_base_prompt
from .tone import TONE_PROMPT
from .tasks import DOING_TASKS_PROMPT

__all__ = [
    "BASE_SYSTEM_PROMPT",
    "get_base_prompt",
    "TONE_PROMPT",
    "DOING_TASKS_PROMPT",
]
