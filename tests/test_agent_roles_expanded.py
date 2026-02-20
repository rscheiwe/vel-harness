"""Tests for expanded default subagent role set."""

from vel_harness.agents import AgentRegistry, DEFAULT_AGENTS


def test_default_agents_include_new_roles() -> None:
    for role in ("discover", "implement", "verify", "critic"):
        assert role in DEFAULT_AGENTS


def test_registry_exposes_new_roles() -> None:
    registry = AgentRegistry()
    agents = registry.list_agents()
    for role in ("discover", "implement", "verify", "critic"):
        assert role in agents
        cfg = registry.get(role)
        assert cfg.name == role

