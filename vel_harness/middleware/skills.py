"""
Skills Middleware

Provides tools for managing and using procedural knowledge skills.

Supports two injection modes:
- TOOL_RESULT: Skills returned as tool_result (preserves prompt caching)
- SYSTEM_PROMPT: Skills added to system prompt (legacy behavior)

The TOOL_RESULT mode follows the Claude Code pattern for better economics
with Anthropic's prompt caching.
"""

from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from vel import ToolSpec

from vel_harness.middleware.base import BaseMiddleware
from vel_harness.skills.registry import SkillsRegistry


class SkillInjectionMode(Enum):
    """Mode for skill content injection."""

    TOOL_RESULT = "tool_result"  # Skills returned as tool_result (recommended)
    SYSTEM_PROMPT = "system_prompt"  # Skills added to system prompt (legacy)


class SkillsMiddleware(BaseMiddleware):
    """
    Middleware providing skills management tools.

    Provides tools:
    - list_skills: Show available skills
    - activate_skill: Load a skill and return its content
    - deactivate_skill: Disable an active skill
    - get_skill: Get full content of a skill

    Supports two injection modes:
    - TOOL_RESULT (default): Skills returned as tool_result for prompt caching
    - SYSTEM_PROMPT: Skills added to system prompt (legacy behavior)
    """

    def __init__(
        self,
        skill_dirs: Optional[List[str]] = None,
        auto_activate: bool = True,
        max_active_skills: int = 5,
        injection_mode: SkillInjectionMode = SkillInjectionMode.TOOL_RESULT,
    ) -> None:
        """
        Initialize skills middleware.

        Args:
            skill_dirs: Directories to load skills from
            auto_activate: Whether to auto-activate skills based on context
            max_active_skills: Maximum number of simultaneously active skills
            injection_mode: How skill content is delivered (TOOL_RESULT or SYSTEM_PROMPT)
        """
        self._registry = SkillsRegistry(skill_dirs=skill_dirs)
        self._auto_activate = auto_activate
        self._max_active_skills = max_active_skills
        self._injection_mode = injection_mode

    @property
    def registry(self) -> SkillsRegistry:
        """Get the skills registry."""
        return self._registry

    def add_skill_directory(self, directory: str) -> int:
        """
        Add a directory and load skills from it.

        Args:
            directory: Directory path

        Returns:
            Number of skills loaded
        """
        self._registry._skill_dirs.append(Path(directory))
        return self._registry.load_from_directories([Path(directory)])

    def process_context(self, context: str) -> List[str]:
        """
        Process context and auto-activate matching skills.

        Args:
            context: Context text (user message, task description)

        Returns:
            Names of newly activated skills
        """
        if not self._auto_activate:
            return []

        # Deactivate skills if we're at the limit
        while len(self._registry._active_skills) >= self._max_active_skills:
            # Remove oldest active skill (first in set)
            oldest = next(iter(self._registry._active_skills))
            self._registry.deactivate_skill(oldest)

        activated = self._registry.activate_by_context(context)
        return [s.name for s in activated]

    def get_tools(self) -> List[ToolSpec]:
        """Return skills tools."""
        return [
            ToolSpec.from_function(
                self._list_skills,
                name="list_skills",
                description=(
                    "List all available skills. Skills provide procedural knowledge "
                    "for specific domains or tasks. Shows name, description, tags, "
                    "and whether each skill is currently active."
                ),
                category="skills",
            ),
            ToolSpec.from_function(
                self._activate_skill,
                name="activate_skill",
                description=(
                    "Load a skill to get its specialized knowledge and instructions. "
                    "The skill content will be returned directly in the response. "
                    "Use this before performing tasks that require domain expertise."
                ),
                category="skills",
            ),
            ToolSpec.from_function(
                self._deactivate_skill,
                name="deactivate_skill",
                description="Deactivate a currently active skill.",
                category="skills",
            ),
            ToolSpec.from_function(
                self._get_skill,
                name="get_skill",
                description=(
                    "Get the full content of a skill including all procedural "
                    "knowledge and instructions."
                ),
                category="skills",
            ),
            ToolSpec.from_function(
                self._search_skills,
                name="search_skills",
                description=(
                    "Search for skills matching a query. Searches skill names, "
                    "descriptions, and tags."
                ),
                category="skills",
            ),
        ]

    def get_system_prompt_segment(self) -> str:
        """Return system prompt with skills information.

        In TOOL_RESULT mode (default): Only lists available skills.
        Skills are loaded on-demand via activate_skill tool.
        This preserves prompt caching since system prompt stays static.

        In SYSTEM_PROMPT mode (legacy): Active skill content is injected.
        """
        segments = ["## Skills System\n"]

        # List available skills summary
        skills = self._registry.enabled_skills
        if skills:
            skill_names = [s.name for s in skills[:10]]  # Show first 10
            more_count = len(skills) - 10 if len(skills) > 10 else 0

            segments.append(f"You have access to {len(skills)} skills for specialized knowledge.\n")
            segments.append(f"Available: {', '.join(skill_names)}")
            if more_count > 0:
                segments.append(f" (+{more_count} more)")
            segments.append("\n")
            segments.append("Use `activate_skill(name)` to load a skill's instructions.\n")
            segments.append("Use `list_skills()` to see all available skills with descriptions.\n")

        # In TOOL_RESULT mode, don't inject skill content into system prompt
        if self._injection_mode == SkillInjectionMode.TOOL_RESULT:
            if self._registry.active_skills:
                active_names = [s.name for s in self._registry.active_skills]
                segments.append(f"\nCurrently loaded skills: {', '.join(active_names)}\n")
            return "\n".join(segments)

        # Legacy SYSTEM_PROMPT mode: Add active skill content
        active_content = self._registry.get_active_prompt_segments()
        if active_content:
            segments.append("\n### Active Skills\n")
            segments.append(active_content)

        return "\n".join(segments)

    def _list_skills(
        self,
        tags: Optional[List[str]] = None,
        active_only: bool = False,
    ) -> Dict[str, Any]:
        """
        List available skills.

        Args:
            tags: Filter by tags (optional)
            active_only: Only show active skills

        Returns:
            Dict with list of skills
        """
        if active_only:
            skills = self._registry.active_skills
        elif tags:
            skills = self._registry.find_skills(tags=tags)
        else:
            skills = self._registry.enabled_skills

        return {
            "skills": [
                {
                    "name": s.name,
                    "description": s.description,
                    "tags": s.tags,
                    "active": s.name in self._registry._active_skills,
                    "priority": s.priority,
                }
                for s in skills
            ],
            "total": len(skills),
            "active_count": len(self._registry._active_skills),
        }

    def _activate_skill(self, name: str) -> Dict[str, Any]:
        """
        Activate a skill and return its content.

        In TOOL_RESULT mode (default), the skill content is returned directly
        in the tool result. This preserves Anthropic prompt caching since
        the system prompt remains static.

        In SYSTEM_PROMPT mode (legacy), the skill is activated and its content
        will be added to the system prompt on the next turn.

        Args:
            name: Name of the skill to activate

        Returns:
            Dict with activation status and skill content (in TOOL_RESULT mode)
        """
        skill = self._registry.get_skill(name)
        if not skill:
            return {"error": f"Skill '{name}' not found"}

        if not skill.enabled:
            return {"error": f"Skill '{name}' is disabled"}

        # Check limit
        if len(self._registry._active_skills) >= self._max_active_skills:
            return {
                "error": f"Maximum active skills ({self._max_active_skills}) reached. "
                "Deactivate a skill first."
            }

        # Mark as active (for tracking)
        self._registry.activate_skill(name)

        # In TOOL_RESULT mode, return skill content directly
        if self._injection_mode == SkillInjectionMode.TOOL_RESULT:
            skill_content = self._registry.get_skill_content(name)
            return {
                "status": "loaded",
                "skill": name,
                "description": skill.description,
                "content": skill_content,
            }

        # Legacy SYSTEM_PROMPT mode - content added to system prompt
        return {
            "status": "activated",
            "skill": name,
            "description": skill.description,
            "note": "Skill content will be available in system prompt",
        }

    def _deactivate_skill(self, name: str) -> Dict[str, Any]:
        """
        Deactivate a skill.

        Args:
            name: Name of the skill to deactivate

        Returns:
            Dict with deactivation status
        """
        if name not in self._registry._active_skills:
            return {"error": f"Skill '{name}' is not active"}

        self._registry.deactivate_skill(name)

        return {"status": "deactivated", "skill": name}

    def _get_skill(self, name: str) -> Dict[str, Any]:
        """
        Get full skill content.

        Args:
            name: Name of the skill

        Returns:
            Dict with skill content
        """
        skill = self._registry.get_skill(name)
        if not skill:
            return {"error": f"Skill '{name}' not found"}

        return {
            "name": skill.name,
            "description": skill.description,
            "content": skill.content,
            "tags": skill.tags,
            "triggers": skill.triggers,
            "active": skill.name in self._registry._active_skills,
        }

    def _search_skills(self, query: str) -> Dict[str, Any]:
        """
        Search for skills.

        Args:
            query: Search query

        Returns:
            Dict with matching skills
        """
        skills = self._registry.find_skills(query=query)

        return {
            "query": query,
            "results": [
                {
                    "name": s.name,
                    "description": s.description,
                    "tags": s.tags,
                    "active": s.name in self._registry._active_skills,
                }
                for s in skills
            ],
            "count": len(skills),
        }

    def get_state(self) -> Dict[str, Any]:
        """Get middleware state."""
        return {
            "registry": self._registry.get_state(),
            "auto_activate": self._auto_activate,
            "max_active_skills": self._max_active_skills,
            "injection_mode": self._injection_mode.value,
        }

    def load_state(self, state: Dict[str, Any]) -> None:
        """Load middleware state."""
        if "registry" in state:
            self._registry.load_state(state["registry"])
        self._auto_activate = state.get("auto_activate", self._auto_activate)
        self._max_active_skills = state.get("max_active_skills", self._max_active_skills)

        # Load injection mode
        mode_value = state.get("injection_mode")
        if mode_value:
            try:
                self._injection_mode = SkillInjectionMode(mode_value)
            except ValueError:
                pass  # Keep default
