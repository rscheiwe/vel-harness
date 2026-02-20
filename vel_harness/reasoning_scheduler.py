"""
Phase-aware reasoning scheduler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from vel_harness.reasoning import ReasoningConfig


@dataclass
class ReasoningSchedulerConfig:
    """Reasoning budgets by phase for native reasoning mode."""

    enabled: bool = True
    planning_budget_tokens: int = 12000
    build_budget_tokens: int = 5000
    verify_budget_tokens: int = 15000


class ReasoningScheduler:
    """Derives reasoning config per execution phase."""

    def __init__(self, config: Optional[ReasoningSchedulerConfig] = None) -> None:
        self.config = config or ReasoningSchedulerConfig()

    def for_phase(self, base: Optional[ReasoningConfig], phase: str) -> Optional[ReasoningConfig]:
        if base is None:
            return None
        if not self.config.enabled:
            return base
        if base.mode != "native":
            return base

        budget = self.config.build_budget_tokens
        if phase == "planning":
            budget = self.config.planning_budget_tokens
        elif phase == "verify":
            budget = self.config.verify_budget_tokens

        return ReasoningConfig(
            mode=base.mode,
            budget_tokens=budget,
            max_refinements=base.max_refinements,
            confidence_threshold=base.confidence_threshold,
            thinking_model=base.thinking_model,
            thinking_tools=base.thinking_tools,
            prompt_template=base.prompt_template,
            delimiters=base.delimiters,
            stream_reasoning=base.stream_reasoning,
            transient=base.transient,
        )

