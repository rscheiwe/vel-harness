"""
Tests for memory startup context injection in create_deep_agent.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from vel_harness.factory import create_deep_agent


def test_memory_agents_md_injected_into_system_prompt(tmp_path: Path) -> None:
    agent_name = "mem-agent"
    root = tmp_path / agent_name
    root.mkdir(parents=True, exist_ok=True)
    (root / "AGENTS.md").write_text("Remember this project rule.", encoding="utf-8")

    with patch("vel_harness.factory.Agent") as MockAgent:
        MockAgent.return_value = MagicMock()

        create_deep_agent(
            config={
                "name": agent_name,
                "model": {"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
                "sandbox": False,
                "memory": {
                    "enabled": True,
                    "persistent_base_path": str(tmp_path),
                    "agents_md_path": "/memories/AGENTS.md",
                },
            }
        )

        assert MockAgent.called
        system_prompt = MockAgent.call_args.kwargs.get("system_prompt", "")
        assert "<agent_memory>" in system_prompt
        assert "Remember this project rule." in system_prompt
