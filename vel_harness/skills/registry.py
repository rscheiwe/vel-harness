"""
Skills Registry

Manages loaded skills and provides lookup functionality.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from vel_harness.skills.loader import (
    DISCOVERY_MODE_ENTRYPOINT_ONLY,
    Skill,
    SkillAsset,
    load_skill,
    load_skill_inventory_from_directory,
)


class SkillsRegistry:
    """
    Registry for managing and looking up skills.

    Provides:
    - Skill loading from directories
    - Lookup by name, tag, or trigger
    - Automatic skill activation based on context
    - Active skill management
    """

    def __init__(
        self,
        skill_dirs: Optional[List[str]] = None,
        auto_load: bool = True,
        discovery_mode: str = DISCOVERY_MODE_ENTRYPOINT_ONLY,
    ) -> None:
        """
        Initialize skills registry.

        Args:
            skill_dirs: Directories to load skills from
            auto_load: Whether to load skills immediately
        """
        self._skills: Dict[str, Skill] = {}
        self._assets: List[SkillAsset] = []
        self._assets_by_skill: Dict[str, List[SkillAsset]] = {}
        self._ambiguous_skills: Dict[str, List[Skill]] = {}
        self._active_skills: Set[str] = set()
        self._skill_dirs = [Path(d) for d in (skill_dirs or [])]
        self._discovery_mode = discovery_mode

        if auto_load and self._skill_dirs:
            self.load_from_directories()

    @property
    def skills(self) -> List[Skill]:
        """Get all loaded skills."""
        return list(self._skills.values())

    @property
    def enabled_skills(self) -> List[Skill]:
        """Get all enabled skills."""
        return [s for s in self._skills.values() if s.enabled]

    @property
    def assets(self) -> List[SkillAsset]:
        """Get all knowledge assets."""
        return list(self._assets)

    @property
    def active_skills(self) -> List[Skill]:
        """Get currently active skills."""
        return [self._skills[name] for name in self._active_skills if name in self._skills]

    def load_from_directories(self, directories: Optional[List[Path]] = None) -> int:
        """
        Load skills from directories.

        Args:
            directories: Directories to load from (uses configured dirs if None)

        Returns:
            Number of skills loaded
        """
        dirs = directories or self._skill_dirs
        if directories is None:
            self._skills = {}
            self._assets = []
            self._assets_by_skill = {}
            self._ambiguous_skills = {}
        loaded_count = 0
        for directory in dirs:
            skills, assets = load_skill_inventory_from_directory(
                directory,
                discovery_mode=self._discovery_mode,
            )
            for skill in skills:
                existing = self._skills.get(skill.name)
                if existing and existing.source_path != skill.source_path:
                    if skill.name not in self._ambiguous_skills:
                        self._ambiguous_skills[skill.name] = [existing, skill]
                    else:
                        self._ambiguous_skills[skill.name].append(skill)
                    continue
                self._skills[skill.name] = skill
                loaded_count += 1

            for asset in assets:
                self._assets.append(asset)
                if asset.skill_name:
                    self._assets_by_skill.setdefault(asset.skill_name, []).append(asset)

        return loaded_count

    def load_skill(self, path: str) -> Skill:
        """
        Load a single skill file.

        Args:
            path: Path to skill file

        Returns:
            Loaded skill
        """
        skill = load_skill(Path(path))
        self._skills[skill.name] = skill
        return skill

    def register_skill(self, skill: Skill) -> None:
        """
        Register a skill directly.

        Args:
            skill: Skill to register
        """
        self._skills[skill.name] = skill

    def unregister_skill(self, name: str) -> bool:
        """
        Unregister a skill by name.

        Args:
            name: Name of skill to unregister

        Returns:
            True if skill was found and removed
        """
        if name in self._skills:
            del self._skills[name]
            self._active_skills.discard(name)
            return True
        return False

    def get_skill(self, name: str) -> Optional[Skill]:
        """
        Get a skill by name.

        Args:
            name: Skill name

        Returns:
            Skill if found, None otherwise
        """
        return self._skills.get(name)

    def find_skills(
        self,
        query: Optional[str] = None,
        tags: Optional[List[str]] = None,
        enabled_only: bool = True,
    ) -> List[Skill]:
        """
        Find skills matching criteria.

        Args:
            query: Text query to match against name/description
            tags: Tags to filter by (any match)
            enabled_only: Only return enabled skills

        Returns:
            List of matching skills
        """
        results = []

        for skill in self._skills.values():
            if enabled_only and not skill.enabled:
                continue

            if query and not skill.matches_query(query):
                continue

            if tags:
                skill_tags_lower = [t.lower() for t in skill.tags]
                if not any(t.lower() in skill_tags_lower for t in tags):
                    continue

            results.append(skill)

        # Sort by priority
        results.sort(key=lambda s: (-s.priority, s.name))
        return results

    def find_by_trigger(self, text: str, enabled_only: bool = True) -> List[Skill]:
        """
        Find skills that match trigger patterns.

        Args:
            text: Text to match against triggers
            enabled_only: Only return enabled skills

        Returns:
            List of matching skills
        """
        results = []

        for skill in self._skills.values():
            if enabled_only and not skill.enabled:
                continue

            if skill.matches_triggers(text):
                results.append(skill)

        results.sort(key=lambda s: (-s.priority, s.name))
        return results

    def activate_skill(self, name: str) -> bool:
        """
        Mark a skill as active.

        Args:
            name: Skill name

        Returns:
            True if skill was found and activated
        """
        if name in self._ambiguous_skills:
            return False
        if name in self._skills and self._skills[name].enabled:
            self._active_skills.add(name)
            return True
        return False

    def get_activation_error(self, name: str) -> Optional[str]:
        """Return deterministic activation error if activation is blocked."""
        if name in self._ambiguous_skills:
            candidates = sorted(
                skill.source_path or "<unknown>"
                for skill in self._ambiguous_skills[name]
            )
            return (
                f"Skill '{name}' is ambiguous. "
                f"Candidate entrypoints: {candidates}"
            )
        if name not in self._skills:
            return f"Skill '{name}' not found"
        if not self._skills[name].enabled:
            return f"Skill '{name}' is disabled"
        return None

    def deactivate_skill(self, name: str) -> bool:
        """
        Mark a skill as inactive.

        Args:
            name: Skill name

        Returns:
            True if skill was active and deactivated
        """
        if name in self._active_skills:
            self._active_skills.discard(name)
            return True
        return False

    def activate_by_context(self, context: str) -> List[Skill]:
        """
        Automatically activate skills based on context.

        Args:
            context: Context text (e.g., user message, task description)

        Returns:
            List of newly activated skills
        """
        matching = self.find_by_trigger(context)
        newly_activated = []

        for skill in matching:
            if skill.name not in self._active_skills:
                self._active_skills.add(skill.name)
                newly_activated.append(skill)

        return newly_activated

    def get_active_prompt_segments(self) -> str:
        """
        Get combined prompt segments for all active skills.

        Returns:
            Combined markdown string
        """
        segments = []
        for skill in self.active_skills:
            segments.append(skill.to_prompt_segment())

        if not segments:
            return ""

        return "\n\n---\n\n".join(segments)

    def get_skill_content(self, name: str) -> str:
        """
        Get skill content formatted for tool_result injection.

        This follows the Claude Code pattern where skills are returned
        as tool_result (not injected into system prompt) to preserve
        Anthropic prompt caching.

        Args:
            name: Skill name

        Returns:
            Skill content wrapped in XML tags, or error message
        """
        if name not in self._skills:
            available = list(self._skills.keys())
            return f"Error: Skill '{name}' not found. Available skills: {available}"

        skill = self._skills[name]

        if not skill.enabled:
            return f"Error: Skill '{name}' is disabled."

        # Format as tool_result (this becomes part of conversation history)
        # The XML tags make it clear to the model this is loaded skill content
        return f"""<skill-loaded name="{name}">
{skill.content}
</skill-loaded>

Follow the instructions in the skill above."""

    def list_skills(self) -> List[Dict[str, Any]]:
        """
        List all skills with metadata.

        Returns:
            List of skill dictionaries
        """
        return [
            {
                **skill.to_dict(),
                "active": skill.name in self._active_skills,
            }
            for skill in self._skills.values()
        ]

    def list_skill_assets(self, skill_name: str) -> List[Dict[str, Any]]:
        """List knowledge assets associated with a skill."""
        return [asset.to_dict() for asset in self._assets_by_skill.get(skill_name, [])]

    def get_state(self) -> Dict[str, Any]:
        """Get registry state for persistence."""
        return {
            "skill_dirs": [str(d) for d in self._skill_dirs],
            "active_skills": list(self._active_skills),
            "discovery_mode": self._discovery_mode,
        }

    def load_state(self, state: Dict[str, Any]) -> None:
        """Load registry state from persistence."""
        self._skill_dirs = [Path(d) for d in state.get("skill_dirs", [])]
        self._active_skills = set(state.get("active_skills", []))
        self._discovery_mode = state.get("discovery_mode", self._discovery_mode)
        self._skills = {}
        self._assets = []
        self._assets_by_skill = {}
        self._ambiguous_skills = {}

        # Reload skills
        if self._skill_dirs:
            self.load_from_directories()
