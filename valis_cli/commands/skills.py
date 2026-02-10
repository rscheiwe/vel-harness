"""
Skills Command

List and manage available skills.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from valis_cli.commands.base import Command, CommandResult


class SkillsCommand(Command):
    """List and manage skills."""

    name = "skills"
    description = "List available skills"
    usage = "/skills [--verbose]"

    async def execute(
        self,
        args: list[str],
        context: Dict[str, Any],
    ) -> CommandResult:
        """
        Execute skills command.

        Args:
            args: Command arguments
            context: Execution context

        Returns:
            CommandResult with skill listing
        """
        verbose = "--verbose" in args or "-v" in args

        config = context.get("config")
        if config is None:
            return CommandResult(
                success=False,
                message="No configuration available",
            )

        skills = []

        # Check global skills
        if config.skills_dir.exists():
            skills.extend(self._scan_skills_dir(config.skills_dir, "global"))

        # Check project skills
        if config.project_dir:
            project_skills = config.project_dir / "skills"
            if project_skills.exists():
                skills.extend(self._scan_skills_dir(project_skills, "project"))

        if not skills:
            return CommandResult(
                success=True,
                message="No skills found.",
                data={"skills": []},
            )

        # Format output
        lines = ["Available Skills:", ""]

        for skill in skills:
            if verbose:
                lines.append(f"  {skill['name']} ({skill['scope']})")
                lines.append(f"    Path: {skill['path']}")
                if skill.get("description"):
                    lines.append(f"    Description: {skill['description']}")
                lines.append("")
            else:
                lines.append(f"  - {skill['name']}")

        return CommandResult(
            success=True,
            message="\n".join(lines),
            data={"skills": skills},
        )

    def _scan_skills_dir(
        self,
        skills_dir: Path,
        scope: str,
    ) -> List[Dict[str, Any]]:
        """Scan a skills directory for skill files."""
        skills = []

        for path in skills_dir.iterdir():
            if path.is_file() and path.suffix in (".py", ".yaml", ".yml", ".md"):
                skill_info = {
                    "name": path.stem,
                    "path": str(path),
                    "scope": scope,
                    "type": path.suffix[1:],
                }

                # Try to extract description
                if path.suffix == ".md":
                    try:
                        content = path.read_text()
                        # First non-empty line after title
                        lines = content.strip().split("\n")
                        for i, line in enumerate(lines):
                            if line.startswith("#"):
                                continue
                            if line.strip():
                                skill_info["description"] = line.strip()[:100]
                                break
                    except Exception:
                        pass

                skills.append(skill_info)

        return sorted(skills, key=lambda s: s["name"])


class SkillInfoCommand(Command):
    """Show detailed skill information."""

    name = "skill"
    description = "Show skill details"
    usage = "/skill <name>"

    async def execute(
        self,
        args: list[str],
        context: Dict[str, Any],
    ) -> CommandResult:
        """Execute skill info command."""
        if not args:
            return CommandResult(
                success=False,
                message="Usage: /skill <name>",
            )

        skill_name = args[0]
        config = context.get("config")

        if config is None:
            return CommandResult(
                success=False,
                message="No configuration available",
            )

        # Search for skill
        skill_path = None

        # Check project skills first
        if config.project_dir:
            project_skills = config.project_dir / "skills"
            for ext in (".py", ".yaml", ".yml", ".md"):
                candidate = project_skills / f"{skill_name}{ext}"
                if candidate.exists():
                    skill_path = candidate
                    break

        # Check global skills
        if skill_path is None and config.skills_dir.exists():
            for ext in (".py", ".yaml", ".yml", ".md"):
                candidate = config.skills_dir / f"{skill_name}{ext}"
                if candidate.exists():
                    skill_path = candidate
                    break

        if skill_path is None:
            return CommandResult(
                success=False,
                message=f"Skill not found: {skill_name}",
            )

        # Read and display skill content
        try:
            content = skill_path.read_text()
            return CommandResult(
                success=True,
                message=f"Skill: {skill_name}\nPath: {skill_path}\n\n{content[:2000]}",
                data={"name": skill_name, "path": str(skill_path), "content": content},
            )
        except Exception as e:
            return CommandResult(
                success=False,
                message=f"Error reading skill: {e}",
            )
