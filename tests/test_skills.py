"""
Skills Tests

Tests for skills loader, registry, and middleware.
"""

import tempfile
from pathlib import Path

import pytest

from vel_harness.skills.loader import (
    Skill,
    SkillParseError,
    load_skill,
    load_skills_from_directory,
    parse_frontmatter,
)
from vel_harness.skills.registry import SkillsRegistry
from vel_harness.middleware.skills import SkillsMiddleware, SkillInjectionMode


# Sample skill content for testing
SAMPLE_SKILL_BASIC = """---
name: Data Analysis
description: Guide for analyzing datasets
tags:
  - data
  - analysis
triggers:
  - analyze data
  - data analysis
priority: 10
---

# Data Analysis Procedure

When analyzing data, follow these steps:

1. Load the dataset
2. Examine the structure
3. Check for missing values
4. Perform exploratory analysis
5. Generate insights
"""

SAMPLE_SKILL_MINIMAL = """
# Simple Guide

This is a minimal skill with no frontmatter.
Just plain markdown content.
"""

SAMPLE_SKILL_COMPLEX = """---
name: Research Workflow
description: Systematic research methodology
author: Test Author
version: "1.0"
tags:
  - research
  - methodology
triggers:
  - research*
  - investigate*
  - study*
requires:
  - web_search
  - file_system
priority: 20
enabled: true
---

# Research Workflow

## Phase 1: Planning
- Define research questions
- Identify sources

## Phase 2: Gathering
- Collect data
- Take notes

## Phase 3: Analysis
- Synthesize findings
- Draw conclusions
"""


# Fixtures


@pytest.fixture
def temp_skills_dir() -> Path:
    """Create a temporary directory with sample skills."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir)

        # Create sample skill files
        (skills_dir / "data_analysis.md").write_text(SAMPLE_SKILL_BASIC)
        (skills_dir / "simple_guide.md").write_text(SAMPLE_SKILL_MINIMAL)
        (skills_dir / "research.md").write_text(SAMPLE_SKILL_COMPLEX)

        # Create a subdirectory with more skills
        subdir = skills_dir / "advanced"
        subdir.mkdir()
        (subdir / "advanced_skill.md").write_text("""---
name: Advanced Skill
description: An advanced skill in subdirectory
tags:
  - advanced
---

Advanced content here.
""")

        yield skills_dir


@pytest.fixture
def registry(temp_skills_dir: Path) -> SkillsRegistry:
    """Create a registry with sample skills."""
    return SkillsRegistry(skill_dirs=[str(temp_skills_dir)])


@pytest.fixture
def skills_middleware(temp_skills_dir: Path) -> SkillsMiddleware:
    """Create skills middleware with sample skills."""
    return SkillsMiddleware(skill_dirs=[str(temp_skills_dir)])


@pytest.fixture
def tool_result_middleware(temp_skills_dir: Path) -> SkillsMiddleware:
    """Create middleware with TOOL_RESULT injection mode."""
    return SkillsMiddleware(
        skill_dirs=[str(temp_skills_dir)],
        auto_activate=False,
        injection_mode=SkillInjectionMode.TOOL_RESULT,
    )


# parse_frontmatter Tests


class TestParseFrontmatter:
    """Tests for frontmatter parsing."""

    def test_parse_with_frontmatter(self) -> None:
        """Test parsing content with frontmatter."""
        content = """---
name: Test
value: 123
---

Body content here.
"""
        meta, body = parse_frontmatter(content)

        assert meta["name"] == "Test"
        assert meta["value"] == 123
        assert body == "Body content here."

    def test_parse_without_frontmatter(self) -> None:
        """Test parsing content without frontmatter."""
        content = "Just plain markdown."
        meta, body = parse_frontmatter(content)

        assert meta == {}
        assert body == "Just plain markdown."

    def test_parse_empty_frontmatter(self) -> None:
        """Test parsing with empty frontmatter."""
        content = """---
---

Content after empty frontmatter.
"""
        meta, body = parse_frontmatter(content)

        assert meta == {}
        assert "Content after empty frontmatter" in body


# Skill Tests


class TestSkill:
    """Tests for Skill dataclass."""

    def test_matches_query_name(self) -> None:
        """Test query matching on name."""
        skill = Skill(name="Data Analysis", description="", content="")

        assert skill.matches_query("data") is True
        assert skill.matches_query("analysis") is True
        assert skill.matches_query("unknown") is False

    def test_matches_query_description(self) -> None:
        """Test query matching on description."""
        skill = Skill(name="Test", description="Guide for research", content="")

        assert skill.matches_query("research") is True
        assert skill.matches_query("guide") is True

    def test_matches_query_tags(self) -> None:
        """Test query matching on tags."""
        skill = Skill(name="Test", description="", content="", tags=["python", "data"])

        assert skill.matches_query("python") is True
        assert skill.matches_query("data") is True

    def test_matches_triggers_exact(self) -> None:
        """Test exact trigger matching."""
        skill = Skill(
            name="Test",
            description="",
            content="",
            triggers=["analyze data", "run analysis"],
        )

        assert skill.matches_triggers("please analyze data") is True
        assert skill.matches_triggers("run analysis now") is True
        assert skill.matches_triggers("something else") is False

    def test_matches_triggers_glob(self) -> None:
        """Test glob pattern trigger matching."""
        skill = Skill(
            name="Test",
            description="",
            content="",
            triggers=["research*", "*analysis*"],
        )

        assert skill.matches_triggers("research project") is True
        assert skill.matches_triggers("do research") is True
        assert skill.matches_triggers("data analysis report") is True

    def test_to_prompt_segment(self) -> None:
        """Test converting skill to prompt segment."""
        skill = Skill(
            name="Test Skill",
            description="A test skill",
            content="# Instructions\n\nDo the thing.",
        )

        segment = skill.to_prompt_segment()

        assert "## Skill: Test Skill" in segment
        assert "*A test skill*" in segment
        assert "# Instructions" in segment

    def test_to_dict(self) -> None:
        """Test converting skill to dictionary."""
        skill = Skill(
            name="Test",
            description="Desc",
            content="Content",
            tags=["a", "b"],
            priority=5,
        )

        d = skill.to_dict()

        assert d["name"] == "Test"
        assert d["description"] == "Desc"
        assert d["tags"] == ["a", "b"]
        assert d["priority"] == 5
        assert d["content_length"] == 7


# load_skill Tests


class TestLoadSkill:
    """Tests for loading skills from files."""

    def test_load_skill_with_frontmatter(self, temp_skills_dir: Path) -> None:
        """Test loading skill with frontmatter."""
        skill = load_skill(temp_skills_dir / "data_analysis.md")

        assert skill.name == "Data Analysis"
        assert skill.description == "Guide for analyzing datasets"
        assert "data" in skill.tags
        assert "analyze data" in skill.triggers
        assert skill.priority == 10

    def test_load_skill_minimal(self, temp_skills_dir: Path) -> None:
        """Test loading skill without frontmatter."""
        skill = load_skill(temp_skills_dir / "simple_guide.md")

        # Name should be derived from filename
        assert "Simple" in skill.name or "guide" in skill.name.lower()
        assert "Simple Guide" in skill.content

    def test_load_skill_complex(self, temp_skills_dir: Path) -> None:
        """Test loading complex skill with all metadata."""
        skill = load_skill(temp_skills_dir / "research.md")

        assert skill.name == "Research Workflow"
        assert skill.author == "Test Author"
        assert skill.version == "1.0"
        assert "web_search" in skill.requires
        assert skill.priority == 20

    def test_load_nonexistent_skill(self, temp_skills_dir: Path) -> None:
        """Test loading a skill that doesn't exist."""
        with pytest.raises(SkillParseError):
            load_skill(temp_skills_dir / "nonexistent.md")


# load_skills_from_directory Tests


class TestLoadSkillsFromDirectory:
    """Tests for loading skills from directory."""

    def test_load_all_skills(self, temp_skills_dir: Path) -> None:
        """Test loading all skills from directory."""
        skills = load_skills_from_directory(temp_skills_dir)

        assert len(skills) >= 3
        names = [s.name for s in skills]
        assert "Data Analysis" in names
        assert "Research Workflow" in names

    def test_load_recursive(self, temp_skills_dir: Path) -> None:
        """Test recursive loading includes subdirectories."""
        skills = load_skills_from_directory(temp_skills_dir, recursive=True)

        names = [s.name for s in skills]
        assert "Advanced Skill" in names

    def test_load_non_recursive(self, temp_skills_dir: Path) -> None:
        """Test non-recursive loading excludes subdirectories."""
        skills = load_skills_from_directory(temp_skills_dir, recursive=False)

        names = [s.name for s in skills]
        assert "Advanced Skill" not in names

    def test_skills_sorted_by_priority(self, temp_skills_dir: Path) -> None:
        """Test that skills are sorted by priority."""
        skills = load_skills_from_directory(temp_skills_dir)

        # Higher priority should come first
        priorities = [s.priority for s in skills]
        assert priorities == sorted(priorities, reverse=True)


# SkillsRegistry Tests


class TestSkillsRegistry:
    """Tests for SkillsRegistry."""

    def test_registry_loads_skills(self, registry: SkillsRegistry) -> None:
        """Test that registry loads skills on init."""
        assert len(registry.skills) >= 3

    def test_get_skill(self, registry: SkillsRegistry) -> None:
        """Test getting skill by name."""
        skill = registry.get_skill("Data Analysis")

        assert skill is not None
        assert skill.name == "Data Analysis"

    def test_get_nonexistent_skill(self, registry: SkillsRegistry) -> None:
        """Test getting nonexistent skill."""
        skill = registry.get_skill("Nonexistent")
        assert skill is None

    def test_find_skills_by_query(self, registry: SkillsRegistry) -> None:
        """Test finding skills by query."""
        skills = registry.find_skills(query="data")

        assert len(skills) >= 1
        assert any(s.name == "Data Analysis" for s in skills)

    def test_find_skills_by_tags(self, registry: SkillsRegistry) -> None:
        """Test finding skills by tags."""
        skills = registry.find_skills(tags=["research"])

        assert len(skills) >= 1
        assert any(s.name == "Research Workflow" for s in skills)

    def test_find_by_trigger(self, registry: SkillsRegistry) -> None:
        """Test finding skills by trigger."""
        skills = registry.find_by_trigger("analyze data")

        assert len(skills) >= 1
        assert any(s.name == "Data Analysis" for s in skills)

    def test_activate_deactivate(self, registry: SkillsRegistry) -> None:
        """Test activating and deactivating skills."""
        assert registry.activate_skill("Data Analysis") is True
        assert "Data Analysis" in [s.name for s in registry.active_skills]

        assert registry.deactivate_skill("Data Analysis") is True
        assert "Data Analysis" not in [s.name for s in registry.active_skills]

    def test_activate_by_context(self, registry: SkillsRegistry) -> None:
        """Test automatic activation by context."""
        activated = registry.activate_by_context("I need to analyze data")

        assert len(activated) >= 1
        assert any(s.name == "Data Analysis" for s in activated)

    def test_get_active_prompt_segments(self, registry: SkillsRegistry) -> None:
        """Test getting prompt segments for active skills."""
        registry.activate_skill("Data Analysis")

        segment = registry.get_active_prompt_segments()

        assert "Data Analysis" in segment
        assert "Procedure" in segment

    def test_state_persistence(self, registry: SkillsRegistry) -> None:
        """Test state persistence."""
        registry.activate_skill("Data Analysis")
        state = registry.get_state()

        assert "Data Analysis" in state["active_skills"]


# SkillsMiddleware Tests


class TestSkillsMiddleware:
    """Tests for SkillsMiddleware."""

    def test_get_tools(self, skills_middleware: SkillsMiddleware) -> None:
        """Test that middleware returns expected tools."""
        tools = skills_middleware.get_tools()
        tool_names = [t.name for t in tools]

        assert "list_skills" in tool_names
        assert "activate_skill" in tool_names
        assert "deactivate_skill" in tool_names
        assert "get_skill" in tool_names
        assert "search_skills" in tool_names

    def test_tool_categories(self, skills_middleware: SkillsMiddleware) -> None:
        """Test that tools have correct categories."""
        tools = skills_middleware.get_tools()

        for tool in tools:
            assert tool.category == "skills"

    def test_list_skills(self, skills_middleware: SkillsMiddleware) -> None:
        """Test listing skills."""
        result = skills_middleware._list_skills()

        assert "skills" in result
        assert result["total"] >= 3

    def test_activate_skill(self, skills_middleware: SkillsMiddleware) -> None:
        """Test activating skill via middleware."""
        result = skills_middleware._activate_skill("Data Analysis")

        assert result["status"] == "loaded"
        assert result["skill"] == "Data Analysis"

    def test_activate_nonexistent(self, skills_middleware: SkillsMiddleware) -> None:
        """Test activating nonexistent skill."""
        result = skills_middleware._activate_skill("Nonexistent")

        assert "error" in result

    def test_deactivate_skill(self, skills_middleware: SkillsMiddleware) -> None:
        """Test deactivating skill via middleware."""
        skills_middleware._activate_skill("Data Analysis")
        result = skills_middleware._deactivate_skill("Data Analysis")

        assert result["status"] == "deactivated"

    def test_get_skill(self, skills_middleware: SkillsMiddleware) -> None:
        """Test getting skill content."""
        result = skills_middleware._get_skill("Data Analysis")

        assert result["name"] == "Data Analysis"
        assert "content" in result
        assert "Procedure" in result["content"]

    def test_search_skills(self, skills_middleware: SkillsMiddleware) -> None:
        """Test searching skills."""
        result = skills_middleware._search_skills("research")

        assert result["count"] >= 1
        assert any(r["name"] == "Research Workflow" for r in result["results"])

    def test_system_prompt_segment(self, skills_middleware: SkillsMiddleware) -> None:
        """Test system prompt content."""
        segment = skills_middleware.get_system_prompt_segment()

        assert "Skills System" in segment
        assert "list_skills" in segment

    def test_process_context(self, skills_middleware: SkillsMiddleware) -> None:
        """Test context processing for auto-activation."""
        activated = skills_middleware.process_context("Let's analyze data")

        assert "Data Analysis" in activated

    def test_state_persistence(self, skills_middleware: SkillsMiddleware) -> None:
        """Test middleware state persistence."""
        skills_middleware._activate_skill("Data Analysis")
        state = skills_middleware.get_state()

        assert "registry" in state
        assert "auto_activate" in state


# Integration Tests


class TestSkillsIntegration:
    """Integration tests for skills system."""

    def test_full_workflow(self, skills_middleware: SkillsMiddleware) -> None:
        """Test complete skills workflow."""
        # List available skills
        skills = skills_middleware._list_skills()
        assert skills["total"] >= 3

        # Search for relevant skill
        search_result = skills_middleware._search_skills("data")
        assert search_result["count"] >= 1

        # Activate skill
        activate_result = skills_middleware._activate_skill("Data Analysis")
        assert activate_result["status"] == "loaded"

        # Get skill content
        skill_content = skills_middleware._get_skill("Data Analysis")
        assert "Procedure" in skill_content["content"]

        # Check system prompt includes active skill
        segment = skills_middleware.get_system_prompt_segment()
        assert "Data Analysis" in segment

        # Deactivate skill
        deactivate_result = skills_middleware._deactivate_skill("Data Analysis")
        assert deactivate_result["status"] == "deactivated"

    def test_auto_activation_workflow(self, skills_middleware: SkillsMiddleware) -> None:
        """Test automatic skill activation."""
        # Process context that should trigger skill
        activated = skills_middleware.process_context(
            "I need to research and investigate this topic"
        )

        # Should activate research-related skill
        assert "Research Workflow" in activated

        # Skill should now be active
        active = skills_middleware._list_skills(active_only=True)
        assert any(s["name"] == "Research Workflow" for s in active["skills"])


# Skill Injection Mode Tests


class TestSkillInjectionModes:
    """Tests for skill injection modes (TOOL_RESULT vs SYSTEM_PROMPT)."""

    @pytest.fixture
    def tool_result_middleware(self, temp_skills_dir: Path) -> SkillsMiddleware:
        """Create middleware with TOOL_RESULT injection mode."""
        return SkillsMiddleware(
            skill_dirs=[str(temp_skills_dir)],
            auto_activate=False,
            injection_mode=SkillInjectionMode.TOOL_RESULT,
        )

    @pytest.fixture
    def system_prompt_middleware(self, temp_skills_dir: Path) -> SkillsMiddleware:
        """Create middleware with SYSTEM_PROMPT injection mode."""
        return SkillsMiddleware(
            skill_dirs=[str(temp_skills_dir)],
            auto_activate=False,
            injection_mode=SkillInjectionMode.SYSTEM_PROMPT,
        )

    def test_tool_result_mode_returns_content(
        self, tool_result_middleware: SkillsMiddleware
    ) -> None:
        """Test that TOOL_RESULT mode returns skill content in response."""
        result = tool_result_middleware._activate_skill("Data Analysis")

        assert result["status"] == "loaded"
        assert "content" in result
        assert "<skill-loaded" in result["content"]
        assert "Data Analysis" in result["content"]
        assert "Follow the instructions" in result["content"]

    def test_system_prompt_mode_no_content(
        self, system_prompt_middleware: SkillsMiddleware
    ) -> None:
        """Test that SYSTEM_PROMPT mode doesn't return content."""
        result = system_prompt_middleware._activate_skill("Data Analysis")

        assert result["status"] == "activated"
        assert "content" not in result
        assert "note" in result  # Has a note about system prompt

    def test_tool_result_mode_system_prompt_no_content(
        self, tool_result_middleware: SkillsMiddleware
    ) -> None:
        """Test that TOOL_RESULT mode keeps system prompt clean."""
        tool_result_middleware._activate_skill("Data Analysis")

        segment = tool_result_middleware.get_system_prompt_segment()

        # Should list available skills but NOT include content
        assert "Skills System" in segment
        assert "activate_skill" in segment
        # Should NOT include the full skill content
        assert "Procedure" not in segment  # This is from skill content

    def test_system_prompt_mode_includes_content(
        self, system_prompt_middleware: SkillsMiddleware
    ) -> None:
        """Test that SYSTEM_PROMPT mode includes content in prompt."""
        system_prompt_middleware._activate_skill("Data Analysis")

        segment = system_prompt_middleware.get_system_prompt_segment()

        # Should include active skill content
        assert "Active Skills" in segment
        assert "Procedure" in segment  # This is from skill content


class TestSkillContentMethod:
    """Tests for get_skill_content method on registry."""

    def test_get_skill_content_format(self, registry: SkillsRegistry) -> None:
        """Test skill content is properly formatted."""
        content = registry.get_skill_content("Data Analysis")

        assert "<skill-loaded" in content
        assert 'name="Data Analysis"' in content
        assert "</skill-loaded>" in content
        assert "Follow the instructions" in content

    def test_get_skill_content_nonexistent(self, registry: SkillsRegistry) -> None:
        """Test getting content for nonexistent skill."""
        content = registry.get_skill_content("Nonexistent")

        assert "Error:" in content
        assert "not found" in content

    def test_get_skill_content_includes_original(self, registry: SkillsRegistry) -> None:
        """Test that skill content includes original markdown."""
        content = registry.get_skill_content("Data Analysis")

        # Should include original skill content
        assert "Data Analysis Procedure" in content or "analyze" in content.lower()


class TestSkillInjectionModeState:
    """Tests for skill injection mode state persistence."""

    def test_state_includes_injection_mode(
        self, tool_result_middleware: SkillsMiddleware
    ) -> None:
        """Test that state includes injection mode."""
        state = tool_result_middleware.get_state()

        assert "injection_mode" in state
        assert state["injection_mode"] == "tool_result"

    def test_load_state_with_injection_mode(
        self, tool_result_middleware: SkillsMiddleware
    ) -> None:
        """Test loading state with injection mode."""
        state = {
            "injection_mode": "system_prompt",
            "auto_activate": True,
            "max_active_skills": 3,
        }

        tool_result_middleware.load_state(state)

        assert tool_result_middleware._injection_mode == SkillInjectionMode.SYSTEM_PROMPT
        assert tool_result_middleware._auto_activate is True
