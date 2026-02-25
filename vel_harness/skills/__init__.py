"""
Vel Harness Skills

Procedural knowledge system for guiding agent behavior.
"""

from vel_harness.skills.loader import (
    DISCOVERY_MODE_ENTRYPOINT_ONLY,
    DISCOVERY_MODE_LEGACY_MARKDOWN_SCAN,
    Skill,
    SkillAsset,
    SkillParseError,
    load_skill,
    load_skill_inventory_from_directory,
    load_skills_from_directory,
    load_skills_from_directories,
    parse_frontmatter,
)
from vel_harness.skills.registry import SkillsRegistry

__all__ = [
    "Skill",
    "SkillAsset",
    "SkillParseError",
    "SkillsRegistry",
    "DISCOVERY_MODE_ENTRYPOINT_ONLY",
    "DISCOVERY_MODE_LEGACY_MARKDOWN_SCAN",
    "load_skill",
    "load_skill_inventory_from_directory",
    "load_skills_from_directory",
    "load_skills_from_directories",
    "parse_frontmatter",
]
