"""
Agent prompts - specialized prompts for subagents.
"""

from .explore import EXPLORE_AGENT_PROMPT
from .plan import PLAN_AGENT_PROMPT
from .discover import DISCOVER_AGENT_PROMPT
from .implement import IMPLEMENT_AGENT_PROMPT
from .verify import VERIFY_AGENT_PROMPT
from .critic import CRITIC_AGENT_PROMPT

__all__ = [
    "EXPLORE_AGENT_PROMPT",
    "PLAN_AGENT_PROMPT",
    "DISCOVER_AGENT_PROMPT",
    "IMPLEMENT_AGENT_PROMPT",
    "VERIFY_AGENT_PROMPT",
    "CRITIC_AGENT_PROMPT",
]
