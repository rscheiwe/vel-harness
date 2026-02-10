"""
Skills Loader

Parses and loads SKILL.md files that provide procedural knowledge to agents.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


class SkillParseError(Exception):
    """Raised when a skill file cannot be parsed."""

    pass


@dataclass
class Skill:
    """
    A loaded skill with metadata and content.

    Skills are procedural knowledge documents that guide agent behavior
    for specific domains or tasks.
    """

    name: str
    description: str
    content: str
    triggers: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    priority: int = 0
    enabled: bool = True
    source_path: Optional[str] = None

    # Optional metadata
    author: Optional[str] = None
    version: Optional[str] = None
    requires: List[str] = field(default_factory=list)

    def matches_query(self, query: str) -> bool:
        """
        Check if this skill matches a search query.

        Args:
            query: Search query (case-insensitive)

        Returns:
            True if skill matches the query
        """
        query_lower = query.lower()

        # Check name
        if query_lower in self.name.lower():
            return True

        # Check description
        if query_lower in self.description.lower():
            return True

        # Check triggers
        for trigger in self.triggers:
            if query_lower in trigger.lower():
                return True

        # Check tags
        for tag in self.tags:
            if query_lower in tag.lower():
                return True

        return False

    def matches_triggers(self, text: str) -> bool:
        """
        Check if text matches any trigger patterns.

        Args:
            text: Text to match against triggers

        Returns:
            True if any trigger matches
        """
        text_lower = text.lower()

        for trigger in self.triggers:
            # Support simple glob patterns
            if "*" in trigger:
                pattern = trigger.lower().replace("*", ".*")
                if re.search(pattern, text_lower):
                    return True
            elif trigger.lower() in text_lower:
                return True

        return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert skill to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "triggers": self.triggers,
            "tags": self.tags,
            "priority": self.priority,
            "enabled": self.enabled,
            "content_length": len(self.content),
            "source_path": self.source_path,
        }

    def to_prompt_segment(self) -> str:
        """
        Format skill as a system prompt segment.

        Returns:
            Formatted markdown string for inclusion in system prompt
        """
        lines = [
            f"## Skill: {self.name}",
            "",
            f"*{self.description}*",
            "",
            self.content,
        ]
        return "\n".join(lines)


def parse_frontmatter(content: str) -> tuple[Dict[str, Any], str]:
    """
    Parse YAML frontmatter from markdown content.

    Args:
        content: Full markdown content with optional frontmatter

    Returns:
        Tuple of (frontmatter_dict, body_content)
    """
    # Check for frontmatter delimiter
    if not content.startswith("---"):
        return {}, content

    # Find end of frontmatter
    end_match = re.search(r"\n---\s*\n", content[3:])
    if not end_match:
        return {}, content

    frontmatter_str = content[3 : end_match.start() + 3]
    body = content[end_match.end() + 3 :]

    try:
        frontmatter = yaml.safe_load(frontmatter_str) or {}
    except yaml.YAMLError as e:
        raise SkillParseError(f"Invalid YAML frontmatter: {e}")

    return frontmatter, body.strip()


def load_skill(path: Path) -> Skill:
    """
    Load a skill from a SKILL.md file.

    Args:
        path: Path to the skill file

    Returns:
        Loaded Skill instance

    Raises:
        SkillParseError: If file cannot be parsed
    """
    if not path.exists():
        raise SkillParseError(f"Skill file not found: {path}")

    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        raise SkillParseError(f"Cannot read skill file {path}: {e}")

    frontmatter, body = parse_frontmatter(content)

    # Extract required fields
    name = frontmatter.get("name")
    if not name:
        # Use filename as fallback
        name = path.stem.replace("_", " ").replace("-", " ").title()
        if name.lower().endswith(" skill"):
            name = name[:-6]

    description = frontmatter.get("description", "")

    # Extract optional fields
    triggers = frontmatter.get("triggers", [])
    if isinstance(triggers, str):
        triggers = [triggers]

    tags = frontmatter.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]

    priority = frontmatter.get("priority", 0)
    enabled = frontmatter.get("enabled", True)
    author = frontmatter.get("author")
    version = frontmatter.get("version")

    requires = frontmatter.get("requires", [])
    if isinstance(requires, str):
        requires = [requires]

    return Skill(
        name=name,
        description=description,
        content=body,
        triggers=triggers,
        tags=tags,
        priority=priority,
        enabled=enabled,
        source_path=str(path),
        author=author,
        version=version,
        requires=requires,
    )


def load_skills_from_directory(
    directory: Path,
    pattern: str = "*.md",
    recursive: bool = True,
) -> List[Skill]:
    """
    Load all skills from a directory.

    Args:
        directory: Directory containing skill files
        pattern: Glob pattern for skill files
        recursive: Whether to search recursively

    Returns:
        List of loaded skills
    """
    if not directory.exists():
        return []

    skills = []
    glob_method = directory.rglob if recursive else directory.glob

    for path in glob_method(pattern):
        # Skip hidden files and directories
        if any(part.startswith(".") for part in path.parts):
            continue

        # Skip non-skill files (e.g., README.md)
        if path.name.lower() in ["readme.md", "changelog.md", "license.md"]:
            continue

        try:
            skill = load_skill(path)
            skills.append(skill)
        except SkillParseError:
            # Skip files that can't be parsed as skills
            continue

    # Sort by priority (higher first), then name
    skills.sort(key=lambda s: (-s.priority, s.name))

    return skills


def load_skills_from_directories(
    directories: List[Path],
    pattern: str = "*.md",
    recursive: bool = True,
) -> List[Skill]:
    """
    Load skills from multiple directories.

    Args:
        directories: List of directories to search
        pattern: Glob pattern for skill files
        recursive: Whether to search recursively

    Returns:
        List of loaded skills (deduplicated by name)
    """
    all_skills: Dict[str, Skill] = {}

    for directory in directories:
        skills = load_skills_from_directory(directory, pattern, recursive)
        for skill in skills:
            # Later directories override earlier ones
            all_skills[skill.name] = skill

    # Convert back to list and sort
    result = list(all_skills.values())
    result.sort(key=lambda s: (-s.priority, s.name))

    return result
