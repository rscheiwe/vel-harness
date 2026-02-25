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


DISCOVERY_MODE_ENTRYPOINT_ONLY = "entrypoint_only"
DISCOVERY_MODE_LEGACY_MARKDOWN_SCAN = "legacy_markdown_scan"
_SKIP_SKILL_FILENAMES = {"readme.md", "changelog.md", "license.md"}


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
    kind: str = "skill"
    entrypoint: bool = True

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
            "kind": self.kind,
            "entrypoint": self.entrypoint,
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


@dataclass
class SkillAsset:
    """Reference document associated with a skill package."""

    name: str
    source_path: str
    skill_name: Optional[str] = None
    description: str = ""
    tags: List[str] = field(default_factory=list)
    kind: str = "knowledge_asset"
    entrypoint: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "source_path": self.source_path,
            "skill_name": self.skill_name,
            "description": self.description,
            "tags": self.tags,
            "kind": self.kind,
            "entrypoint": self.entrypoint,
        }


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
        # Use parent directory for SKILL.md entrypoints, otherwise filename.
        if path.stem.lower() == "skill":
            name = path.parent.name.replace("_", " ").replace("-", " ").title()
        else:
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
        kind="skill",
        entrypoint=_is_entrypoint_skill(path, frontmatter),
    )


def _is_hidden_path(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)


def _iter_markdown_files(directory: Path, recursive: bool = True) -> List[Path]:
    if not directory.exists():
        return []
    glob_method = directory.rglob if recursive else directory.glob
    files: List[Path] = []
    for path in glob_method("*.md"):
        if _is_hidden_path(path):
            continue
        files.append(path)
    return files


def _is_frontmatter_skill(frontmatter: Dict[str, Any]) -> bool:
    kind = str(frontmatter.get("kind", "")).strip().lower()
    if kind != "skill":
        return False
    name = frontmatter.get("name")
    description = frontmatter.get("description")
    return bool(name and description)


def _is_entrypoint_skill(path: Path, frontmatter: Dict[str, Any]) -> bool:
    if path.name == "SKILL.md":
        return True
    return _is_frontmatter_skill(frontmatter)


def _discover_skill_paths(
    files: List[Path],
    discovery_mode: str,
) -> List[Path]:
    skill_paths: List[Path] = []
    for path in files:
        if path.name.lower() in _SKIP_SKILL_FILENAMES:
            continue
        if discovery_mode == DISCOVERY_MODE_LEGACY_MARKDOWN_SCAN:
            skill_paths.append(path)
            continue

        try:
            content = path.read_text(encoding="utf-8")
            frontmatter, _ = parse_frontmatter(content)
        except Exception:
            frontmatter = {}

        if _is_entrypoint_skill(path, frontmatter):
            skill_paths.append(path)

    return skill_paths


def _find_parent_skill_name(path: Path, skill_roots: Dict[Path, str]) -> Optional[str]:
    best_match: Optional[Path] = None
    for root in skill_roots:
        try:
            path.relative_to(root)
        except ValueError:
            continue
        if best_match is None or len(root.parts) > len(best_match.parts):
            best_match = root
    if best_match is None:
        return None
    return skill_roots[best_match]


def load_skill_inventory_from_directory(
    directory: Path,
    recursive: bool = True,
    discovery_mode: str = DISCOVERY_MODE_ENTRYPOINT_ONLY,
) -> tuple[List[Skill], List[SkillAsset]]:
    """Load skills and reference assets from a directory."""
    files = _iter_markdown_files(directory, recursive=recursive)
    if not files:
        return [], []

    skill_paths = set(_discover_skill_paths(files, discovery_mode))
    skills: List[Skill] = []
    skill_roots: Dict[Path, str] = {}

    for path in skill_paths:
        try:
            skill = load_skill(path)
            skills.append(skill)
            if skill.entrypoint:
                skill_roots[path.parent] = skill.name
        except SkillParseError:
            continue

    assets: List[SkillAsset] = []
    for path in files:
        if path in skill_paths:
            continue

        description = ""
        name = path.stem.replace("_", " ").replace("-", " ").title()
        tags: List[str] = []

        try:
            content = path.read_text(encoding="utf-8")
            frontmatter, _ = parse_frontmatter(content)
            if isinstance(frontmatter.get("name"), str) and frontmatter["name"].strip():
                name = frontmatter["name"].strip()
            if isinstance(frontmatter.get("description"), str):
                description = frontmatter["description"]
            frontmatter_tags = frontmatter.get("tags", [])
            if isinstance(frontmatter_tags, str):
                frontmatter_tags = [frontmatter_tags]
            if isinstance(frontmatter_tags, list):
                tags = [str(tag) for tag in frontmatter_tags]
        except Exception:
            pass

        assets.append(
            SkillAsset(
                name=name,
                source_path=str(path),
                skill_name=_find_parent_skill_name(path, skill_roots),
                description=description,
                tags=tags,
            )
        )

    skills.sort(key=lambda s: (-s.priority, s.name))
    assets.sort(key=lambda a: (a.skill_name or "", a.name, a.source_path))
    return skills, assets


def load_skills_from_directory(
    directory: Path,
    pattern: str = "*.md",
    recursive: bool = True,
    discovery_mode: str = DISCOVERY_MODE_ENTRYPOINT_ONLY,
) -> List[Skill]:
    """
    Load all skills from a directory.

    Args:
        directory: Directory containing skill files
        pattern: Glob pattern for skill files (kept for compatibility)
        recursive: Whether to search recursively
        discovery_mode: Skill discovery mode

    Returns:
        List of loaded skills
    """
    _ = pattern  # compatibility with existing API
    skills, _assets = load_skill_inventory_from_directory(
        directory=directory,
        recursive=recursive,
        discovery_mode=discovery_mode,
    )
    return skills


def load_skills_from_directories(
    directories: List[Path],
    pattern: str = "*.md",
    recursive: bool = True,
    discovery_mode: str = DISCOVERY_MODE_ENTRYPOINT_ONLY,
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
        skills = load_skills_from_directory(directory, pattern, recursive, discovery_mode)
        for skill in skills:
            # Later directories override earlier ones
            all_skills[skill.name] = skill

    # Convert back to list and sort
    result = list(all_skills.values())
    result.sort(key=lambda s: (-s.priority, s.name))

    return result
