"""
Tests for valis_cli.config
"""

import json
import tempfile
from pathlib import Path

import pytest

from valis_cli.config import (
    ApprovalSettings,
    Config,
    ModelSettings,
    detect_project_dir,
    get_config,
    init_project,
)


class TestModelSettings:
    """Tests for ModelSettings."""

    def test_default_values(self):
        """Test default model settings."""
        settings = ModelSettings()
        assert settings.provider == "anthropic"
        assert settings.model == "claude-sonnet-4-5-20250929"
        assert settings.temperature is None
        assert settings.max_tokens is None

    def test_to_dict(self):
        """Test conversion to dict."""
        settings = ModelSettings(
            provider="openai",
            model="gpt-4o",
            temperature=0.7,
        )
        d = settings.to_dict()
        assert d["provider"] == "openai"
        assert d["model"] == "gpt-4o"
        assert d["temperature"] == 0.7
        assert "max_tokens" not in d

    def test_from_dict(self):
        """Test creation from dict."""
        settings = ModelSettings.from_dict({
            "provider": "anthropic",
            "model": "claude-3-opus",
            "max_tokens": 4096,
        })
        assert settings.provider == "anthropic"
        assert settings.model == "claude-3-opus"
        assert settings.max_tokens == 4096


class TestApprovalSettings:
    """Tests for ApprovalSettings."""

    def test_default_auto_approve(self):
        """Test default auto-approve list."""
        settings = ApprovalSettings()
        assert settings.require_approval is True
        assert "read_file" in settings.auto_approve
        assert "ls" in settings.auto_approve
        assert len(settings.always_deny) == 0

    def test_custom_approval_settings(self):
        """Test custom approval settings."""
        settings = ApprovalSettings(
            require_approval=False,
            auto_approve=["custom_tool"],
            always_deny=["dangerous_tool"],
        )
        assert settings.require_approval is False
        assert settings.auto_approve == ["custom_tool"]
        assert settings.always_deny == ["dangerous_tool"]


class TestConfig:
    """Tests for Config."""

    def test_default_config(self):
        """Test default configuration."""
        config = Config()
        assert config.global_dir == Path.home() / ".valis"
        assert config.project_dir is None
        assert config.agent_name == "valis-agent"
        assert config.max_turns == 50

    def test_derived_paths(self):
        """Test derived path properties."""
        with tempfile.TemporaryDirectory() as tmpdir:
            global_dir = Path(tmpdir) / "global"
            global_dir.mkdir()
            (global_dir / "memories").mkdir()
            (global_dir / "skills").mkdir()

            config = Config(global_dir=global_dir)
            config.ensure_dirs()

            assert config.memories_dir == global_dir / "memories"
            assert config.skills_dir == global_dir / "skills"

    def test_project_overrides_global(self):
        """Test that project paths override global."""
        with tempfile.TemporaryDirectory() as tmpdir:
            global_dir = Path(tmpdir) / "global"
            project_dir = Path(tmpdir) / "project"

            global_dir.mkdir()
            project_dir.mkdir()
            (global_dir / "memories").mkdir()
            (project_dir / "memories").mkdir()

            config = Config(global_dir=global_dir, project_dir=project_dir)
            assert config.memories_dir == project_dir / "memories"

    def test_save_and_load(self):
        """Test saving and loading configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            global_dir = Path(tmpdir)

            config = Config(global_dir=global_dir)
            config.model.model = "test-model"
            config.sandbox_enabled = False
            config.save()

            # Load and verify
            loaded = Config.load(config.config_file)
            assert loaded.model.model == "test-model"
            assert loaded.sandbox_enabled is False

    def test_to_dict(self):
        """Test config to dict conversion."""
        config = Config()
        d = config.to_dict()
        assert "global_dir" in d
        assert "model" in d
        assert "agent_name" in d


class TestProjectDetection:
    """Tests for project directory detection."""

    def test_detect_valis_dir(self):
        """Test detecting .valis directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            valis_dir = root / ".valis"
            valis_dir.mkdir()

            detected = detect_project_dir(root)
            assert detected.resolve() == valis_dir.resolve()

    def test_detect_walks_up(self):
        """Test detection walks up directory tree."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            valis_dir = root / ".valis"
            valis_dir.mkdir()

            subdir = root / "src" / "lib"
            subdir.mkdir(parents=True)

            detected = detect_project_dir(subdir)
            assert detected.resolve() == valis_dir.resolve()

    def test_detect_none_when_missing(self):
        """Test returns None when no .valis found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            detected = detect_project_dir(Path(tmpdir))
            assert detected is None


class TestInitProject:
    """Tests for project initialization."""

    def test_init_creates_structure(self):
        """Test init creates expected structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            valis_dir = init_project(root)

            assert valis_dir.exists()
            assert (valis_dir / "memories").is_dir()
            assert (valis_dir / "skills").is_dir()
            assert (valis_dir / "config.json").is_file()
            assert (valis_dir / "AGENTS.md").is_file()

    def test_init_creates_default_agents_md(self):
        """Test AGENTS.md has default content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            valis_dir = init_project(root)

            content = (valis_dir / "AGENTS.md").read_text()
            assert "Agent Knowledge" in content
            assert "Project Overview" in content


class TestGetConfig:
    """Tests for get_config function."""

    def test_get_config_creates_dirs(self):
        """Test get_config ensures directories exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            global_dir = Path(tmpdir) / "valis"
            config = get_config(global_dir=global_dir)

            assert global_dir.exists()
            assert (global_dir / "memories").exists()
            assert (global_dir / "skills").exists()

    def test_get_config_loads_existing(self):
        """Test Config.load loads existing config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            global_dir = Path(tmpdir)

            # Create config file
            config_data = {
                "model": {"provider": "openai", "model": "gpt-4o"},
                "sandbox_enabled": False,
            }
            global_dir.mkdir(exist_ok=True)
            config_file = global_dir / "config.json"
            with open(config_file, "w") as f:
                json.dump(config_data, f)

            # Test Config.load directly to avoid detect_project_dir
            config = Config.load(config_file)
            assert config.model.provider == "openai"
            assert config.sandbox_enabled is False
